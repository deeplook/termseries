#!/usr/bin/env python3
"""Convert Fitbit JSON exports into the two-column CSV format termseries reads."""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast
from zoneinfo import ZoneInfo

Dataset = Literal["steps", "heart", "sleep"]

_FILE_PATTERNS: dict[Dataset, str] = {
    "steps": "steps-*.json",
    "heart": "heart_rate-*.json",
    "sleep": "sleep-*.json",
}
_SLEEP_STAGE_VALUES = {"wake": 0, "rem": 1, "light": 2, "deep": 3}


def _to_utc_timestamp(value: str, source_timezone: ZoneInfo) -> str:
    """Convert Fitbit's timezone-less export timestamps into ISO-8601 UTC."""
    if "T" in value:
        parsed = datetime.fromisoformat(value)
    else:
        parsed = datetime.strptime(value, "%m/%d/%y %H:%M:%S")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_timezone)
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _load_records(path: Path) -> list[object]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array.")
    return data


def _records_to_samples(
    dataset: Dataset, records: Iterable[object], source_timezone: ZoneInfo, path: Path
) -> Iterator[tuple[str, str]]:
    """Yield normalized timestamp/value rows from one Fitbit export file."""
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{path} contains a non-object record.")
        if dataset == "steps":
            date_time = record.get("dateTime")
            value = record.get("value")
            if not isinstance(date_time, str) or not isinstance(value, str):
                raise ValueError(f"{path} has an invalid steps record.")
            yield _to_utc_timestamp(date_time, source_timezone), value
        elif dataset == "heart":
            date_time = record.get("dateTime")
            value = record.get("value")
            if not isinstance(date_time, str) or not isinstance(value, dict):
                raise ValueError(f"{path} has an invalid heart-rate record.")
            bpm = value.get("bpm")
            if not isinstance(bpm, (int, float)):
                raise ValueError(f"{path} has a heart-rate record without numeric BPM.")
            yield _to_utc_timestamp(date_time, source_timezone), str(bpm)
        else:
            if record.get("mainSleep") is not True:
                continue
            levels = record.get("levels")
            if not isinstance(levels, dict):
                raise ValueError(f"{path} has a sleep record without levels data.")
            stages = levels.get("data")
            if not isinstance(stages, list):
                raise ValueError(f"{path} has a sleep record without stage data.")
            for stage in stages:
                if not isinstance(stage, dict):
                    raise ValueError(f"{path} has an invalid sleep stage.")
                date_time = stage.get("dateTime")
                level = stage.get("level")
                if not isinstance(date_time, str) or level not in _SLEEP_STAGE_VALUES:
                    raise ValueError(f"{path} has an invalid sleep stage value.")
                yield (
                    _to_utc_timestamp(date_time, source_timezone),
                    str(_SLEEP_STAGE_VALUES[cast(str, level)]),
                )


def convert_dataset(
    dataset: Dataset,
    input_dir: Path,
    output_path: Path,
    timezone_name: str = "Europe/Berlin",
) -> int:
    """Convert all matching Fitbit JSON files into one sorted, de-duplicated CSV."""
    if dataset not in _FILE_PATTERNS:
        raise ValueError(
            f"Unsupported dataset {dataset!r}; choose steps, heart, or sleep."
        )
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")

    source_timezone = ZoneInfo(timezone_name)
    input_paths = sorted(input_dir.glob(_FILE_PATTERNS[dataset]))
    if not input_paths:
        raise ValueError(f"No {_FILE_PATTERNS[dataset]!r} files found in {input_dir}.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="termseries-fitbit-") as temp_dir:
        database_path = Path(temp_dir) / "samples.sqlite3"
        with (
            contextlib.closing(sqlite3.connect(database_path)) as connection,
            connection,
        ):
            connection.execute(
                "CREATE TABLE samples (timestamp TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            for input_path in input_paths:
                connection.executemany(
                    "INSERT OR REPLACE INTO samples(timestamp, value) VALUES (?, ?)",
                    _records_to_samples(
                        dataset,
                        _load_records(input_path),
                        source_timezone,
                        input_path,
                    ),
                )
            with output_path.open("w", newline="") as output_file:
                writer = csv.writer(output_file)
                writer.writerow(["timestamp", "value"])
                writer.writerows(
                    connection.execute(
                        "SELECT timestamp, value FROM samples ORDER BY timestamp"
                    )
                )
            count = connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    return int(count)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the converter."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset",
        choices=["steps", "heart", "sleep"],
        help="Fitbit dataset to convert.",
    )
    parser.add_argument(
        "input_dir", type=Path, help="Directory containing Fitbit JSON exports."
    )
    parser.add_argument(
        "output", type=Path, help="Destination termseries timestamp,value CSV file."
    )
    parser.add_argument(
        "--timezone",
        default="Europe/Berlin",
        help=(
            "IANA timezone for the timezone-less Fitbit export timestamps "
            "(default: Europe/Berlin)."
        ),
    )
    return parser


def main() -> None:
    """Run the converter CLI."""
    arguments = build_parser().parse_args()
    count = convert_dataset(
        arguments.dataset, arguments.input_dir, arguments.output, arguments.timezone
    )
    print(f"Wrote {count} samples to {arguments.output}")


if __name__ == "__main__":
    main()
