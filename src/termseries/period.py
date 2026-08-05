"""Unified free-form period parsing and source-specific interval mapping."""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

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


_TZ_SUFFIX_RE = re.compile(r"(Z|[+-]\d{2}:\d{2})$")


def pad_datetime_str(value: str, *, round_up: bool = False) -> str:
    """Fill missing trailing components of a partial ISO-8601 string.

    By default, missing components are zero-filled to the *start* of the
    given granularity: ``"2024"`` -> ``"2024-01-01T00:00:00"``, ``"2024-05"``
    -> ``"2024-05-01T00:00:00"``, ``"2024-05-01T12"`` ->
    ``"2024-05-01T12:00:00"``.

    With ``round_up=True``, missing components instead fill to the *end* of
    the given granularity: ``"2024"`` -> ``"2024-12-31T23:59:59"``,
    ``"2024-05"`` -> ``"2024-05-31T23:59:59"`` (calendar-aware month length),
    ``"2024-05-17"`` -> ``"2024-05-17T23:59:59"``. Use this for a ``--to``
    bound so e.g. ``--to 2026`` covers all of 2026, not just its first
    instant.

    A trailing ``Z`` or ``+HH:MM``/``-HH:MM`` offset is preserved as-is.
    """
    value = value.strip()
    tz_match = _TZ_SUFFIX_RE.search(value)
    tz_suffix = ""
    if tz_match:
        tz_suffix = tz_match.group(1)
        value = value[: tz_match.start()]

    if "T" in value:
        date_part, _, time_part = value.partition("T")
    elif " " in value:
        date_part, _, time_part = value.partition(" ")
    else:
        date_part, time_part = value, ""

    date_components = date_part.split("-") if date_part else []
    if round_up:
        if len(date_components) == 1:
            date_components.append("12")
        if len(date_components) == 2:
            year, month = int(date_components[0]), int(date_components[1])
            date_components.append(str(calendar.monthrange(year, month)[1]))
    else:
        while len(date_components) < 3:
            date_components.append("01")
    date_part = "-".join(
        c if i == 0 else f"{int(c):02d}" for i, c in enumerate(date_components[:3])
    )

    time_components = time_part.split(":") if time_part else []
    if round_up:
        if not time_components:
            time_components = ["23", "59", "59"]
        else:
            while len(time_components) < 3:
                time_components.append("59")
    else:
        while len(time_components) < 3:
            time_components.append("00")
    time_part = ":".join(time_components[:3])

    return f"{date_part}T{time_part}{tz_suffix}"


def parse_time_bound(
    value: str, *, now: datetime, tz: tzinfo | None, round_up: bool = False
) -> datetime:
    """Parse an ISO-8601 instant, ``"now"``, or a relative/anchored start.

    Partial ISO dates/times (e.g. ``"2024-05"``) are padded to the right via
    :func:`pad_datetime_str`; pass ``round_up=True`` for a ``--to``-style
    bound so a partial date covers through its end, not just its start.
    Raises ``ValueError`` on invalid input.
    """
    if value == "now":
        return now
    try:
        delta = parse_period(value, tz=tz)
    except ValueError:
        delta = None
    else:
        if value in ("max", "auto"):
            raise ValueError("Time bounds cannot be 'max' or 'auto'.")
        assert delta is not None  # "max"/"auto" handled above
        return now - delta
    try:
        parsed = datetime.fromisoformat(pad_datetime_str(value, round_up=round_up))
    except ValueError as exc:
        raise ValueError(
            "Use an ISO-8601 date/time (e.g. 2026-07-01 or "
            "2026-07-01T12:00:00Z), 'now', or a value such as 7d/ytd."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(timezone.utc)


def resolve_tz(tz: str) -> tzinfo | None:
    """Resolve a ``--tz`` CLI value to a ``tzinfo``.

    ``"UTC"`` -> ``timezone.utc``, ``"local"`` -> ``None`` (meaning: use
    ``astimezone(None)``, i.e. the system's local timezone), anything else
    is treated as an IANA zone name.
    """
    if tz == "UTC":
        return timezone.utc
    if tz == "local":
        return None
    return ZoneInfo(tz)


def _to_date_cutoff(
    period: str, now: datetime | None = None, tz: tzinfo | None = timezone.utc
) -> datetime | None:
    """Return the absolute cutoff for a to-date period, or ``None``.

    Calendar boundaries (start of year/month/week/day/hour) are computed in
    *tz* (default UTC), so e.g. ``dtd`` means "since local midnight" when
    *tz* reflects the user's ``--tz`` choice, not always UTC midnight.
    """
    if period not in _TO_DATE_PERIODS:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    now = now.astimezone(tz)
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


def parse_period(value: str, *, tz: tzinfo | None = timezone.utc) -> timedelta | None:
    """Parse a free-form period string into a timedelta.

    Returns ``None`` for ``"max"``.  Raises ``ValueError`` on invalid input.
    Approximate conversions: ``mo`` = 30 days, ``y`` = 365 days.
    *tz* controls which timezone to-date periods (ytd/mtd/wtd/dtd/htd)
    anchor their calendar boundary in (default UTC).
    """
    if value in ("max", "auto"):
        return None
    if value in _TO_DATE_PERIODS:
        now = datetime.now(timezone.utc)
        cutoff = _to_date_cutoff(value, now, tz=tz)
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
    tz: tzinfo | None = timezone.utc,
) -> TimeSeries:
    """Filter *series* to points within *period* of a reference time.

    *reference* defaults to the most recent timestamp in the series.
    Pass an explicit value (e.g. ``datetime.now()``) to anchor the
    window to a fixed point so that multiple series share the same range.
    *tz* controls which timezone to-date periods (ytd/mtd/wtd/dtd/htd)
    anchor their calendar boundary in (default UTC).
    """
    cutoff = _to_date_cutoff(period, now=reference, tz=tz)
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
    period: str, data: dict[str, TimeSeries], *, tz: tzinfo | None = timezone.utc
) -> tuple[datetime, datetime] | None:
    """Compute an x-axis range ending at *now* for the given period and data.

    For a specific period the window is ``[now - delta, now]``.
    For ``"max"`` it spans from the earliest data point to now.
    For ``"auto"`` returns ``None`` so matplotlib auto-fits to the data.
    *tz* controls which timezone to-date periods anchor their boundary in.
    """
    if period == "auto":
        return None
    now = datetime.now(timezone.utc)
    cutoff = _to_date_cutoff(period, now, tz=tz)
    if cutoff is not None:
        return (cutoff, now)
    delta = parse_period(period, tz=tz)
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


def polymarket_auto_interval(period: str) -> str:
    """Pick a Polymarket aggregation interval based on period duration."""
    delta = parse_period(period)
    if delta is None:
        return "max"
    if delta <= timedelta(hours=6):
        return "1m"
    if delta <= timedelta(days=3):
        return "1h"
    if delta <= timedelta(days=30):
        return "6h"
    if delta <= timedelta(days=180):
        return "1d"
    return "1w"


def polymarket_covering_range(period: str) -> str:
    """Map any period to the smallest Polymarket-native window that covers it."""
    delta = parse_period(period)
    if delta is None:
        return "max"
    if delta <= timedelta(hours=1):
        return "1h"
    if delta <= timedelta(hours=6):
        return "6h"
    if delta <= timedelta(days=1):
        return "1d"
    if delta <= timedelta(weeks=1):
        return "1w"
    return "max"
