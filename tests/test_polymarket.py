"""Tests for termseries.polymarket module."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from termseries.polymarket import (
    _display_market_name,
    _fetch_price_history,
    _normalize_market_ref,
    _resolve_market_token,
    _search_market_payload,
    _slug_to_query,
    fetch_polymarket_series,
)


def _mock_resp(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class TestResolveMarketToken:
    def test_display_market_name_uses_party_from_question(self) -> None:
        payload = {
            "question": "Will Example Party win the most seats in the next election?"
        }
        assert _display_market_name(payload) == "Example Party"

    def test_normalizes_frontend_event_url(self) -> None:
        assert (
            _normalize_market_ref(
                "https://polymarket.com/event/fed-decision-in-october"
            )
            == "fed-decision-in-october"
        )

    def test_slug_to_query_removes_filler_words(self) -> None:
        assert _slug_to_query("will-bitcoin-hit-150k-in-2026") == "bitcoin 150k 2026"

    def test_resolves_yes_alias_to_first_token(self) -> None:
        payload = {
            "clobTokenIds": '["1001", "1002"]',
            "outcomes": '["Yes", "No"]',
        }
        with patch(
            "termseries.polymarket.requests.get", return_value=_mock_resp(payload)
        ):
            label, token_id = _resolve_market_token("some-market", "yes")
        assert label == "Yes"
        assert token_id == "1001"

    def test_resolves_case_insensitive_outcome_label(self) -> None:
        payload = {
            "clobTokenIds": '["2001", "2002"]',
            "shortOutcomes": '["Trump", "Other"]',
        }
        with patch(
            "termseries.polymarket.requests.get", return_value=_mock_resp(payload)
        ):
            label, token_id = _resolve_market_token("election-market", "trump")
        assert label == "Trump"
        assert token_id == "2001"

    def test_unknown_outcome_raises(self) -> None:
        payload = {
            "clobTokenIds": '["2001", "2002"]',
            "outcomes": '["Yes", "No"]',
        }
        with (
            patch(
                "termseries.polymarket.requests.get", return_value=_mock_resp(payload)
            ),
            pytest.raises(ValueError, match="unknown outcome"),
        ):
            _resolve_market_token("some-market", "maybe")

    def test_falls_back_to_event_slug_when_market_slug_404s(self) -> None:
        event_payload = {
            "markets": [
                {
                    "clobTokenIds": '["3001", "3002"]',
                    "outcomes": '["Yes", "No"]',
                }
            ]
        }
        with patch(
            "termseries.polymarket._get_json",
            side_effect=[RuntimeError("404 Client Error"), event_payload],
        ):
            label, token_id = _resolve_market_token("event-slug", "yes")
        assert label == "Yes"
        assert token_id == "3001"


class TestSearchMarketPayload:
    def test_prefers_best_matching_open_market(self) -> None:
        payload = {
            "events": [
                {
                    "markets": [
                        {
                            "slug": "will-bitcoin-hit-150k-by-june-30-2026",
                            "question": "Will Bitcoin hit $150k by June 30, 2026?",
                            "active": True,
                            "closed": False,
                            "endDate": "2026-06-30T04:00:00Z",
                            "clobTokenIds": '["1", "2"]',
                            "outcomes": '["Yes", "No"]',
                        },
                        {
                            "slug": "will-bitcoin-hit-150k-by-december-31-2026",
                            "question": "Will Bitcoin hit $150k by December 31, 2026?",
                            "active": True,
                            "closed": False,
                            "endDate": "2026-12-31T05:00:00Z",
                            "clobTokenIds": '["3", "4"]',
                            "outcomes": '["Yes", "No"]',
                        },
                    ]
                }
            ]
        }
        with patch("termseries.polymarket._get_json", return_value=payload):
            market = _search_market_payload("will-bitcoin-hit-150k-in-2026")
        assert market["slug"] == "will-bitcoin-hit-150k-by-december-31-2026"

    def test_resolve_market_token_falls_back_to_search(self) -> None:
        search_payload = {
            "events": [
                {
                    "markets": [
                        {
                            "slug": "will-bitcoin-hit-150k-by-december-31-2026",
                            "question": "Will Bitcoin hit $150k by December 31, 2026?",
                            "active": True,
                            "closed": False,
                            "endDate": "2026-12-31T05:00:00Z",
                            "clobTokenIds": '["3", "4"]',
                            "outcomes": '["Yes", "No"]',
                        }
                    ]
                }
            ]
        }
        with patch(
            "termseries.polymarket._get_json",
            side_effect=[
                RuntimeError("404 Client Error"),
                RuntimeError("404 Client Error"),
                search_payload,
            ],
        ):
            label, token_id = _resolve_market_token(
                "will-bitcoin-hit-150k-in-2026", "yes"
            )
        assert label == "Yes"
        assert token_id == "3"


class TestFetchPriceHistory:
    def test_parses_history_points_as_utc(self) -> None:
        payload = {"history": [{"t": 1_700_000_000, "p": 0.44}]}
        with patch(
            "termseries.polymarket.requests.get", return_value=_mock_resp(payload)
        ):
            pts = _fetch_price_history("1001", interval="1h", fidelity=5)
        assert pts == [(datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc), 0.44)]

    def test_empty_history_raises(self) -> None:
        with (
            patch(
                "termseries.polymarket.requests.get",
                return_value=_mock_resp({"history": []}),
            ),
            pytest.raises(RuntimeError, match="no price history"),
        ):
            _fetch_price_history("1001", interval="1h", fidelity=1)


class TestFetchPolymarketSeries:
    def test_fetches_market_series_and_deduplicates_slugs(self) -> None:
        market_payload = {
            "clobTokenIds": '["1001", "1002"]',
            "outcomes": '["Yes", "No"]',
        }
        history_payload = {"history": [{"t": 1_700_000_000, "p": 0.61}]}

        with patch(
            "termseries.polymarket.requests.get",
            side_effect=[_mock_resp(market_payload), _mock_resp(history_payload)],
        ) as mock_get:
            data = fetch_polymarket_series(
                ["btc-150k", "btc-150k"],
                "7d",
                outcome="yes",
                interval="1h",
                fidelity=3,
            )

        assert list(data) == ["Polymarket: Yes"]
        assert data["Polymarket: Yes"][0][1] == 0.61
        assert mock_get.call_count == 2
        history_call = mock_get.call_args_list[1]
        assert history_call.kwargs["params"]["market"] == "1001"
        assert history_call.kwargs["params"]["interval"] == "1h"
        assert history_call.kwargs["params"]["fidelity"] == 3
        assert "startTs" not in history_call.kwargs["params"]
        assert "endTs" not in history_call.kwargs["params"]

    def test_max_period_omits_time_bounds_and_uses_max_interval(self) -> None:
        market_payload = {
            "clobTokenIds": '["1001", "1002"]',
            "outcomes": '["Yes", "No"]',
        }
        history_payload = {"history": [{"t": 1_700_000_000, "p": 0.61}]}

        with patch(
            "termseries.polymarket.requests.get",
            side_effect=[_mock_resp(market_payload), _mock_resp(history_payload)],
        ) as mock_get:
            fetch_polymarket_series(["btc-150k"], "max")

        params = mock_get.call_args_list[1].kwargs["params"]
        assert params["interval"] == "max"
        assert "startTs" not in params
        assert "endTs" not in params

    def test_non_native_period_fetches_covering_window_and_trims(self) -> None:
        market_payload = {
            "clobTokenIds": '["1001", "1002"]',
            "outcomes": '["Yes", "No"]',
        }
        history_payload = {
            "history": [
                {"t": 1_700_000_000, "p": 0.10},
                {"t": 1_700_700_000, "p": 0.20},
            ]
        }

        with patch(
            "termseries.polymarket.requests.get",
            side_effect=[_mock_resp(market_payload), _mock_resp(history_payload)],
        ) as mock_get:
            data = fetch_polymarket_series(["btc-150k"], "30d")

        assert mock_get.call_args_list[1].kwargs["params"]["interval"] == "max"
        assert len(data["Polymarket: Yes"]) <= 2

    def test_empty_markets_raise(self) -> None:
        with pytest.raises(ValueError, match="No Polymarket market slugs"):
            fetch_polymarket_series([], "7d")

    def test_event_slug_expands_to_multiple_market_series(self) -> None:
        event_payload = {
            "markets": [
                {
                    "slug": "candidate-a",
                    "clobTokenIds": '["1001", "1002"]',
                    "outcomes": '["Yes", "No"]',
                },
                {
                    "slug": "candidate-b",
                    "clobTokenIds": '["2001", "2002"]',
                    "outcomes": '["Yes", "No"]',
                },
            ]
        }
        history_a = {"history": [{"t": 1_700_000_000, "p": 0.61}]}
        history_b = {"history": [{"t": 1_700_000_000, "p": 0.24}]}

        with patch(
            "termseries.polymarket._get_json",
            side_effect=[
                RuntimeError("404 Client Error"),
                event_payload,
                history_a,
                history_b,
            ],
        ):
            data = fetch_polymarket_series(["winner-event"], "30d")

        assert list(data) == ["candidate-a: Yes", "candidate-b: Yes"]

    def test_skips_markets_with_no_history_if_others_have_data(self) -> None:
        event_payload = {
            "markets": [
                {
                    "slug": "candidate-a",
                    "clobTokenIds": '["1001", "1002"]',
                    "outcomes": '["Yes", "No"]',
                },
                {
                    "slug": "candidate-b",
                    "clobTokenIds": '["2001", "2002"]',
                    "outcomes": '["Yes", "No"]',
                },
            ]
        }
        history_a = {"history": [{"t": 1_700_000_000, "p": 0.61}]}
        empty_history: dict[str, list[object]] = {"history": []}

        with patch(
            "termseries.polymarket._get_json",
            side_effect=[
                RuntimeError("404 Client Error"),
                event_payload,
                history_a,
                empty_history,
            ],
        ):
            data = fetch_polymarket_series(["winner-event"], "30d")

        assert list(data) == ["candidate-a: Yes"]
