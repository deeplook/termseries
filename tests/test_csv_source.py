"""Tests for termseries.csv_source functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from termseries.csv_source import (
    _parse_timestamp,
    _read_csv,
    fetch_csv_series,
)
from termseries.period import filter_period

# ===================================================================
# _parse_timestamp
# ===================================================================


class TestParseTimestamp:
    def test_iso8601_basic(self) -> None:
        dt = _parse_timestamp("2024-01-15T10:30:00+00:00")
        assert dt == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

    def test_iso8601_z_suffix(self) -> None:
        dt = _parse_timestamp("2024-01-15T10:30:00Z")
        assert dt == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)

    def test_iso8601_date_only(self) -> None:
        dt = _parse_timestamp("2024-01-15")
        assert dt == datetime(2024, 1, 15, tzinfo=timezone.utc)

    def test_unix_epoch_integer(self) -> None:
        dt = _parse_timestamp("1700000000")
        assert dt == datetime.fromtimestamp(1700000000, tz=timezone.utc)

    def test_unix_epoch_float(self) -> None:
        dt = _parse_timestamp("1700000000.5")
        assert dt == datetime.fromtimestamp(1700000000.5, tz=timezone.utc)

    def test_whitespace_stripped(self) -> None:
        dt = _parse_timestamp("  2024-01-15  ")
        assert dt == datetime(2024, 1, 15, tzinfo=timezone.utc)

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            _parse_timestamp("not-a-date")

    def test_naive_datetime_gets_utc(self) -> None:
        dt = _parse_timestamp("2024-06-15T12:00:00")
        assert dt.tzinfo == timezone.utc


# ===================================================================
# _read_csv
# ===================================================================


class TestReadCsv:
    def test_basic_two_column(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("2024-01-01,10.0\n2024-01-02,20.0\n")
        series = _read_csv(str(f))
        assert len(series) == 2
        assert series[0][1] == 10.0
        assert series[1][1] == 20.0

    def test_header_detection(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("timestamp,value\n2024-01-01,10.0\n2024-01-02,20.0\n")
        series = _read_csv(str(f))
        assert len(series) == 2

    def test_sorts_by_timestamp(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("2024-01-03,30.0\n2024-01-01,10.0\n2024-01-02,20.0\n")
        series = _read_csv(str(f))
        timestamps = [dt for dt, _ in series]
        assert timestamps == sorted(timestamps)

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("2024-01-01,10.0\n\n\n2024-01-02,20.0\n")
        series = _read_csv(str(f))
        assert len(series) == 2

    def test_skips_nan_and_inf(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text(
            "2024-01-01,10.0\n2024-01-02,nan\n2024-01-03,inf\n2024-01-04,20.0\n"
        )
        series = _read_csv(str(f))
        assert len(series) == 2
        assert series[0][1] == 10.0
        assert series[1][1] == 20.0

    def test_missing_file_raises(self) -> None:
        with pytest.raises(RuntimeError, match="File not found"):
            _read_csv("/nonexistent/path.csv")

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.csv"
        f.write_text("")
        with pytest.raises(RuntimeError, match="No valid data"):
            _read_csv(str(f))

    def test_header_only_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "header.csv"
        f.write_text("timestamp,value\n")
        with pytest.raises(RuntimeError, match="No valid data"):
            _read_csv(str(f))

    def test_malformed_row_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.csv"
        f.write_text("2024-01-01,10.0\n2024-01-02\n")
        with pytest.raises(RuntimeError, match="expected 2 columns"):
            _read_csv(str(f))

    def test_bad_value_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad_val.csv"
        f.write_text("2024-01-01,10.0\n2024-01-02,abc\n")
        with pytest.raises(RuntimeError, match="bad value"):
            _read_csv(str(f))

    def test_bad_timestamp_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad_ts.csv"
        f.write_text("2024-01-01,10.0\ngarbage,20.0\n")
        with pytest.raises(RuntimeError, match="bad timestamp"):
            _read_csv(str(f))


# ===================================================================
# _filter_last
# ===================================================================


class TestFilterLast:
    def _make_daily_series(self, n: int = 100) -> list[tuple[datetime, float]]:
        base = datetime(2024, 6, 1, tzinfo=timezone.utc)
        return [(base + timedelta(days=i), float(i)) for i in range(n)]

    def test_max_returns_unchanged(self) -> None:
        series = self._make_daily_series()
        assert filter_period(series, "max") == series

    def test_1d(self) -> None:
        series = self._make_daily_series()
        filtered = filter_period(series, "1d")
        assert len(filtered) == 2  # last day + 1 day back

    def test_7d(self) -> None:
        series = self._make_daily_series()
        filtered = filter_period(series, "7d")
        assert len(filtered) == 8

    def test_30d(self) -> None:
        series = self._make_daily_series()
        filtered = filter_period(series, "30d")
        assert len(filtered) == 31

    def test_empty_series(self) -> None:
        assert filter_period([], "7d") == []


# ===================================================================
# fetch_csv_series
# ===================================================================


class TestFetchCsvSeries:
    def test_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "sensor.csv"
        f.write_text("2024-01-01,10.0\n2024-01-02,20.0\n")
        result = fetch_csv_series([str(f)], "max")
        assert "sensor" in result
        assert len(result["sensor"]) == 2

    def test_multiple_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "temp.csv"
        f2 = tmp_path / "humid.csv"
        f1.write_text("2024-01-01,20.0\n2024-01-02,21.0\n")
        f2.write_text("2024-01-01,50.0\n2024-01-02,55.0\n")
        result = fetch_csv_series([str(f1), str(f2)], "max")
        assert "temp" in result
        assert "humid" in result

    def test_deduplicates_by_resolved_path(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("2024-01-01,10.0\n")
        # Pass the same file twice with different representations
        result = fetch_csv_series([str(f), str(f)], "max")
        assert len(result) == 1

    def test_applies_last_filter(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        now = datetime.now(timezone.utc)
        lines = [
            f"{(now - timedelta(days=30 - i)).strftime('%Y-%m-%dT%H:%M:%S+00:00')},"
            f"{float(i)}"
            for i in range(31)
        ]
        f.write_text("\n".join(lines) + "\n")
        result = fetch_csv_series([str(f)], "7d")
        assert 7 <= len(result["data"]) <= 8

    def test_label_from_stem(self, tmp_path: Path) -> None:
        f = tmp_path / "my_sensor_data.csv"
        f.write_text("2024-01-01,1.0\n")
        result = fetch_csv_series([str(f)], "max")
        assert "my_sensor_data" in result
