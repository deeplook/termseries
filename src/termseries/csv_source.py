"""CSV data-loading for termseries."""

from __future__ import annotations

import csv
import math
import re
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

            if val_raw.strip() == "":
                continue

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


def _read_csv_columns(path: str, columns: list[str]) -> dict[str, TimeSeries]:
    """Read a CSV with a header row and return one TimeSeries per column.

    Unlike :func:`_read_csv`, this always requires a header row so that
    *columns* can be resolved by name; there is no header auto-detection.
    """
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"File not found: {path}")
    if not p.is_file():
        raise RuntimeError(f"Not a file: {path}")

    with p.open(newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise RuntimeError(f"No valid data in {path}") from exc

        indices: dict[str, int] = {}
        for name in columns:
            try:
                indices[name] = header.index(name)
            except ValueError as exc:
                available = ", ".join(header[1:])
                hint = (
                    " Columns are comma-separated (path.csv:col1,col2); "
                    "did you mean to use commas instead of colons?"
                    if ":" in name
                    else ""
                )
                raise RuntimeError(
                    f"{path}: column {name!r} not found; available columns: "
                    f"{available}.{hint}"
                ) from exc

        series: dict[str, TimeSeries] = {name: [] for name in columns}
        for lineno, row in enumerate(reader, 2):
            if not row or all(cell.strip() == "" for cell in row):
                continue
            if len(row) < len(header):
                raise RuntimeError(
                    f"{path}:{lineno}: expected {len(header)} columns, got {len(row)}"
                )

            try:
                dt = _parse_timestamp(row[0])
            except (ValueError, OSError) as exc:
                raise RuntimeError(
                    f"{path}:{lineno}: bad timestamp {row[0]!r}"
                ) from exc

            for name, idx in indices.items():
                val_raw = row[idx]
                if val_raw.strip() == "":
                    continue
                try:
                    val = float(val_raw)
                except ValueError as exc:
                    raise RuntimeError(
                        f"{path}:{lineno}: bad value {val_raw!r} in column {name!r}"
                    ) from exc
                if math.isnan(val) or math.isinf(val):
                    continue
                series[name].append((dt, val))

    for name, rows in series.items():
        if not rows:
            raise RuntimeError(f"No valid data for column {name!r} in {path}")
        rows.sort(key=lambda r: r[0])

    return series


def _sniff_header_columns(path: str) -> list[str] | None:
    """Return the first row of *path* if it looks like a header row.

    Uses the same header-vs-data heuristic as :func:`_read_csv`: a row only
    counts as a header when neither its first nor second field parses as a
    timestamp/number. Returns ``None`` for headerless files, files with
    fewer than 2 columns, or files whose first row is data rather than a
    header.
    """
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"File not found: {path}")
    if not p.is_file():
        raise RuntimeError(f"Not a file: {path}")

    with p.open(newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or all(cell.strip() == "" for cell in row):
                continue
            if len(row) < 2:
                return None
            ts_raw, val_raw = row[0], row[1]
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
            return row if not ts_ok and not val_ok else None
    return None


_CSV_COLON_RE = re.compile(r"\.csv:", re.IGNORECASE)


def _parse_csv_arg(raw: str) -> tuple[str, list[str] | None]:
    """Split a ``path[:col1,col2,...]`` CLI argument into path and columns.

    The colon suffix is only recognised right after a ``.csv`` extension,
    not just any colon -- a naive "split on the first colon" would misparse
    a Windows absolute path with a column suffix (e.g.
    ``C:\\data\\sensors.csv:temp``), since the drive letter's colon comes
    first and isn't a ``.csv`` boundary. Matching a colon mistakenly typed
    within the column list itself (``file.csv:a:b:c``) still resolves to
    the real ``file.csv`` path, so the resulting error names the bad column
    list instead of claiming the file itself is missing.
    """
    match = _CSV_COLON_RE.search(raw)
    if match is not None:
        split_at = match.end() - 1  # index of the colon itself
        path_part, cols_part = raw[:split_at], raw[split_at + 1 :]
        if cols_part:
            columns = [c.strip() for c in cols_part.split(",") if c.strip()]
            if columns:
                return path_part, columns
    return raw, None


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

    Each entry in *paths* is a CSV file path, optionally suffixed with
    ``:col1,col2,...`` to select specific columns from a header row. Without
    a suffix, a CSV whose header has more than one value column has every
    value column auto-plotted (labelled ``<stem>.<column>``) rather than
    silently reading only the first; a plain 2-column CSV keeps its
    original ``<stem>`` label.
    """
    now = datetime.now(timezone.utc) if parse_period(period) is not None else None
    resolved_tz = resolve_tz(tz)
    seen: set[str] = set()
    result: dict[str, TimeSeries] = {}

    for raw_arg in paths:
        path, columns = _parse_csv_arg(raw_arg)
        if columns is None:
            header = _sniff_header_columns(path)
            if header is not None and len(header) > 2:
                # A wide CSV with no explicit :col selection -- auto-plot
                # every value column instead of silently dropping all but
                # the first, as a bare 2-column read would.
                columns = header[1:]
        resolved = str(Path(path).resolve())
        dedup_key = f"{resolved}:{','.join(columns)}" if columns else resolved
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if columns is not None:
            for column, column_series in _read_csv_columns(path, columns).items():
                column_series = filter_period(
                    column_series, period, reference=now, tz=resolved_tz
                )
                if not column_series:
                    raise RuntimeError(
                        f"{path}:{column}: no data left after trimming to "
                        f"period={period}."
                    )
                if resample is not None:
                    column_series = resample_series(column_series, resample, aggregate)
                label = f"{Path(path).stem}.{column}"
                result[label] = column_series
        else:
            series = _read_csv(path)
            series = filter_period(series, period, reference=now, tz=resolved_tz)
            if not series:
                raise RuntimeError(
                    f"{path}: no data left after trimming to period={period}."
                )
            if resample is not None:
                series = resample_series(series, resample, aggregate)
            label = Path(path).stem
            result[label] = series

    return result
