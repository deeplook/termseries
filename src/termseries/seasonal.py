"""Seasonal cycle wrapping: split a series into overlaid per-cycle chunks."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, tzinfo
from typing import NamedTuple

from termseries.period import parse_period
from termseries.types import TimeSeries

# Chosen because it's a leap year: every Feb 29 in the input data has a valid
# target date once remapped onto this shared reference year. Do not change
# this to a non-leap year.
REFERENCE_YEAR = 2000
assert calendar.isleap(REFERENCE_YEAR)

SECONDS_PER_WEEK = 7 * 86400
WEEKDAY_NAMES: list[str] = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


class CycleSpec(NamedTuple):
    kind: str  # "year", "quarter", or "duration"
    duration_seconds: float | None  # only set for kind == "duration"


def parse_cycle(value: str) -> CycleSpec:
    """Parse a ``--cycle`` value: ``"year"``, ``"quarter"``, or a duration.

    Durations use the same free-form syntax as ``--last``/``--gaps`` (e.g.
    ``"90d"``, ``"4w"``). Raises ``ValueError`` on invalid input.
    """
    if value == "year":
        return CycleSpec("year", None)
    if value == "quarter":
        return CycleSpec("quarter", None)
    try:
        duration = parse_period(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid cycle {value!r}. Use 'year', 'quarter', or a positive "
            "duration (e.g. 90d, 4w)."
        ) from exc
    if duration is None or duration.total_seconds() <= 0:
        raise ValueError(
            f"Invalid cycle {value!r}. Use 'year', 'quarter', or a positive "
            "duration (e.g. 90d, 4w)."
        )
    return CycleSpec("duration", duration.total_seconds())


def _to_reference_date(local: datetime) -> datetime:
    """Project a calendar date/time onto the shared reference year.

    Reconstructs the date directly from (month, day, time-of-day) rather
    than via elapsed-time arithmetic, so non-leap source years don't drift
    by a day when overlaid against the (leap) reference year.
    """
    return local.replace(year=REFERENCE_YEAR)


def _label_and_ref(
    local: datetime, first_local: datetime, spec: CycleSpec
) -> tuple[str, datetime]:
    """Compute a point's cycle label and its remapped reference-window date."""
    if spec.kind == "year":
        label = str(local.year)
        ref_dt = _to_reference_date(local)
    elif spec.kind == "quarter":
        quarter = (local.month - 1) // 3 + 1
        label = f"{local.year} Q{quarter}"
        quarter_start_month = (quarter - 1) * 3 + 1
        quarter_start = local.replace(
            month=quarter_start_month,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        quarter_elapsed = local - quarter_start
        # Every quarter overlays onto the same Jan-Mar reference window
        # regardless of which calendar quarter it came from, so the x-axis
        # shows a single quarter's width, not a year.
        ref_dt = datetime(REFERENCE_YEAR, 1, 1, tzinfo=local.tzinfo) + quarter_elapsed
    elif spec.duration_seconds == SECONDS_PER_WEEK:
        # Calendar-aligned to Monday (like quarters are aligned to
        # Jan/Apr/Jul/Oct), so weeks chain seamlessly across the data and
        # the x-axis can show weekday names starting Monday.
        weekday = local.weekday()  # Monday=0 .. Sunday=6
        week_start = (local - timedelta(days=weekday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        iso_year, iso_week, _ = local.isocalendar()
        label = f"{iso_year}-W{iso_week:02d}"
        week_elapsed = local - week_start
        ref_dt = datetime(REFERENCE_YEAR, 1, 1, tzinfo=local.tzinfo) + week_elapsed
    else:
        assert spec.duration_seconds is not None
        elapsed_seconds = (local - first_local).total_seconds()
        n = int(elapsed_seconds // spec.duration_seconds)
        label = f"chunk {n + 1}"
        offset_seconds = elapsed_seconds - n * spec.duration_seconds
        ref_dt = datetime(REFERENCE_YEAR, 1, 1, tzinfo=local.tzinfo) + timedelta(
            seconds=offset_seconds
        )
    return label, ref_dt


def wrap_series(
    data: dict[str, TimeSeries],
    cycle: str,
    *,
    tz: tzinfo | None = None,
) -> dict[str, TimeSeries]:
    """Split each series into overlaid per-cycle chunks with cycle-labeled names.

    Each output key is ``f"{name} ({cycle_label})"`` (e.g. ``"TSLA (2024)"``,
    ``"TSLA (2024 Q1)"``), and its points are remapped onto a shared
    synthetic reference year so cycles overlay on the x-axis. Partial first
    and last chunks are kept, not dropped. Output keys are ordered so a
    given input series' chunks stay adjacent, in chronological order.
    """
    spec = parse_cycle(cycle)
    result: dict[str, TimeSeries] = {}
    for name, series in data.items():
        if not series:
            result[name] = series
            continue
        chunks: dict[str, TimeSeries] = {}
        first_local = series[0][0].astimezone(tz)
        for dt, value in series:
            local = dt.astimezone(tz)
            label, ref_dt = _label_and_ref(local, first_local, spec)
            chunks.setdefault(label, []).append((ref_dt, value))
        # Input series are assumed chronologically sorted, so dict insertion
        # order already yields chunks in chronological order (a plain
        # alphabetic sort would misorder e.g. "chunk 10" before "chunk 2").
        for label, points in chunks.items():
            result[f"{name} ({label})"] = points
    return result


def count_cycles(
    data: dict[str, TimeSeries],
    cycle: str,
    *,
    tz: tzinfo | None = None,
) -> int:
    """Count distinct cycle occurrences (e.g. weeks/years) spanned by *data*.

    A cycle occurrence used by any input series counts once, even if not
    every series has data in it -- this matches how many overlaid lines
    ``wrap_series`` would produce for a single input series.
    """
    spec = parse_cycle(cycle)
    labels: set[str] = set()
    for series in data.values():
        if not series:
            continue
        first_local = series[0][0].astimezone(tz)
        for dt, _value in series:
            local = dt.astimezone(tz)
            label, _ref_dt = _label_and_ref(local, first_local, spec)
            labels.add(label)
    return len(labels)
