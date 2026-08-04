"""Tests for converting Fitbit JSON exports into termseries CSV files."""

import csv
import json
from pathlib import Path

from tools.fitbit_to_csv import convert_dataset


def write_json(path: Path, records: list[object]) -> None:
    path.write_text(json.dumps(records))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def test_convert_steps_sorts_deduplicates_and_writes_utc_csv(tmp_path: Path) -> None:
    """Minute-level step records become one ordered, renderable CSV series."""
    source = tmp_path / "data"
    source.mkdir()
    write_json(
        source / "steps-2026-08-01.json",
        [
            {"dateTime": "08/01/26 00:02:00", "value": "20"},
            {"dateTime": "08/01/26 00:01:00", "value": "10"},
        ],
    )
    write_json(
        source / "steps-2026-08-02.json",
        [{"dateTime": "08/01/26 00:02:00", "value": "20"}],
    )
    output = tmp_path / "steps.csv"

    count = convert_dataset("steps", source, output, timezone_name="Europe/Berlin")

    assert count == 2
    assert read_csv(output) == [
        {"timestamp": "2026-07-31T22:01:00Z", "value": "10"},
        {"timestamp": "2026-07-31T22:02:00Z", "value": "20"},
    ]


def test_convert_heart_extracts_bpm_values(tmp_path: Path) -> None:
    """Heart-rate records use their nested BPM field instead of confidence."""
    source = tmp_path / "data"
    source.mkdir()
    write_json(
        source / "heart_rate-2026-08-01.json",
        [{"dateTime": "08/01/26 12:00:00", "value": {"bpm": 63, "confidence": 3}}],
    )
    output = tmp_path / "heart.csv"

    count = convert_dataset("heart", source, output, timezone_name="Europe/Berlin")

    assert count == 1
    assert read_csv(output) == [{"timestamp": "2026-08-01T10:00:00Z", "value": "63"}]


def test_convert_sleep_writes_main_session_stage_timeline(tmp_path: Path) -> None:
    """Sleep stages become a numeric step series and non-main sessions are omitted."""
    source = tmp_path / "data"
    source.mkdir()
    write_json(
        source / "sleep-2026-08-01.json",
        [
            {
                "mainSleep": True,
                "levels": {
                    "data": [
                        {
                            "dateTime": "2026-08-01T00:00:00.000",
                            "level": "wake",
                            "seconds": 60,
                        },
                        {
                            "dateTime": "2026-08-01T00:01:00.000",
                            "level": "deep",
                            "seconds": 60,
                        },
                    ]
                },
            },
            {
                "mainSleep": False,
                "levels": {
                    "data": [
                        {
                            "dateTime": "2026-08-01T12:00:00.000",
                            "level": "light",
                            "seconds": 60,
                        }
                    ]
                },
            },
        ],
    )
    output = tmp_path / "sleep.csv"

    count = convert_dataset("sleep", source, output, timezone_name="Europe/Berlin")

    assert count == 2
    assert read_csv(output) == [
        {"timestamp": "2026-07-31T22:00:00Z", "value": "0"},
        {"timestamp": "2026-07-31T22:01:00Z", "value": "3"},
    ]
