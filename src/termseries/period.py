"""Unified free-form period parsing and Yahoo Finance mapping."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from termseries.types import TimeSeries

_PERIOD_RE = re.compile(r"^(\d+)(mo|[mhdwy])$")

_UNIT_TO_TIMEDELTA: dict[str, timedelta] = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
    "mo": timedelta(days=30),
    "y": timedelta(days=365),
}

_TO_DATE_PERIODS = frozenset({"ytd", "mtd", "wtd", "dtd", "htd"})


def _to_date_cutoff(period: str, now: datetime | None = None) -> datetime | None:
    """Return the absolute cutoff for a to-date period, or ``None``."""
    if period not in _TO_DATE_PERIODS:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    if period == "ytd":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "mtd":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "wtd":
        days_since_monday = now.weekday()  # Monday=0
        monday = now - timedelta(days=days_since_monday)
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "dtd":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    # htd
    return now.replace(minute=0, second=0, microsecond=0)


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
    "htd",
    "dtd",
    "wtd",
    "mtd",
    "ytd",
    "max",
    "auto",
]


def parse_period(value: str) -> timedelta | None:
    """Parse a free-form period string into a timedelta.

    Returns ``None`` for ``"max"``.  Raises ``ValueError`` on invalid input.
    Approximate conversions: ``mo`` = 30 days, ``y`` = 365 days.
    """
    if value in ("max", "auto"):
        return None
    if value in _TO_DATE_PERIODS:
        now = datetime.now(timezone.utc)
        cutoff = _to_date_cutoff(value, now)
        assert cutoff is not None  # guaranteed by _TO_DATE_PERIODS check
        return now - cutoff
    m = _PERIOD_RE.match(value)
    if not m:
        raise ValueError(
            f"Invalid period {value!r}. "
            "Use <number><unit> (e.g. 14d, 2w, 3mo), "
            "a to-date period (ytd, mtd, wtd, dtd, htd), 'max', or 'auto'."
        )
    n = int(m.group(1))
    unit = m.group(2)
    return _UNIT_TO_TIMEDELTA[unit] * n


def filter_period(
    series: TimeSeries,
    period: str,
    *,
    reference: datetime | None = None,
) -> TimeSeries:
    """Filter *series* to points within *period* of a reference time.

    *reference* defaults to the most recent timestamp in the series.
    Pass an explicit value (e.g. ``datetime.now()``) to anchor the
    window to a fixed point so that multiple series share the same range.
    """
    cutoff = _to_date_cutoff(period)
    if cutoff is not None:
        return [(dt, v) for dt, v in series if dt >= cutoff]
    delta = parse_period(period)
    if delta is None:
        return series
    if not series:
        return series
    cutoff = (reference or series[-1][0]) - delta
    return [(dt, v) for dt, v in series if dt >= cutoff]


def xlim_now(
    period: str, data: dict[str, TimeSeries]
) -> tuple[datetime, datetime] | None:
    """Compute an x-axis range ending at *now* for the given period and data.

    For a specific period the window is ``[now - delta, now]``.
    For ``"max"`` it spans from the earliest data point to now.
    For ``"auto"`` returns ``None`` so matplotlib auto-fits to the data.
    """
    if period == "auto":
        return None
    now = datetime.now(timezone.utc)
    cutoff = _to_date_cutoff(period, now)
    if cutoff is not None:
        return (cutoff, now)
    delta = parse_period(period)
    if delta is not None:
        return (now - delta, now)
    all_ts = [dt for pts in data.values() for dt, _ in pts]
    return (min(all_ts), now) if all_ts else None


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
