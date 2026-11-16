"""Tests for termseries.yahoo module."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from termseries.yahoo import _fetch_closes, fetch_yahoo_series


@pytest.fixture(autouse=True)
def mock_sleep() -> Iterator[MagicMock]:
    """Exercise pacing and retries without wall-clock delays."""
    with patch("termseries.yahoo.time.sleep") as sleep:
        yield sleep


def _mock_resp(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def _payload(timestamps: list[int], closes: list[float | None]) -> dict[str, object]:
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


# ===================================================================
# _fetch_closes
# ===================================================================


class TestFetchCloses:
    def test_happy_path(self) -> None:
        p = _payload([1_700_000_000, 1_700_086_400], [150.0, 155.0])
        with patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)):
            pts = _fetch_closes("TSLA", "1d")
        assert len(pts) == 2
        assert pts[0][1] == 150.0
        assert pts[1][1] == 155.0

    def test_timestamps_are_utc(self) -> None:
        p = _payload([0], [100.0])
        with patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)):
            pts = _fetch_closes("TSLA", "1d")
        assert pts[0][0].tzinfo == timezone.utc

    def test_none_closes_skipped(self) -> None:
        p = _payload(
            [1_700_000_000, 1_700_086_400, 1_700_172_800], [150.0, None, 155.0]
        )
        with patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)):
            pts = _fetch_closes("TSLA", "1d")
        assert len(pts) == 2
        assert pts[0][1] == 150.0
        assert pts[1][1] == 155.0

    def test_empty_result_raises(self) -> None:
        p: dict[str, object] = {"chart": {"result": []}}
        with (
            patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)),
            pytest.raises(RuntimeError, match="unexpected Yahoo response"),
        ):
            _fetch_closes("BADTICKER", "1d")

    def test_all_none_closes_raises(self) -> None:
        p = _payload([1_700_000_000], [None])
        with (
            patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)),
            pytest.raises(RuntimeError, match="no close data"),
        ):
            _fetch_closes("TSLA", "1d")

    def test_connection_error_wrapped_as_runtime_error(self) -> None:
        """A network failure must surface as RuntimeError, not a raw traceback."""
        with (
            patch(
                "termseries.yahoo.requests.Session.get",
                side_effect=requests.ConnectionError("offline"),
            ),
            pytest.raises(RuntimeError, match="Yahoo Finance request failed"),
        ):
            _fetch_closes("TSLA", "1d")

    def test_http_error_wrapped_as_runtime_error(self) -> None:
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        with (
            patch("termseries.yahoo.requests.Session.get", return_value=resp),
            pytest.raises(RuntimeError, match="Yahoo Finance request failed"),
        ):
            _fetch_closes("TSLA", "1d")

    def test_interval_included_in_url(self) -> None:
        p = _payload([1_700_000_000], [100.0])
        with patch(
            "termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)
        ) as mock:
            _fetch_closes("TSLA", "1mo", interval="1d")
        url = mock.call_args[0][0]
        assert "interval=1d" in url
        assert "range=1mo" in url


# ===================================================================
# fetch_yahoo_series
# ===================================================================


class TestFetchYahooSeries:
    def _simple_payload(self) -> dict[str, object]:
        return _payload([1_700_000_000, 1_700_086_400], [100.0, 101.0])

    def test_single_ticker(self) -> None:
        with patch(
            "termseries.yahoo.requests.Session.get",
            return_value=_mock_resp(self._simple_payload()),
        ):
            result = fetch_yahoo_series(["TSLA"], "1d")
        assert "TSLA" in result
        assert len(result["TSLA"]) == 2

    def test_uppercases_tickers(self) -> None:
        with patch(
            "termseries.yahoo.requests.Session.get",
            return_value=_mock_resp(self._simple_payload()),
        ):
            result = fetch_yahoo_series(["tsla"], "1d")
        assert "TSLA" in result

    def test_deduplicates_tickers(self) -> None:
        with patch(
            "termseries.yahoo.requests.Session.get",
            return_value=_mock_resp(self._simple_payload()),
        ):
            result = fetch_yahoo_series(["TSLA", "tsla", "TSLA"], "1d")
        assert len(result) == 1

    def test_empty_tickers_raises(self) -> None:
        with pytest.raises(ValueError, match="No ticker symbols"):
            fetch_yahoo_series([], "1d")

    def test_whitespace_only_ticker_raises(self) -> None:
        with pytest.raises(ValueError, match="No ticker symbols"):
            fetch_yahoo_series(["   "], "1d")

    def test_explicit_interval_bypasses_auto(self) -> None:
        with patch(
            "termseries.yahoo.requests.Session.get",
            return_value=_mock_resp(self._simple_payload()),
        ) as mock:
            fetch_yahoo_series(["TSLA"], "1d", interval="1h")
        url = mock.call_args[0][0]
        assert "interval=1h" in url

    def test_non_native_period_trims(self) -> None:
        """A period like '14d' maps to covering range '1mo' and is trimmed."""
        import datetime as _dt

        now = datetime.now(timezone.utc)
        # 36 daily points spanning the last 35 days
        timestamps = [
            int((now - _dt.timedelta(days=35 - i)).timestamp()) for i in range(36)
        ]
        closes: list[float | None] = [100.0 + i for i in range(36)]
        p = _payload(timestamps, closes)
        with patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)):
            result = fetch_yahoo_series(["TSLA"], "14d")
        # After trimming to 14 days we should have fewer than all 36 points
        assert len(result["TSLA"]) < 36

    def test_period_that_trims_to_nothing_raises_instead_of_empty_series(
        self,
    ) -> None:
        """A degenerate period (e.g. 0d) must raise, not silently return an
        empty series that renders as a blank chart with no error."""
        import datetime as _dt

        now = datetime.now(timezone.utc)
        timestamps = [int((now - _dt.timedelta(days=1)).timestamp())]
        p = _payload(timestamps, [100.0])
        with (
            patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)),
            pytest.raises(RuntimeError, match="no data left after trimming"),
        ):
            fetch_yahoo_series(["TSLA"], "0d")

    def test_multiple_tickers_share_the_same_trim_reference(self) -> None:
        """Two tickers trimmed in the same call must share one reference time,
        not each anchor to their own last data point (which could differ)."""
        p = self._simple_payload()
        with (
            patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)),
            patch(
                "termseries.yahoo.filter_period", wraps=lambda pts, *a, **kw: pts
            ) as mock_filter,
        ):
            fetch_yahoo_series(["TSLA", "AAPL"], "14d")
        assert mock_filter.call_count == 2
        references = {call.kwargs["reference"] for call in mock_filter.call_args_list}
        assert len(references) == 1
        assert next(iter(references)) is not None

    def test_tz_is_resolved_and_threaded_to_filter_period(self) -> None:
        p = self._simple_payload()
        with (
            patch("termseries.yahoo.requests.Session.get", return_value=_mock_resp(p)),
            patch(
                "termseries.yahoo.filter_period", wraps=lambda pts, *a, **kw: pts
            ) as mock_filter,
        ):
            fetch_yahoo_series(["TSLA"], "14d", tz="America/Los_Angeles")
        assert str(mock_filter.call_args.kwargs["tz"]) == "America/Los_Angeles"


class TestRateLimits:
    def test_retries_429_then_returns_data(self, mock_sleep: MagicMock) -> None:
        limited = _mock_resp({})
        limited.status_code = 429
        limited.headers = {}
        with patch(
            "termseries.yahoo.requests.Session.get",
            side_effect=[limited, _mock_resp(_payload([0], [100.0]))],
        ) as get:
            assert _fetch_closes("NVDA", "1d") == [
                (datetime.fromtimestamp(0, timezone.utc), 100.0)
            ]
        assert get.call_count == 2
        limited.close.assert_called_once()
        mock_sleep.assert_called_once()
        assert 30 <= mock_sleep.call_args.args[0] <= 31

    @pytest.mark.parametrize("retry_after", ["120", "Thu, 01 Jan 2026 00:02:00 GMT"])
    def test_honors_retry_after(self, retry_after: str, mock_sleep: MagicMock) -> None:
        limited = _mock_resp({})
        limited.status_code = 429
        limited.headers = {"Retry-After": retry_after}
        with (
            patch("termseries.yahoo.time.time", return_value=1767225600),
            patch(
                "termseries.yahoo.requests.Session.get",
                side_effect=[limited, _mock_resp(_payload([0], [100.0]))],
            ),
        ):
            _fetch_closes("NVDA", "1d")
        assert 120 <= mock_sleep.call_args.args[0] <= 121

    @pytest.mark.parametrize(
        "retry_after", ["bad", "NaN", "inf", "-1", "Wed, 31 Dec 2025 23:59:00 GMT"]
    )
    def test_bad_or_past_retry_after_uses_backoff(
        self, retry_after: str, mock_sleep: MagicMock
    ) -> None:
        limited = _mock_resp({})
        limited.status_code = 429
        limited.headers = {"Retry-After": retry_after}
        with (
            patch("termseries.yahoo.time.time", return_value=1767225600),
            patch(
                "termseries.yahoo.requests.Session.get",
                side_effect=[limited, _mock_resp(_payload([0], [100.0]))],
            ),
        ):
            _fetch_closes("NVDA", "1d")
        assert 30 <= mock_sleep.call_args.args[0] <= 31

    def test_persistent_429_stops_after_three_requests(
        self, mock_sleep: MagicMock
    ) -> None:
        limited = _mock_resp({})
        limited.status_code = 429
        limited.headers = {}
        with (
            patch("termseries.yahoo.requests.Session.get", return_value=limited) as get,
            pytest.raises(RuntimeError, match="NVDA.*HTTP 429.*retry later"),
        ):
            fetch_yahoo_series(["NVDA", "AAPL"], "1d")
        assert get.call_count == 3  # no mirror requests or subsequent ticker
        assert mock_sleep.call_count == 2  # no sleep after the final attempt
        assert 30 <= mock_sleep.call_args_list[0].args[0] <= 31
        assert 60 <= mock_sleep.call_args_list[1].args[0] <= 61

    def test_success_needs_one_request_and_no_sleep(
        self, mock_sleep: MagicMock
    ) -> None:
        with patch(
            "termseries.yahoo.requests.Session.get",
            return_value=_mock_resp(_payload([0], [100.0])),
        ) as get:
            _fetch_closes("NVDA", "1d")
        get.assert_called_once()
        mock_sleep.assert_not_called()

    def test_batch_shares_session_and_paces_unique_tickers(
        self, mock_sleep: MagicMock
    ) -> None:
        with patch(
            "termseries.yahoo.requests.Session.get",
            autospec=True,
            return_value=_mock_resp(_payload([0], [100.0])),
        ) as get:
            result = fetch_yahoo_series(["nvda", "NVDA", "AAPL", "MSFT"], "1d")
        assert list(result) == ["NVDA", "AAPL", "MSFT"]
        assert get.call_count == 3
        assert len({id(call.args[0]) for call in get.call_args_list}) == 1
        assert mock_sleep.call_args_list == [((2,),), ((2,),)]
