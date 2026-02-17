"""Tests for termseries.gaps module."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
import typer

from termseries.cli import _apply_gaps, _validate_gaps
from termseries.gaps import insert_gaps
from termseries.types import TimeSeries


def _ts(minutes: list[int], values: list[float] | None = None) -> TimeSeries:
    """Build a TimeSeries from minute offsets."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    if values is None:
        values = [float(m) for m in minutes]
    return [
        (base + timedelta(minutes=m), v) for m, v in zip(minutes, values, strict=False)
    ]


def _nan_indices(series: TimeSeries) -> list[int]:
    """Return indices of NaN values in a series."""
    return [i for i, (_, v) in enumerate(series) if math.isnan(v)]


class TestInsertGaps:
    def test_no_gaps_regular_data(self) -> None:
        series = _ts([0, 1, 2, 3, 4])
        result = insert_gaps(series)
        assert len(result) == 5
        assert _nan_indices(result) == []

    def test_single_gap(self) -> None:
        series = _ts([0, 1, 2, 10, 11])
        result = insert_gaps(series)
        nans = _nan_indices(result)
        assert len(nans) == 1
        # NaN should be between index 2 (t=2) and the point at t=10
        nan_dt = result[nans[0]][0]
        assert result[nans[0] - 1][0] == series[2][0]  # before gap
        assert result[nans[0] + 1][0] == series[3][0]  # after gap
        # Midpoint of gap
        expected_mid = series[2][0] + (series[3][0] - series[2][0]) / 2
        assert nan_dt == expected_mid

    def test_multiple_gaps(self) -> None:
        series = _ts([0, 1, 2, 10, 11, 12, 20, 21])
        result = insert_gaps(series)
        nans = _nan_indices(result)
        assert len(nans) == 2

    def test_fewer_than_3_points_unchanged(self) -> None:
        series = _ts([0, 1])
        result = insert_gaps(series)
        assert result == series

    def test_single_point_unchanged(self) -> None:
        series = _ts([0])
        result = insert_gaps(series)
        assert result == series

    def test_empty_series(self) -> None:
        result = insert_gaps([])
        assert result == []

    def test_all_same_timestamp(self) -> None:
        series = _ts([0, 0, 0, 0])
        result = insert_gaps(series)
        # Median interval is 0, so no gaps detected
        assert len(result) == 4
        assert _nan_indices(result) == []

    def test_two_points_unchanged(self) -> None:
        series = _ts([0, 100])
        result = insert_gaps(series)
        assert len(result) == 2
        assert _nan_indices(result) == []

    def test_max_gap_filters_small_gaps(self) -> None:
        # Gap of 8 minutes between t=2 and t=10
        series = _ts([0, 1, 2, 10, 11])
        # max_gap=10min means the 8-minute gap should be connected
        result = insert_gaps(series, max_gap=timedelta(minutes=10))
        assert _nan_indices(result) == []

    def test_max_gap_breaks_large_gaps(self) -> None:
        series = _ts([0, 1, 2, 10, 11])
        # max_gap=5min means the 8-minute gap should be broken
        result = insert_gaps(series, max_gap=timedelta(minutes=5))
        assert len(_nan_indices(result)) == 1

    def test_values_preserved(self) -> None:
        series = _ts([0, 1, 2, 3, 4], [10.0, 20.0, 30.0, 40.0, 50.0])
        result = insert_gaps(series)
        non_nan = [(dt, v) for dt, v in result if not math.isnan(v)]
        assert non_nan == series

    def test_returns_new_list(self) -> None:
        series = _ts([0, 1, 2, 3])
        result = insert_gaps(series)
        assert result is not series


class TestValidateGaps:
    def test_connect_accepted(self) -> None:
        assert _validate_gaps("connect") == "connect"

    def test_show_accepted(self) -> None:
        assert _validate_gaps("show") == "show"

    def test_duration_accepted(self) -> None:
        assert _validate_gaps("1h") == "1h"
        assert _validate_gaps("30m") == "30m"
        assert _validate_gaps("2d") == "2d"

    def test_invalid_rejected(self) -> None:
        with pytest.raises(typer.BadParameter):
            _validate_gaps("invalid")

    def test_max_rejected(self) -> None:
        with pytest.raises(typer.BadParameter):
            _validate_gaps("max")


class TestApplyGaps:
    def test_connect_returns_unchanged(self) -> None:
        data = {"A": _ts([0, 1, 2, 10, 11])}
        result = _apply_gaps(data, "connect")
        assert result is data

    def test_show_inserts_nans(self) -> None:
        data = {"A": _ts([0, 1, 2, 10, 11])}
        result = _apply_gaps(data, "show")
        assert len(result["A"]) > len(data["A"])
        assert any(math.isnan(v) for _, v in result["A"])

    def test_duration_filters_by_threshold(self) -> None:
        # Gap of 8 minutes between t=2 and t=10
        data = {"A": _ts([0, 1, 2, 10, 11])}
        # 10m threshold: 8-min gap stays connected
        result = _apply_gaps(data, "10m")
        assert not any(math.isnan(v) for _, v in result["A"])
        # 5m threshold: 8-min gap gets broken
        result = _apply_gaps(data, "5m")
        assert any(math.isnan(v) for _, v in result["A"])


class TestEndToEnd:
    """Integration tests: CSV data → gap processing → render."""

    def test_csv_with_gaps_show(self, tmp_path: pytest.TempPathFactory) -> None:
        """CSV with temporal gap + --gaps show produces NaN in render data."""

        from termseries.csv_source import fetch_csv_series
        from termseries.render import _render_png

        # Create CSV with a gap: 5 points at 1-min intervals, then a 10-min gap
        csv_file = tmp_path / "gapped.csv"
        lines = []
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        for i in range(5):
            dt = base + timedelta(minutes=i)
            lines.append(f"{dt.isoformat()},{100 + i}")
        # Big gap
        for i in range(3):
            dt = base + timedelta(minutes=15 + i)
            lines.append(f"{dt.isoformat()},{200 + i}")
        csv_file.write_text("\n".join(lines))

        data = fetch_csv_series([str(csv_file)], "max")
        data = _apply_gaps(data, "show")

        # Verify NaN was inserted
        series = list(data.values())[0]
        assert any(math.isnan(v) for _, v in series)

        # Verify it renders without error
        png = _render_png(data, (4, 1), "max")
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_csv_with_gaps_duration_threshold(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        """--gaps DURATION: small gap connected, large gap broken."""
        from termseries.csv_source import fetch_csv_series
        from termseries.render import _render_png

        csv_file = tmp_path / "mixed_gaps.csv"
        lines = []
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # Regular points (1-min apart)
        for i in range(5):
            dt = base + timedelta(minutes=i)
            lines.append(f"{dt.isoformat()},{100 + i}")
        # 5-minute gap (small)
        for i in range(3):
            dt = base + timedelta(minutes=10 + i)
            lines.append(f"{dt.isoformat()},{200 + i}")
        # 60-minute gap (large)
        for i in range(3):
            dt = base + timedelta(minutes=72 + i)
            lines.append(f"{dt.isoformat()},{300 + i}")
        csv_file.write_text("\n".join(lines))

        data = fetch_csv_series([str(csv_file)], "max")

        # Threshold of 30m: 5-min gap connected, 60-min gap broken
        result = _apply_gaps(data, "30m")
        series = list(result.values())[0]
        nan_count = sum(1 for _, v in series if math.isnan(v))
        # Only the large gap should be broken
        assert nan_count == 1

        # Renders without error
        png = _render_png(result, (4, 1), "max")
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
