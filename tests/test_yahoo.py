"""Tests for termseries.yahoo module."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from termseries.yahoo import _fetch_closes, fetch_yahoo_series


def _mock_resp(payload: object) -> MagicMock:
    resp = MagicMock()
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
        with patch("termseries.yahoo.requests.get", return_value=_mock_resp(p)):
            pts = _fetch_closes("TSLA", "1d")
        assert len(pts) == 2
        assert pts[0][1] == 150.0
        assert pts[1][1] == 155.0

    def test_timestamps_are_utc(self) -> None:
        p = _payload([0], [100.0])
        with patch("termseries.yahoo.requests.get", return_value=_mock_resp(p)):
            pts = _fetch_closes("TSLA", "1d")
        assert pts[0][0].tzinfo == timezone.utc

    def test_none_closes_skipped(self) -> None:
        p = _payload(
            [1_700_000_000, 1_700_086_400, 1_700_172_800], [150.0, None, 155.0]
        )
        with patch("termseries.yahoo.requests.get", return_value=_mock_resp(p)):
            pts = _fetch_closes("TSLA", "1d")
        assert len(pts) == 2
        assert pts[0][1] == 150.0
        assert pts[1][1] == 155.0

    def test_empty_result_raises(self) -> None:
        p: dict[str, object] = {"chart": {"result": []}}
        with (
            patch("termseries.yahoo.requests.get", return_value=_mock_resp(p)),
            pytest.raises(RuntimeError, match="unexpected Yahoo response"),
        ):
            _fetch_closes("BADTICKER", "1d")

    def test_all_none_closes_raises(self) -> None:
        p = _payload([1_700_000_000], [None])
        with (
            patch("termseries.yahoo.requests.get", return_value=_mock_resp(p)),
            pytest.raises(RuntimeError, match="no close data"),
        ):
            _fetch_closes("TSLA", "1d")

    def test_interval_included_in_url(self) -> None:
        p = _payload([1_700_000_000], [100.0])
        with patch("termseries.yahoo.requests.get", return_value=_mock_resp(p)) as mock:
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
            "termseries.yahoo.requests.get",
            return_value=_mock_resp(self._simple_payload()),
        ):
            result = fetch_yahoo_series(["TSLA"], "1d")
        assert "TSLA" in result
        assert len(result["TSLA"]) == 2

    def test_uppercases_tickers(self) -> None:
        with patch(
            "termseries.yahoo.requests.get",
            return_value=_mock_resp(self._simple_payload()),
        ):
            result = fetch_yahoo_series(["tsla"], "1d")
        assert "TSLA" in result

    def test_deduplicates_tickers(self) -> None:
        with patch(
            "termseries.yahoo.requests.get",
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
            "termseries.yahoo.requests.get",
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
        with patch("termseries.yahoo.requests.get", return_value=_mock_resp(p)):
            result = fetch_yahoo_series(["TSLA"], "14d")
        # After trimming to 14 days we should have fewer than all 36 points
        assert len(result["TSLA"]) < 36
