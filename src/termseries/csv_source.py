"""CSV data-loading for termseries."""

from __future__ import annotations

import csv
import math
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from termseries.period import filter_period, parse_period, resolve_tz
from termseries.types import TimeSeries

_AGGREGATES: dict[str, Callable[[list[float]], float]] = {
    "mean": lambda values: sum(values) / len(values),
    "median": median,
    "min": min,
    "max": max,
    "sum": sum,
    "count": lambda values: float(len(values)),
    "first": lambda values: values[0],
    "last": lambda values: values[-1],
}

# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


def _parse_timestamp(raw: str) -> datetime:
    """Parse an ISO 8601 string or Unix epoch into a UTC-aware datetime."""
    raw = raw.strip()

    # Try Unix epoch (pure numeric, possibly with decimal)
    try:
        ts = float(raw)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except ValueError:
        pass

    # Handle trailing Z for Python 3.10 compat (fromisoformat doesn't accept it)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------


def _read_csv(path: str) -> TimeSeries:
    """Read a two-column CSV (timestamp, value) and return a sorted TimeSeries.

    Raises ``RuntimeError`` on missing file, empty data, or malformed rows.
    """
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"File not found: {path}")
    if not p.is_file():
        raise RuntimeError(f"Not a file: {path}")

    rows: TimeSeries = []
    with p.open(newline="") as f:
        reader = csv.reader(f)
        header_skipped = False
        for lineno, row in enumerate(reader, 1):
            # skip blank lines
            if not row or all(cell.strip() == "" for cell in row):
                continue

            if len(row) < 2:
                if lineno == 1 and not header_skipped:
                    # might be a single-column header, skip
                    header_skipped = True
                    continue
                raise RuntimeError(
                    f"{path}:{lineno}: expected 2 columns, got {len(row)}"
                )

            ts_raw, val_raw = row[0], row[1]

            # Auto-detect header: only treat the first non-blank row as a
            # header if *neither* column looks like real data. A row with a
            # bad timestamp but a valid numeric value is more likely a
            # corrupt data row than a header, so let it fall through to the
            # normal parsing below (and raise a clear error).
            if not header_skipped and not rows:
                ts_ok = True
                try:
                    _parse_timestamp(ts_raw)
                except (ValueError, OSError):
                    ts_ok = False
                val_ok = True
                try:
                    float(val_raw)
                except ValueError:
                    val_ok = False
                if not ts_ok and not val_ok:
                    header_skipped = True
                    continue

            try:
                dt = _parse_timestamp(ts_raw)
            except (ValueError, OSError) as exc:
                raise RuntimeError(
                    f"{path}:{lineno}: bad timestamp {ts_raw!r}"
                ) from exc

            try:
                val = float(val_raw)
            except ValueError as exc:
                raise RuntimeError(f"{path}:{lineno}: bad value {val_raw!r}") from exc

            if math.isnan(val) or math.isinf(val):
                continue

            rows.append((dt, val))

    if not rows:
        raise RuntimeError(f"No valid data in {path}")

    rows.sort(key=lambda r: r[0])
    return rows


# ---------------------------------------------------------------------------
# Public fetch function
# ---------------------------------------------------------------------------


def resample_series(
    series: TimeSeries, interval: str, aggregate: str = "mean"
) -> TimeSeries:
    """Reduce a series into fixed UTC buckets.

    *interval* uses duration syntax (for example ``"1m"`` or ``"1h"``).
    Buckets are aligned to the Unix epoch and represented by their starting
    timestamp. ``aggregate`` must be one of :data:`_AGGREGATES`.
    """
    try:
        width = parse_period(interval)
    except ValueError as exc:
        raise ValueError(f"Invalid resample interval {interval!r}: {exc}") from exc
    if interval in {"max", "auto", "ytd", "mtd", "wtd", "dtd", "htd"} or (
        width is None or width.total_seconds() <= 0
    ):
        raise ValueError(
            f"Resample interval must be a positive duration, got {interval!r}."
        )
    try:
        reducer = _AGGREGATES[aggregate]
    except KeyError as exc:
        choices = ", ".join(_AGGREGATES)
        raise ValueError(
            f"Unknown aggregate {aggregate!r}; choose one of: {choices}."
        ) from exc

    width_seconds = width.total_seconds()
    buckets: dict[int, list[float]] = {}
    for timestamp, value in series:
        bucket = math.floor(timestamp.timestamp() / width_seconds)
        buckets.setdefault(bucket, []).append(value)

    return [
        (
            datetime.fromtimestamp(bucket * width_seconds, tz=timezone.utc),
            reducer(values),
        )
        for bucket, values in sorted(buckets.items())
    ]


def fetch_csv_series(
    paths: list[str],
    period: str,
    *,
    tz: str = "UTC",
    resample: str | None = None,
    aggregate: str = "mean",
) -> dict[str, TimeSeries]:
    """Load CSV files and return labelled time-series data.

    Conforms to the ``fetch_fn`` signature used by the TUI and CLI.

    The period window is anchored to *now* so that all series share the
    same time range (rather than each being truncated to its own last
    timestamp). *tz* controls which timezone to-date periods
    (ytd/mtd/wtd/dtd/htd) anchor their calendar boundary in. When *resample*
    is set, each filtered series is reduced into fixed UTC buckets using
    *aggregate*.
    """
    now = datetime.now(timezone.utc) if parse_period(period) is not None else None
    resolved_tz = resolve_tz(tz)
    seen: set[str] = set()
    result: dict[str, TimeSeries] = {}

    for raw_path in paths:
        resolved = str(Path(raw_path).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)

        series = _read_csv(raw_path)
        series = filter_period(series, period, reference=now, tz=resolved_tz)
        if not series:
            raise RuntimeError(
                f"{raw_path}: no data left after trimming to period={period}."
            )
        if resample is not None:
            series = resample_series(series, resample, aggregate)
        label = Path(raw_path).stem
        result[label] = series

    return result
