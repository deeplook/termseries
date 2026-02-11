"""Unified free-form period parsing and Yahoo Finance mapping."""

from __future__ import annotations

import re
from datetime import timedelta

from termseries._types import TimeSeries

_PERIOD_RE = re.compile(r"^(\d+)(mo|[mhdwy])$")

_UNIT_TO_TIMEDELTA: dict[str, timedelta] = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
    "mo": timedelta(days=30),
    "y": timedelta(days=365),
}

# Yahoo-native ranges in ascending order of duration.
_YAHOO_NATIVE_RANGES: list[tuple[str, timedelta]] = [
    ("1d", timedelta(days=1)),
    ("5d", timedelta(days=5)),
    ("1mo", timedelta(days=30)),
    ("3mo", timedelta(days=90)),
    ("6mo", timedelta(days=180)),
    ("1y", timedelta(days=365)),
    ("2y", timedelta(days=730)),
    ("5y", timedelta(days=1825)),
    ("10y", timedelta(days=3650)),
]

TUI_PERIOD_CHOICES: list[str] = [
    "30m",
    "1h",
    "3h",
    "6h",
    "12h",
    "1d",
    "2d",
    "5d",
    "7d",
    "2w",
    "1mo",
    "3mo",
    "6mo",
    "1y",
    "2y",
    "5y",
    "10y",
    "max",
]


def parse_period(value: str) -> timedelta | None:
    """Parse a free-form period string into a timedelta.

    Returns ``None`` for ``"max"``.  Raises ``ValueError`` on invalid input.
    Approximate conversions: ``mo`` = 30 days, ``y`` = 365 days.
    """
    if value == "max":
        return None
    m = _PERIOD_RE.match(value)
    if not m:
        raise ValueError(
            f"Invalid period {value!r}. "
            "Use <number><unit> (e.g. 14d, 2w, 3mo) or 'max'."
        )
    n = int(m.group(1))
    unit = m.group(2)
    return _UNIT_TO_TIMEDELTA[unit] * n


def filter_period(series: TimeSeries, period: str) -> TimeSeries:
    """Filter *series* to points within *period* of the most recent timestamp."""
    delta = parse_period(period)
    if delta is None:
        return series
    if not series:
        return series
    cutoff = series[-1][0] - delta
    return [(dt, v) for dt, v in series if dt >= cutoff]


def yahoo_covering_range(period: str) -> str:
    """Map any period to the smallest Yahoo-native range that covers it.

    Returns ``"max"`` for ``"max"`` or periods exceeding 10 years.
    """
    delta = parse_period(period)
    if delta is None:
        return "max"
    for native_str, native_td in _YAHOO_NATIVE_RANGES:
        if delta <= native_td:
            return native_str
    return "max"


def yahoo_auto_interval(period: str) -> str:
    """Pick a Yahoo interval based on period duration.

    Threshold-based: ``<=1d`` → ``"5m"``, ``<=7d`` → ``"15m"``, else ``"1d"``.
    """
    delta = parse_period(period)
    if delta is None:
        return "1d"
    if delta <= timedelta(days=1):
        return "5m"
    if delta <= timedelta(days=7):
        return "15m"
    return "1d"
