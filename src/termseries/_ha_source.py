"""Home Assistant data source for termseries.

Fetches sensor history from a running Home Assistant instance via the
REST API.  Connection is configured through environment variables:

- ``HASS_URL``   – base URL (e.g. ``http://homeassistant.local:8123``)
- ``HASS_TOKEN`` – long-lived access token
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from termseries._csv_source import _LAST_DELTAS, _filter_last, _parse_timestamp
from termseries._types import TimeSeries

# ---------------------------------------------------------------------------
# Low-level HTTP helper
# ---------------------------------------------------------------------------


def _ha_request(path: str) -> Any:
    """Send an authenticated GET to the Home Assistant REST API.

    Returns the parsed JSON body.  Raises ``RuntimeError`` on missing env
    vars, connection errors, or non-200 responses.
    """
    base_url = os.environ.get("HASS_URL")
    token = os.environ.get("HASS_TOKEN")
    if not base_url or not token:
        raise RuntimeError("HASS_URL and HASS_TOKEN environment variables must be set.")

    url = f"{base_url.rstrip('/')}{path}"

    try:
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
    except requests.ConnectionError as exc:
        raise RuntimeError(
            f"Failed to connect to Home Assistant at {url}: {exc}"
        ) from exc

    if resp.status_code != 200:
        raise RuntimeError(
            f"Home Assistant API returned HTTP {resp.status_code} for {path}"
        )
    return resp.json()


# ---------------------------------------------------------------------------
# Entity history
# ---------------------------------------------------------------------------


def _fetch_ha_entity(entity_id: str, period: str) -> TimeSeries:
    """Fetch history for a single HA entity and return a sorted TimeSeries.

    *period* is a :class:`LastPeriod` value string (e.g. ``"7d"``).
    """
    delta = _LAST_DELTAS.get(period)
    if delta is None:
        # "all" — request a very large window (10 years)
        start = datetime(2015, 1, 1, tzinfo=timezone.utc)
    else:
        start = datetime.now(tz=timezone.utc) - delta

    now = datetime.now(tz=timezone.utc)
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    path = (
        f"/api/history/period/{start_iso}"
        f"?end_time={end_iso}"
        f"&filter_entity_id={entity_id}"
        f"&minimal_response&no_attributes&significant_changes_only"
    )

    data = _ha_request(path)

    # HA returns a list of lists; first (and only when filtering by one
    # entity) element is the list of state-change objects.
    if not data or not data[0]:
        raise RuntimeError(
            f"No history data for entity {entity_id} in period {period}."
        )

    points: TimeSeries = []
    for entry in data[0]:
        state_str = entry.get("state", "")
        try:
            value = float(state_str)
        except (ValueError, TypeError):
            # Skip non-numeric states like "unavailable", "unknown", etc.
            continue

        dt = _parse_timestamp(entry["last_changed"])
        points.append((dt, value))

    if not points:
        raise RuntimeError(
            f"No numeric states for entity {entity_id} in period {period}."
        )

    points.sort(key=lambda r: r[0])

    # The HA history API includes the state at the period start as the first
    # entry, with ``last_changed`` set to when that state was *actually* set —
    # which can be well before ``start``.  Drop any such stale points so the
    # chart doesn't show an artifact (a diagonal line from a stale value).
    points = [(dt, v) for dt, v in points if dt >= start]

    return _filter_last(points, period)


# ---------------------------------------------------------------------------
# Unit detection
# ---------------------------------------------------------------------------


def _detect_unit(entity_id: str) -> str:
    """Return the ``unit_of_measurement`` attribute for *entity_id*.

    Falls back to ``"value"`` when the attribute is absent.
    """
    data = _ha_request(f"/api/states/{entity_id}")
    return (data.get("attributes") or {}).get("unit_of_measurement") or "value"


# ---------------------------------------------------------------------------
# Public fetch function
# ---------------------------------------------------------------------------


def fetch_ha_series(entity_ids: list[str], period: str) -> dict[str, TimeSeries]:
    """Fetch HA sensor history and return labelled time-series data.

    Conforms to the ``fetch_fn`` signature used by the TUI and CLI.
    Labels use the ``friendly_name`` attribute when available, falling
    back to the raw *entity_id*.
    """
    seen: set[str] = set()
    result: dict[str, TimeSeries] = {}

    for eid in entity_ids:
        eid = eid.strip()
        if eid in seen:
            continue
        seen.add(eid)

        series = _fetch_ha_entity(eid, period)

        # Determine a friendly label
        state_data = _ha_request(f"/api/states/{eid}")
        label = (state_data.get("attributes") or {}).get("friendly_name") or eid

        result[label] = series

    return result
