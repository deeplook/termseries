"""CSV data-loading for termseries.

Named ``_csv_source`` to avoid shadowing the stdlib ``csv`` module.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from pathlib import Path

from termseries._period import filter_period
from termseries._types import TimeSeries

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

            # Auto-detect header: try parsing the first non-blank row
            if not header_skipped and not rows:
                try:
                    _parse_timestamp(ts_raw)
                except (ValueError, OSError):
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


def fetch_csv_series(paths: list[str], period: str) -> dict[str, TimeSeries]:
    """Load CSV files and return labelled time-series data.

    Conforms to the ``fetch_fn`` signature used by the TUI and CLI.
    """
    seen: set[str] = set()
    result: dict[str, TimeSeries] = {}

    for raw_path in paths:
        resolved = str(Path(raw_path).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)

        series = _read_csv(raw_path)
        series = filter_period(series, period)
        label = Path(raw_path).stem
        result[label] = series

    return result
