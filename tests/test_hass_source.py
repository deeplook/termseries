"""Tests for termseries.hass_source functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from termseries.hass_source import (
    _detect_unit,
    _fetch_hass_entity,
    _hass_request,
    expand_entities,
    fetch_hass_series,
)


def _recent_iso(hours_ago: float) -> str:
    """Return an ISO 8601 timestamp *hours_ago* hours before now (UTC)."""
    dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _mock_response(body: object, status: int = 200) -> MagicMock:
    """Create a fake ``requests.Response``-like object."""
    resp = MagicMock()
    resp.json.return_value = body
    resp.status_code = status
    return resp


# ===================================================================
# _hass_request
# ===================================================================


class TestHaRequest:
    def test_missing_env_vars_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HASS_SERVER", raising=False)
        monkeypatch.delenv("HASS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="HASS_SERVER and HASS_TOKEN"):
            _hass_request("/api/states")

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.delenv("HASS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="HASS_SERVER and HASS_TOKEN"):
            _hass_request("/api/states")

    def test_missing_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HASS_SERVER", raising=False)
        monkeypatch.setenv("HASS_TOKEN", "tok")
        with pytest.raises(RuntimeError, match="HASS_SERVER and HASS_TOKEN"):
            _hass_request("/api/states")

    def test_successful_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "test-token")

        resp = _mock_response({"key": "value"})
        with patch("termseries.hass_source.requests.get", return_value=resp):
            result = _hass_request("/api/states")
        assert result == {"key": "value"}

    def test_trailing_slash_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123/")
        monkeypatch.setenv("HASS_TOKEN", "test-token")

        resp = _mock_response([])
        with patch(
            "termseries.hass_source.requests.get", return_value=resp
        ) as mock_get:
            _hass_request("/api/states")
        # Check that the URL was built correctly (no double slash)
        assert mock_get.call_args[0][0] == "http://ha.local:8123/api/states"

    def test_connection_error_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "test-token")

        with (
            patch(
                "termseries.hass_source.requests.get",
                side_effect=requests.ConnectionError("Connection refused"),
            ),
            pytest.raises(RuntimeError, match="Failed to connect"),
        ):
            _hass_request("/api/states")


# ===================================================================
# _fetch_hass_entity
# ===================================================================


class TestFetchHaEntity:
    def test_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                {"state": "21.5", "last_changed": _recent_iso(3)},
                {"state": "22.0", "last_changed": _recent_iso(2)},
                {"state": "22.8", "last_changed": _recent_iso(1)},
            ]
        ]
        resp = _mock_response(history)
        with patch("termseries.hass_source.requests.get", return_value=resp):
            series = _fetch_hass_entity("sensor.temp", "7d")

        assert len(series) == 3
        assert series[0][1] == 21.5
        assert series[2][1] == 22.8
        # Sorted by timestamp
        timestamps = [dt for dt, _ in series]
        assert timestamps == sorted(timestamps)

    def test_drops_stale_initial_point(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The HA API includes a synthetic state at the period start whose
        last_changed can predate the window — this must be dropped."""
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                # Stale point: last_changed is 30 days ago (outside 7d window)
                {"state": "0.0", "last_changed": _recent_iso(24 * 30)},
                # Real points within 7d
                {"state": "22.0", "last_changed": _recent_iso(2)},
                {"state": "22.8", "last_changed": _recent_iso(1)},
            ]
        ]
        resp = _mock_response(history)
        with patch("termseries.hass_source.requests.get", return_value=resp):
            series = _fetch_hass_entity("sensor.temp", "7d")

        assert len(series) == 2
        assert series[0][1] == 22.0

    def test_filters_non_numeric_states(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                {"state": "21.5", "last_changed": "2024-06-10T10:00:00+00:00"},
                {"state": "unavailable", "last_changed": "2024-06-10T11:00:00+00:00"},
                {"state": "unknown", "last_changed": "2024-06-10T12:00:00+00:00"},
                {"state": "22.0", "last_changed": "2024-06-10T13:00:00+00:00"},
            ]
        ]
        resp = _mock_response(history)
        with patch("termseries.hass_source.requests.get", return_value=resp):
            series = _fetch_hass_entity("sensor.temp", "max")

        assert len(series) == 2
        assert series[0][1] == 21.5
        assert series[1][1] == 22.0

    def test_period_that_trims_to_nothing_raises_instead_of_empty_series(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A degenerate period (e.g. 0d) must raise, not silently return an
        empty series that renders as a blank chart with no error."""
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                {"state": "21.5", "last_changed": _recent_iso(1)},
            ]
        ]
        resp = _mock_response(history)
        with (
            patch("termseries.hass_source.requests.get", return_value=resp),
            pytest.raises(RuntimeError, match="left after trimming"),
        ):
            _fetch_hass_entity("sensor.temp", "0d")

    def test_empty_history_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        resp = _mock_response([[]])
        with (
            patch("termseries.hass_source.requests.get", return_value=resp),
            pytest.raises(RuntimeError, match="No history data"),
        ):
            _fetch_hass_entity("sensor.temp", "7d")

    def test_all_non_numeric_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                {"state": "unavailable", "last_changed": "2024-06-10T10:00:00+00:00"},
                {"state": "unknown", "last_changed": "2024-06-10T11:00:00+00:00"},
            ]
        ]
        resp = _mock_response(history)
        with (
            patch("termseries.hass_source.requests.get", return_value=resp),
            pytest.raises(RuntimeError, match="No numeric states"),
        ):
            _fetch_hass_entity("sensor.temp", "7d")

    def test_no_data_at_all_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        resp = _mock_response([])
        with (
            patch("termseries.hass_source.requests.get", return_value=resp),
            pytest.raises(RuntimeError, match="No history data"),
        ):
            _fetch_hass_entity("sensor.temp", "7d")

    def test_sorts_unsorted_history(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                {"state": "22.0", "last_changed": "2024-06-10T12:00:00+00:00"},
                {"state": "21.0", "last_changed": "2024-06-10T10:00:00+00:00"},
                {"state": "21.5", "last_changed": "2024-06-10T11:00:00+00:00"},
            ]
        ]
        resp = _mock_response(history)
        with patch("termseries.hass_source.requests.get", return_value=resp):
            series = _fetch_hass_entity("sensor.temp", "max")

        timestamps = [dt for dt, _ in series]
        assert timestamps == sorted(timestamps)
        assert series[0][1] == 21.0
        assert series[1][1] == 21.5
        assert series[2][1] == 22.0


# ===================================================================
# _detect_unit
# ===================================================================


class TestDetectUnit:
    def test_returns_unit_of_measurement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        state = {
            "entity_id": "sensor.temp",
            "state": "21.5",
            "attributes": {"unit_of_measurement": "\u00b0C", "friendly_name": "Temp"},
        }
        resp = _mock_response(state)
        with patch("termseries.hass_source.requests.get", return_value=resp):
            assert _detect_unit("sensor.temp") == "\u00b0C"

    def test_fallback_to_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        state = {
            "entity_id": "sensor.custom",
            "state": "42",
            "attributes": {"friendly_name": "Custom Sensor"},
        }
        resp = _mock_response(state)
        with patch("termseries.hass_source.requests.get", return_value=resp):
            assert _detect_unit("sensor.custom") == "value"

    def test_empty_attributes_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        state = {"entity_id": "sensor.bare", "state": "1", "attributes": {}}
        resp = _mock_response(state)
        with patch("termseries.hass_source.requests.get", return_value=resp):
            assert _detect_unit("sensor.bare") == "value"


# ===================================================================
# expand_entities
# ===================================================================


class TestExpandEntities:
    _ALL_STATES = [
        {"entity_id": "sensor.sciphone_battery_level"},
        {"entity_id": "sensor.home_int_battery_level"},
        {"entity_id": "sensor.sciphone_battery_level_2"},
        {"entity_id": "sensor.living_room_temperature"},
    ]

    def test_literal_ids_pass_through_without_network(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No wildcard chars -> no /api/states request is made."""
        with patch(
            "termseries.hass_source.requests.get",
            side_effect=AssertionError("should not hit the network"),
        ):
            result = expand_entities(["sensor.temp", " sensor.humid "])

        assert result == ["sensor.temp", "sensor.humid"]

    def test_literal_ids_still_deduplicated(self) -> None:
        assert expand_entities(["sensor.temp", "sensor.temp"]) == ["sensor.temp"]

    def test_glob_pattern_matches_and_is_unanchored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        resp = _mock_response(self._ALL_STATES)

        with patch("termseries.hass_source.requests.get", return_value=resp):
            result = expand_entities(["sensor.*battery_level"])

        assert result == [
            "sensor.home_int_battery_level",
            "sensor.sciphone_battery_level",
            "sensor.sciphone_battery_level_2",
        ]

    def test_mixes_literal_and_pattern(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        resp = _mock_response(self._ALL_STATES)

        with patch("termseries.hass_source.requests.get", return_value=resp):
            result = expand_entities(
                ["sensor.living_room_temperature", "sensor.*battery_level"]
            )

        assert result == [
            "sensor.living_room_temperature",
            "sensor.home_int_battery_level",
            "sensor.sciphone_battery_level",
            "sensor.sciphone_battery_level_2",
        ]

    def test_no_match_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        resp = _mock_response(self._ALL_STATES)

        with (
            patch("termseries.hass_source.requests.get", return_value=resp),
            pytest.raises(RuntimeError, match="No entities matched"),
        ):
            expand_entities(["sensor.nonexistent_*"])

    def test_question_mark_matches_single_char(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        resp = _mock_response(self._ALL_STATES)

        with patch("termseries.hass_source.requests.get", return_value=resp):
            result = expand_entities(["sensor.sciphone_battery_level_?"])

        assert result == ["sensor.sciphone_battery_level_2"]


# ===================================================================
# fetch_hass_series
# ===================================================================


class TestFetchHaSeries:
    def _make_mocks(self) -> dict[str, object]:
        """Return mock responses keyed by API path prefix."""
        history_a = [
            [
                {"state": "21.5", "last_changed": "2024-06-10T10:00:00+00:00"},
                {"state": "22.0", "last_changed": "2024-06-10T11:00:00+00:00"},
            ]
        ]
        history_b = [
            [
                {"state": "50.0", "last_changed": "2024-06-10T10:00:00+00:00"},
                {"state": "55.0", "last_changed": "2024-06-10T11:00:00+00:00"},
            ]
        ]
        state_a = {
            "entity_id": "sensor.temp",
            "state": "22.0",
            "attributes": {
                "unit_of_measurement": "\u00b0C",
                "friendly_name": "Living Room Temperature",
            },
        }
        state_b = {
            "entity_id": "sensor.humid",
            "state": "55.0",
            "attributes": {
                "unit_of_measurement": "%",
                "friendly_name": "Bedroom Humidity",
            },
        }
        return {
            "history_a": history_a,
            "history_b": history_b,
            "state_a": state_a,
            "state_b": state_b,
        }

    def _side_effect(self, mocks: dict[str, Any]) -> Any:
        """Return a requests.get side-effect that dispatches by URL."""

        def get(url: str, **kwargs: Any) -> Any:
            if "/api/history/period/" in url and "sensor.temp" in url:
                return _mock_response(mocks["history_a"])
            if "/api/history/period/" in url and "sensor.humid" in url:
                return _mock_response(mocks["history_b"])
            if "/api/states/sensor.temp" in url:
                return _mock_response(mocks["state_a"])
            if "/api/states/sensor.humid" in url:
                return _mock_response(mocks["state_b"])
            raise ValueError(f"Unexpected URL: {url}")

        return get

    def test_single_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        mocks = self._make_mocks()

        with patch(
            "termseries.hass_source.requests.get",
            side_effect=self._side_effect(mocks),
        ):
            result = fetch_hass_series(["sensor.temp"], "max")

        assert "Living Room Temperature" in result
        assert len(result["Living Room Temperature"]) == 2

    def test_multiple_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        mocks = self._make_mocks()

        with patch(
            "termseries.hass_source.requests.get",
            side_effect=self._side_effect(mocks),
        ):
            result = fetch_hass_series(["sensor.temp", "sensor.humid"], "max")

        assert "Living Room Temperature" in result
        assert "Bedroom Humidity" in result

    def test_multiple_entities_share_the_same_reference(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two entities fetched in one call must share one reference time,
        not each anchor independently to their own request-time 'now'."""
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        mocks = self._make_mocks()

        with (
            patch(
                "termseries.hass_source.requests.get",
                side_effect=self._side_effect(mocks),
            ),
            patch(
                "termseries.hass_source._fetch_hass_entity",
                wraps=_fetch_hass_entity,
            ) as spy,
        ):
            fetch_hass_series(["sensor.temp", "sensor.humid"], "max")

        assert spy.call_count == 2
        references = {call.kwargs["reference"] for call in spy.call_args_list}
        assert len(references) == 1
        assert next(iter(references)) is not None

    def test_tz_is_resolved_and_threaded_to_fetch_entity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tz= kwarg must reach _fetch_hass_entity as a resolved tzinfo,
        not the raw string, and must not just be silently dropped."""
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        mocks = self._make_mocks()

        with (
            patch(
                "termseries.hass_source.requests.get",
                side_effect=self._side_effect(mocks),
            ),
            patch(
                "termseries.hass_source._fetch_hass_entity",
                wraps=_fetch_hass_entity,
            ) as spy,
        ):
            fetch_hass_series(["sensor.temp"], "max", tz="America/Los_Angeles")

        assert str(spy.call_args.kwargs["tz"]) == "America/Los_Angeles"

    def test_deduplicates_entity_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        mocks = self._make_mocks()

        with patch(
            "termseries.hass_source.requests.get",
            side_effect=self._side_effect(mocks),
        ):
            result = fetch_hass_series(
                ["sensor.temp", "sensor.temp", "sensor.temp"], "max"
            )

        assert len(result) == 1

    def test_fallback_label_to_entity_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_SERVER", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                {"state": "42.0", "last_changed": "2024-06-10T10:00:00+00:00"},
            ]
        ]
        state = {
            "entity_id": "sensor.no_name",
            "state": "42.0",
            "attributes": {},
        }

        def get(url: str, **kwargs: Any) -> Any:
            if "/api/history/period/" in url:
                return _mock_response(history)
            if "/api/states/" in url:
                return _mock_response(state)
            raise ValueError(f"Unexpected URL: {url}")

        with patch("termseries.hass_source.requests.get", side_effect=get):
            result = fetch_hass_series(["sensor.no_name"], "max")

        assert "sensor.no_name" in result
