"""Tests for termseries._ha_source functions."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import patch

import pytest

from termseries._ha_source import (
    _detect_unit,
    _fetch_ha_entity,
    _ha_request,
    fetch_ha_series,
)


def _mock_response(body: object, status: int = 200) -> io.BytesIO:
    """Create a fake HTTP response object."""
    data = json.dumps(body).encode("utf-8")
    resp = io.BytesIO(data)
    resp.status = status  # type: ignore[attr-defined]
    return resp


# ===================================================================
# _ha_request
# ===================================================================


class TestHaRequest:
    def test_missing_env_vars_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HASS_URL", raising=False)
        monkeypatch.delenv("HASS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="HASS_URL and HASS_TOKEN"):
            _ha_request("/api/states")

    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.delenv("HASS_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="HASS_URL and HASS_TOKEN"):
            _ha_request("/api/states")

    def test_missing_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HASS_URL", raising=False)
        monkeypatch.setenv("HASS_TOKEN", "tok")
        with pytest.raises(RuntimeError, match="HASS_URL and HASS_TOKEN"):
            _ha_request("/api/states")

    def test_successful_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "test-token")

        resp = _mock_response({"key": "value"})
        with patch("termseries._ha_source.urllib.request.urlopen", return_value=resp):
            result = _ha_request("/api/states")
        assert result == {"key": "value"}

    def test_trailing_slash_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123/")
        monkeypatch.setenv("HASS_TOKEN", "test-token")

        resp = _mock_response([])
        with patch(
            "termseries._ha_source.urllib.request.urlopen", return_value=resp
        ) as mock_urlopen:
            _ha_request("/api/states")
        # Check that the URL was built correctly (no double slash)
        called_req = mock_urlopen.call_args[0][0]
        assert called_req.full_url == "http://ha.local:8123/api/states"

    def test_connection_error_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "test-token")

        import urllib.error

        with (
            patch(
                "termseries._ha_source.urllib.request.urlopen",
                side_effect=urllib.error.URLError("Connection refused"),
            ),
            pytest.raises(RuntimeError, match="Failed to connect"),
        ):
            _ha_request("/api/states")


# ===================================================================
# _fetch_ha_entity
# ===================================================================


_SAMPLE_HISTORY = [
    [
        {
            "state": "21.5",
            "last_changed": "2024-06-10T10:00:00+00:00",
        },
        {
            "state": "22.0",
            "last_changed": "2024-06-10T11:00:00+00:00",
        },
        {
            "state": "22.8",
            "last_changed": "2024-06-10T12:00:00+00:00",
        },
    ]
]


class TestFetchHaEntity:
    def test_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        resp = _mock_response(_SAMPLE_HISTORY)
        with patch("termseries._ha_source.urllib.request.urlopen", return_value=resp):
            series = _fetch_ha_entity("sensor.temp", "7d")

        assert len(series) == 3
        assert series[0][1] == 21.5
        assert series[2][1] == 22.8
        # Sorted by timestamp
        timestamps = [dt for dt, _ in series]
        assert timestamps == sorted(timestamps)

    def test_filters_non_numeric_states(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
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
        with patch("termseries._ha_source.urllib.request.urlopen", return_value=resp):
            series = _fetch_ha_entity("sensor.temp", "all")

        assert len(series) == 2
        assert series[0][1] == 21.5
        assert series[1][1] == 22.0

    def test_empty_history_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        resp = _mock_response([[]])
        with (
            patch("termseries._ha_source.urllib.request.urlopen", return_value=resp),
            pytest.raises(RuntimeError, match="No history data"),
        ):
            _fetch_ha_entity("sensor.temp", "7d")

    def test_all_non_numeric_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                {"state": "unavailable", "last_changed": "2024-06-10T10:00:00+00:00"},
                {"state": "unknown", "last_changed": "2024-06-10T11:00:00+00:00"},
            ]
        ]
        resp = _mock_response(history)
        with (
            patch("termseries._ha_source.urllib.request.urlopen", return_value=resp),
            pytest.raises(RuntimeError, match="No numeric states"),
        ):
            _fetch_ha_entity("sensor.temp", "7d")

    def test_no_data_at_all_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        resp = _mock_response([])
        with (
            patch("termseries._ha_source.urllib.request.urlopen", return_value=resp),
            pytest.raises(RuntimeError, match="No history data"),
        ):
            _fetch_ha_entity("sensor.temp", "7d")

    def test_sorts_unsorted_history(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        history = [
            [
                {"state": "22.0", "last_changed": "2024-06-10T12:00:00+00:00"},
                {"state": "21.0", "last_changed": "2024-06-10T10:00:00+00:00"},
                {"state": "21.5", "last_changed": "2024-06-10T11:00:00+00:00"},
            ]
        ]
        resp = _mock_response(history)
        with patch("termseries._ha_source.urllib.request.urlopen", return_value=resp):
            series = _fetch_ha_entity("sensor.temp", "all")

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
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        state = {
            "entity_id": "sensor.temp",
            "state": "21.5",
            "attributes": {"unit_of_measurement": "\u00b0C", "friendly_name": "Temp"},
        }
        resp = _mock_response(state)
        with patch("termseries._ha_source.urllib.request.urlopen", return_value=resp):
            assert _detect_unit("sensor.temp") == "\u00b0C"

    def test_fallback_to_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        state = {
            "entity_id": "sensor.custom",
            "state": "42",
            "attributes": {"friendly_name": "Custom Sensor"},
        }
        resp = _mock_response(state)
        with patch("termseries._ha_source.urllib.request.urlopen", return_value=resp):
            assert _detect_unit("sensor.custom") == "value"

    def test_empty_attributes_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")

        state = {"entity_id": "sensor.bare", "state": "1", "attributes": {}}
        resp = _mock_response(state)
        with patch("termseries._ha_source.urllib.request.urlopen", return_value=resp):
            assert _detect_unit("sensor.bare") == "value"


# ===================================================================
# fetch_ha_series
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
        """Return a urlopen side-effect that dispatches by URL path."""

        def urlopen(req: Any, **kwargs: Any) -> Any:
            url = req.full_url
            if "/api/history/period/" in url and "sensor.temp" in url:
                return _mock_response(mocks["history_a"])
            if "/api/history/period/" in url and "sensor.humid" in url:
                return _mock_response(mocks["history_b"])
            if "/api/states/sensor.temp" in url:
                return _mock_response(mocks["state_a"])
            if "/api/states/sensor.humid" in url:
                return _mock_response(mocks["state_b"])
            raise ValueError(f"Unexpected URL: {url}")

        return urlopen

    def test_single_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        mocks = self._make_mocks()

        with patch(
            "termseries._ha_source.urllib.request.urlopen",
            side_effect=self._side_effect(mocks),
        ):
            result = fetch_ha_series(["sensor.temp"], "all")

        assert "Living Room Temperature" in result
        assert len(result["Living Room Temperature"]) == 2

    def test_multiple_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        mocks = self._make_mocks()

        with patch(
            "termseries._ha_source.urllib.request.urlopen",
            side_effect=self._side_effect(mocks),
        ):
            result = fetch_ha_series(["sensor.temp", "sensor.humid"], "all")

        assert "Living Room Temperature" in result
        assert "Bedroom Humidity" in result

    def test_deduplicates_entity_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
        monkeypatch.setenv("HASS_TOKEN", "tok")
        mocks = self._make_mocks()

        with patch(
            "termseries._ha_source.urllib.request.urlopen",
            side_effect=self._side_effect(mocks),
        ):
            result = fetch_ha_series(
                ["sensor.temp", "sensor.temp", "sensor.temp"], "all"
            )

        assert len(result) == 1

    def test_fallback_label_to_entity_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HASS_URL", "http://ha.local:8123")
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

        def urlopen(req: Any, **kwargs: Any) -> Any:
            url = req.full_url
            if "/api/history/period/" in url:
                return _mock_response(history)
            if "/api/states/" in url:
                return _mock_response(state)
            raise ValueError(f"Unexpected URL: {url}")

        with patch("termseries._ha_source.urllib.request.urlopen", side_effect=urlopen):
            result = fetch_ha_series(["sensor.no_name"], "all")

        assert "sensor.no_name" in result
