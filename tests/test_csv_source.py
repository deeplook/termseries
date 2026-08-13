"""Tests for termseries.csv_source functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from termseries.csv_source import (
    _parse_csv_arg,
    _parse_timestamp,
    _read_csv,
    _read_csv_columns,
    _sniff_header_columns,
    fetch_csv_series,
    resample_series,
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

    def test_directory_raises_not_a_file(self, tmp_path: Path) -> None:
        """Passing a directory must raise a clean error, not crash with a
        raw IsADirectoryError from Path.open()."""
        with pytest.raises(RuntimeError, match="Not a file"):
            _read_csv(str(tmp_path))

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

    def test_blank_value_skipped_not_error(self, tmp_path: Path) -> None:
        f = tmp_path / "sparse.csv"
        f.write_text("2024-01-01,10.0\n2024-01-02,\n2024-01-03,20.0\n")
        series = _read_csv(str(f))
        assert len(series) == 2
        assert [v for _, v in series] == [10.0, 20.0]

    def test_bad_timestamp_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad_ts.csv"
        f.write_text("2024-01-01,10.0\ngarbage,20.0\n")
        with pytest.raises(RuntimeError, match="bad timestamp"):
            _read_csv(str(f))

    def test_corrupt_first_row_raises_not_silently_skipped(
        self, tmp_path: Path
    ) -> None:
        """A bad-timestamp-but-valid-value first row is corrupt data, not a
        header, and should raise rather than being silently dropped."""
        f = tmp_path / "corrupt_first.csv"
        f.write_text("garbage,100\n2024-01-02,20.0\n")
        with pytest.raises(RuntimeError, match="bad timestamp"):
            _read_csv(str(f))


# ===================================================================
# _parse_csv_arg
# ===================================================================


class TestParseCsvArg:
    def test_plain_path_unchanged(self) -> None:
        assert _parse_csv_arg("data.csv") == ("data.csv", None)

    def test_path_with_columns(self) -> None:
        assert _parse_csv_arg("data.csv:temp,humidity") == (
            "data.csv",
            ["temp", "humidity"],
        )

    def test_single_column(self) -> None:
        assert _parse_csv_arg("data.csv:temp") == ("data.csv", ["temp"])

    def test_strips_whitespace_around_columns(self) -> None:
        assert _parse_csv_arg("data.csv: temp , humidity ") == (
            "data.csv",
            ["temp", "humidity"],
        )

    def test_windows_drive_letter_not_misparsed(self) -> None:
        assert _parse_csv_arg("C:\\data.csv") == ("C:\\data.csv", None)

    def test_trailing_colon_with_no_columns_unchanged(self) -> None:
        assert _parse_csv_arg("data.csv:") == ("data.csv:", None)

    def test_colon_typo_still_resolves_real_path(self) -> None:
        """A column list mistakenly colon- instead of comma-separated must
        still split off the real path, so downstream code reports a bad
        column list rather than a nonexistent file."""
        assert _parse_csv_arg("data.csv:TESLA:BMW:MERCEDES") == (
            "data.csv",
            ["TESLA:BMW:MERCEDES"],
        )

    def test_windows_absolute_path_with_columns(self) -> None:
        """Regression test: a naive "split on the first colon" misparses a
        Windows absolute path with a column suffix, since the drive
        letter's colon comes first and isn't a .csv boundary -- the whole
        string (including the column suffix) was wrongly treated as a
        literal, nonexistent path."""
        assert _parse_csv_arg("C:\\data\\sensors.csv:temp,humidity") == (
            "C:\\data\\sensors.csv",
            ["temp", "humidity"],
        )

    def test_windows_absolute_path_with_columns_and_typo(self) -> None:
        assert _parse_csv_arg("C:\\data\\sensors.csv:temp:humidity") == (
            "C:\\data\\sensors.csv",
            ["temp:humidity"],
        )


# ===================================================================
# _sniff_header_columns
# ===================================================================


class TestSniffHeaderColumns:
    def test_detects_header_row(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp,humidity\n2024-01-01,20.0,50.0\n")
        assert _sniff_header_columns(str(f)) == ["timestamp", "temp", "humidity"]

    def test_no_header_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("2024-01-01,20.0,50.0\n")
        assert _sniff_header_columns(str(f)) is None

    def test_two_column_header_returns_header(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("timestamp,value\n2024-01-01,10.0\n")
        assert _sniff_header_columns(str(f)) == ["timestamp", "value"]

    def test_two_column_no_header_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("2024-01-01,10.0\n")
        assert _sniff_header_columns(str(f)) is None

    def test_skips_leading_blank_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("\n\ntimestamp,temp,humidity\n2024-01-01,20.0,50.0\n")
        assert _sniff_header_columns(str(f)) == ["timestamp", "temp", "humidity"]

    def test_missing_file_raises(self) -> None:
        with pytest.raises(RuntimeError, match="File not found"):
            _sniff_header_columns("/nonexistent/path.csv")


# ===================================================================
# _read_csv_columns
# ===================================================================


class TestReadCsvColumns:
    def test_selects_requested_columns(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text(
            "timestamp,temp,humidity,pressure\n"
            "2024-01-01,20.0,50.0,1013.0\n"
            "2024-01-02,21.0,55.0,1012.0\n"
        )
        result = _read_csv_columns(str(f), ["temp", "humidity"])
        assert set(result) == {"temp", "humidity"}
        assert result["temp"][0][1] == 20.0
        assert result["humidity"][1][1] == 55.0

    def test_sorts_each_column_by_timestamp(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp\n2024-01-03,3.0\n2024-01-01,1.0\n2024-01-02,2.0\n")
        result = _read_csv_columns(str(f), ["temp"])
        assert [v for _, v in result["temp"]] == [1.0, 2.0, 3.0]

    def test_unknown_column_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp\n2024-01-01,20.0\n")
        with pytest.raises(RuntimeError, match="column 'bogus' not found"):
            _read_csv_columns(str(f), ["bogus"])

    def test_colon_typo_gets_comma_hint(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp,humidity\n2024-01-01,20.0,50.0\n")
        with pytest.raises(RuntimeError, match="use commas instead of colons"):
            _read_csv_columns(str(f), ["temp:humidity"])

    def test_missing_file_raises(self) -> None:
        with pytest.raises(RuntimeError, match="File not found"):
            _read_csv_columns("/nonexistent/path.csv", ["temp"])

    def test_header_only_raises_no_valid_data(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp\n")
        with pytest.raises(RuntimeError, match="No valid data for column"):
            _read_csv_columns(str(f), ["temp"])

    def test_skips_nan_and_inf_per_column(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text(
            "timestamp,temp,humidity\n"
            "2024-01-01,10.0,nan\n"
            "2024-01-02,nan,50.0\n"
            "2024-01-03,20.0,60.0\n"
        )
        result = _read_csv_columns(str(f), ["temp", "humidity"])
        assert [v for _, v in result["temp"]] == [10.0, 20.0]
        assert [v for _, v in result["humidity"]] == [50.0, 60.0]

    def test_bad_value_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp\n2024-01-01,abc\n")
        with pytest.raises(RuntimeError, match="bad value"):
            _read_csv_columns(str(f), ["temp"])

    def test_blank_value_skipped_not_error(self, tmp_path: Path) -> None:
        """Real-world wide CSVs (e.g. per-brand monthly counts) commonly
        leave a cell blank for a column with no data at that timestamp,
        rather than writing 'nan'. That must be treated as a missing point
        for that column, not a hard parse error."""
        f = tmp_path / "sensors.csv"
        f.write_text(
            "timestamp,temp,humidity\n"
            "2024-01-01,10.0,\n"
            "2024-01-02,,50.0\n"
            "2024-01-03,20.0,60.0\n"
        )
        result = _read_csv_columns(str(f), ["temp", "humidity"])
        assert [v for _, v in result["temp"]] == [10.0, 20.0]
        assert [v for _, v in result["humidity"]] == [50.0, 60.0]

    def test_bad_timestamp_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp\ngarbage,20.0\n")
        with pytest.raises(RuntimeError, match="bad timestamp"):
            _read_csv_columns(str(f), ["temp"])


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


class TestResampleSeries:
    def test_mean_groups_values_in_epoch_aligned_buckets(self) -> None:
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        series = [
            (base + timedelta(seconds=10), 60.0),
            (base + timedelta(seconds=50), 90.0),
            (base + timedelta(minutes=1, seconds=10), 120.0),
        ]

        assert resample_series(series, "1m") == [
            (base, 75.0),
            (base + timedelta(minutes=1), 120.0),
        ]

    def test_other_aggregates(self) -> None:
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        series = [
            (base, 1.0),
            (base + timedelta(seconds=2), 9.0),
            (base + timedelta(seconds=3), 3.0),
        ]

        assert resample_series(series, "1m", "median")[0][1] == 3.0
        assert resample_series(series, "1m", "min")[0][1] == 1.0
        assert resample_series(series, "1m", "max")[0][1] == 9.0
        assert resample_series(series, "1m", "sum")[0][1] == 13.0
        assert resample_series(series, "1m", "count")[0][1] == 3.0
        assert resample_series(series, "1m", "first")[0][1] == 1.0
        assert resample_series(series, "1m", "last")[0][1] == 3.0

    @pytest.mark.parametrize(
        "interval", ["max", "auto", "ytd", "mtd", "wtd", "dtd", "htd", "0m", "bogus"]
    )
    def test_rejects_non_positive_or_non_duration_intervals(
        self, interval: str
    ) -> None:
        with pytest.raises(ValueError):
            resample_series([], interval)

    def test_rejects_unknown_aggregate(self) -> None:
        with pytest.raises(ValueError, match="Unknown aggregate"):
            resample_series([], "1m", "average")


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

    def test_period_that_trims_to_nothing_raises_instead_of_empty_series(
        self, tmp_path: Path
    ) -> None:
        """A degenerate period (e.g. 0d) must raise, not silently return an
        empty series that renders as a blank chart with no error."""
        f = tmp_path / "data.csv"
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        f.write_text(f"{yesterday.strftime('%Y-%m-%dT%H:%M:%S+00:00')},10.0\n")
        with pytest.raises(RuntimeError, match="no data left after trimming"):
            fetch_csv_series([str(f)], "0d")

    def test_label_from_stem(self, tmp_path: Path) -> None:
        f = tmp_path / "my_sensor_data.csv"
        f.write_text("2024-01-01,1.0\n")
        result = fetch_csv_series([str(f)], "max")
        assert "my_sensor_data" in result

    def test_resamples_after_filtering(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("2024-01-01T00:00:10Z,10\n2024-01-01T00:00:50Z,20\n")
        result = fetch_csv_series([str(f)], "max", resample="1m")
        assert result["data"] == [(datetime(2024, 1, 1, tzinfo=timezone.utc), 15.0)]

    def test_multi_column_selection(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text(
            "timestamp,temp,humidity\n2024-01-01,20.0,50.0\n2024-01-02,21.0,55.0\n"
        )
        result = fetch_csv_series([f"{f}:temp,humidity"], "max")
        assert set(result) == {"sensors.temp", "sensors.humidity"}
        assert result["sensors.temp"][0][1] == 20.0
        assert result["sensors.humidity"][1][1] == 55.0

    def test_mixes_plain_files_and_column_selection(self, tmp_path: Path) -> None:
        plain = tmp_path / "pressure.csv"
        plain.write_text("2024-01-01,1013.0\n")
        wide = tmp_path / "sensors.csv"
        wide.write_text("timestamp,temp\n2024-01-01,20.0\n")
        result = fetch_csv_series([str(plain), f"{wide}:temp"], "max")
        assert set(result) == {"pressure", "sensors.temp"}

    def test_deduplicates_by_path_and_columns(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp,humidity\n2024-01-01,20.0,50.0\n")
        result = fetch_csv_series([f"{f}:temp", f"{f}:temp"], "max")
        assert list(result) == ["sensors.temp"]

    def test_same_file_different_columns_not_deduplicated(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp,humidity\n2024-01-01,20.0,50.0\n")
        result = fetch_csv_series([f"{f}:temp", f"{f}:humidity"], "max")
        assert set(result) == {"sensors.temp", "sensors.humidity"}

    def test_column_period_that_trims_to_nothing_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        f.write_text(
            f"timestamp,temp\n{yesterday.strftime('%Y-%m-%dT%H:%M:%S+00:00')},20.0\n"
        )
        with pytest.raises(RuntimeError, match="no data left after trimming"):
            fetch_csv_series([f"{f}:temp"], "0d")

    def test_wide_headered_csv_without_suffix_plots_every_column(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text(
            "timestamp,temp,humidity,pressure\n"
            "2024-01-01,20.0,50.0,1013.0\n"
            "2024-01-02,21.0,55.0,1012.0\n"
        )
        result = fetch_csv_series([str(f)], "max")
        assert set(result) == {"sensors.temp", "sensors.humidity", "sensors.pressure"}
        assert result["sensors.pressure"][0][1] == 1013.0

    def test_two_column_headered_csv_keeps_legacy_label(self, tmp_path: Path) -> None:
        f = tmp_path / "sensor.csv"
        f.write_text("timestamp,value\n2024-01-01,10.0\n2024-01-02,20.0\n")
        result = fetch_csv_series([str(f)], "max")
        assert list(result) == ["sensor"]

    def test_explicit_columns_override_auto_expansion(self, tmp_path: Path) -> None:
        f = tmp_path / "sensors.csv"
        f.write_text("timestamp,temp,humidity,pressure\n2024-01-01,20.0,50.0,1013.0\n")
        result = fetch_csv_series([f"{f}:temp"], "max")
        assert list(result) == ["sensors.temp"]

    def test_tz_is_resolved_and_threaded_to_filter_period(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("2024-01-01,10.0\n")
        with patch(
            "termseries.csv_source.filter_period", wraps=lambda pts, *a, **kw: pts
        ) as mock_filter:
            fetch_csv_series([str(f)], "ytd", tz="America/Los_Angeles")
        assert str(mock_filter.call_args.kwargs["tz"]) == "America/Los_Angeles"
