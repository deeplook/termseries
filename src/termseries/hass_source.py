"""Home Assistant data source for termseries.

Fetches sensor history from a running Home Assistant instance via the
REST API.  Connection is configured through environment variables:

- ``HASS_SERVER`` – base URL (e.g. ``http://homeassistant.local:8123``)
- ``HASS_TOKEN``  – long-lived access token
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from termseries.csv_source import _parse_timestamp
from termseries.period import filter_period, parse_period
from termseries.types import TimeSeries

# ---------------------------------------------------------------------------
# Low-level HTTP helper
# ---------------------------------------------------------------------------


def _hass_request(path: str) -> Any:
    """Send an authenticated GET to the Home Assistant REST API.

    Returns the parsed JSON body.  Raises ``RuntimeError`` on missing env
    vars, connection errors, or non-200 responses.
    """
    base_url = os.environ.get("HASS_SERVER")
    token = os.environ.get("HASS_TOKEN")
    if not base_url or not token:
        raise RuntimeError(
            "HASS_SERVER and HASS_TOKEN environment variables must be set."
        )

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
# Entity ID pattern expansion
# ---------------------------------------------------------------------------

_PATTERN_CHARS = re.compile(r"[*?]")


def _is_pattern(entity_id: str) -> bool:
    return bool(_PATTERN_CHARS.search(entity_id))


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Build an unanchored regex from a shell-glob-like pattern.

    ``*`` matches any run of characters and ``?`` matches a single
    character; everything else is matched literally. Unlike ``fnmatch``,
    the match is *not* anchored to the full entity ID, so a pattern like
    ``sensor.*battery_level`` also matches a trailing suffix such as
    ``sensor.phone_battery_level_2``.
    """
    parts = re.split(r"([*?])", pattern)
    regex = "".join(
        ".*" if part == "*" else "." if part == "?" else re.escape(part)
        for part in parts
    )
    return re.compile(regex)


def expand_entities(entity_ids: list[str]) -> list[str]:
    """Expand glob-style patterns (``*``, ``?``) against live HA entity IDs.

    Literal entity IDs (no wildcard characters) pass through unchanged.
    Patterns are resolved against the full list of entities currently known
    to Home Assistant, in one ``/api/states`` request shared across all
    patterns. Raises ``RuntimeError`` if a pattern matches nothing.
    """
    all_ids: list[str] = []
    if any(_is_pattern(e) for e in entity_ids):
        states = _hass_request("/api/states")
        all_ids = sorted(s["entity_id"] for s in states)

    resolved: list[str] = []
    seen: set[str] = set()
    for raw in entity_ids:
        eid = raw.strip()
        if _is_pattern(eid):
            regex = _pattern_to_regex(eid)
            matches = [m for m in all_ids if regex.search(m)]
            if not matches:
                raise RuntimeError(f"No entities matched pattern {eid!r}.")
            for m in matches:
                if m not in seen:
                    seen.add(m)
                    resolved.append(m)
        elif eid not in seen:
            seen.add(eid)
            resolved.append(eid)

    return resolved


# ---------------------------------------------------------------------------
# Entity history
# ---------------------------------------------------------------------------


def _fetch_hass_entity(
    entity_id: str, period: str, *, reference: datetime | None = None
) -> TimeSeries:
    """Fetch history for a single HA entity and return a sorted TimeSeries.

    *period* is a :class:`LastPeriod` value string (e.g. ``"7d"``).
    *reference* anchors both the request window and the final trim; pass
    the same value across entities in one call so they share a range.
    """
    now = reference if reference is not None else datetime.now(tz=timezone.utc)
    delta = parse_period(period)
    if delta is None:  # noqa: SIM108 -- if/else reads clearer with this comment
        # "max" — request a very large window (10 years)
        start = datetime(2015, 1, 1, tzinfo=timezone.utc)
    else:
        start = now - delta

    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    path = (
        f"/api/history/period/{start_iso}"
        f"?end_time={end_iso}"
        f"&filter_entity_id={entity_id}"
        f"&minimal_response&no_attributes&significant_changes_only"
    )

    data = _hass_request(path)

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

    return filter_period(points, period, reference=now)


# ---------------------------------------------------------------------------
# Unit detection
# ---------------------------------------------------------------------------


def _detect_unit(entity_id: str) -> str:
    """Return the ``unit_of_measurement`` attribute for *entity_id*.

    Falls back to ``"value"`` when the attribute is absent.
    """
    data = _hass_request(f"/api/states/{entity_id}")
    return (data.get("attributes") or {}).get("unit_of_measurement") or "value"


# ---------------------------------------------------------------------------
# Public fetch function
# ---------------------------------------------------------------------------


def fetch_hass_series(entity_ids: list[str], period: str) -> dict[str, TimeSeries]:
    """Fetch HA sensor history and return labelled time-series data.

    Conforms to the ``fetch_fn`` signature used by the TUI and CLI.
    Labels use the ``friendly_name`` attribute when available, falling
    back to the raw *entity_id*. Entity IDs may include glob-style
    patterns (``*``, ``?``); see :func:`expand_entities`.
    """
    result: dict[str, TimeSeries] = {}
    reference = datetime.now(tz=timezone.utc)

    for eid in expand_entities(entity_ids):
        series = _fetch_hass_entity(eid, period, reference=reference)

        # Determine a friendly label
        state_data = _hass_request(f"/api/states/{eid}")
        label = (state_data.get("attributes") or {}).get("friendly_name") or eid

        # Disambiguate entities that share the same friendly_name so one
        # doesn't silently overwrite another in the result dict.
        if label in result:
            label = f"{label} ({eid})"

        result[label] = series

    return result
