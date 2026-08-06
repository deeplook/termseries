"""Tests for termseries.seasonal module."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from termseries.cli import app
from termseries.seasonal import REFERENCE_YEAR, count_cycles, parse_cycle, wrap_series
from termseries.types import TimeSeries

runner = CliRunner()
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 25


def _daily(start: datetime, days: int, values: list[float] | None = None) -> TimeSeries:
    if values is None:
        values = [float(i) for i in range(days)]
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


class TestParseCycle:
    def test_year(self) -> None:
        assert parse_cycle("year") == ("year", None)

    def test_quarter(self) -> None:
        assert parse_cycle("quarter") == ("quarter", None)

    def test_duration(self) -> None:
        spec = parse_cycle("90d")
        assert spec.kind == "duration"
        assert spec.duration_seconds == pytest.approx(90 * 86400)

    def test_duration_weeks(self) -> None:
        spec = parse_cycle("4w")
        assert spec.kind == "duration"
        assert spec.duration_seconds == pytest.approx(4 * 7 * 86400)

    def test_invalid_unit_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid cycle"):
            parse_cycle("month")

    def test_max_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid cycle"):
            parse_cycle("max")

    def test_zero_duration_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid cycle"):
            parse_cycle("0d")

    def test_garbage_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid cycle"):
            parse_cycle("not-a-cycle")


class TestReferenceYear:
    def test_reference_year_is_leap(self) -> None:
        assert calendar.isleap(REFERENCE_YEAR)


class TestWrapSeriesYear:
    def test_splits_by_calendar_year(self) -> None:
        series = _daily(datetime(2022, 1, 1, tzinfo=timezone.utc), 3 * 365 + 1)
        data = {"NAME": series}
        result = wrap_series(data, "year", tz=timezone.utc)
        assert set(result.keys()) == {
            "NAME (2022)",
            "NAME (2023)",
            "NAME (2024)",
        }

    def test_keys_grouped_and_chronological(self) -> None:
        series = _daily(datetime(2022, 6, 1, tzinfo=timezone.utc), 400)
        data = {"NAME": series}
        result = wrap_series(data, "year", tz=timezone.utc)
        assert list(result.keys()) == ["NAME (2022)", "NAME (2023)"]

    def test_values_preserved(self) -> None:
        series = _daily(
            datetime(2023, 1, 1, tzinfo=timezone.utc), 5, [10.0, 20.0, 30.0, 40.0, 50.0]
        )
        data = {"NAME": series}
        result = wrap_series(data, "year", tz=timezone.utc)
        values = [v for _, v in result["NAME (2023)"]]
        assert values == [10.0, 20.0, 30.0, 40.0, 50.0]

    def test_points_projected_onto_reference_year(self) -> None:
        series = _daily(datetime(2023, 3, 15, tzinfo=timezone.utc), 1)
        data = {"NAME": series}
        result = wrap_series(data, "year", tz=timezone.utc)
        dt, _ = result["NAME (2023)"][0]
        assert dt.year == REFERENCE_YEAR
        assert dt.month == 3
        assert dt.day == 15

    def test_leap_day_maps_cleanly(self) -> None:
        series = [(datetime(2024, 2, 29, tzinfo=timezone.utc), 1.0)]
        data = {"NAME": series}
        result = wrap_series(data, "year", tz=timezone.utc)
        dt, _ = result["NAME (2024)"][0]
        assert (dt.month, dt.day) == (2, 29)

    def test_non_leap_year_month_day_unaffected_by_leap_reference(self) -> None:
        # A date in a non-leap source year must map to the *same* month/day
        # in the (leap) reference year -- no elapsed-day drift.
        series = [(datetime(2023, 6, 15, tzinfo=timezone.utc), 1.0)]
        data = {"NAME": series}
        result = wrap_series(data, "year", tz=timezone.utc)
        dt, _ = result["NAME (2023)"][0]
        assert (dt.month, dt.day) == (6, 15)

    def test_empty_series_passthrough(self) -> None:
        data: dict[str, TimeSeries] = {"NAME": []}
        result = wrap_series(data, "year", tz=timezone.utc)
        assert result == {"NAME": []}

    def test_empty_data(self) -> None:
        assert wrap_series({}, "year", tz=timezone.utc) == {}

    def test_multi_series(self) -> None:
        series_a = _daily(datetime(2022, 1, 1, tzinfo=timezone.utc), 3 * 365 + 1)
        series_b = _daily(datetime(2022, 1, 1, tzinfo=timezone.utc), 3 * 365 + 1)
        data = {"AAA": series_a, "BBB": series_b}
        result = wrap_series(data, "year", tz=timezone.utc)
        assert len(result) == 6
        assert all(name.startswith(("AAA (", "BBB (")) for name in result)

    def test_cycle_longer_than_span_yields_one_chunk(self) -> None:
        series = _daily(datetime(2023, 1, 1, tzinfo=timezone.utc), 10)
        data = {"NAME": series}
        result = wrap_series(data, "year", tz=timezone.utc)
        assert list(result.keys()) == ["NAME (2023)"]


class TestWrapSeriesQuarter:
    def test_splits_across_year_boundary(self) -> None:
        series = _daily(datetime(2023, 11, 1, tzinfo=timezone.utc), 90)
        data = {"NAME": series}
        result = wrap_series(data, "quarter", tz=timezone.utc)
        assert set(result.keys()) == {
            "NAME (2023 Q4)",
            "NAME (2024 Q1)",
        }

    def test_calendar_aligned_quarters(self) -> None:
        series = [
            (datetime(2023, 1, 1, tzinfo=timezone.utc), 1.0),
            (datetime(2023, 4, 1, tzinfo=timezone.utc), 2.0),
            (datetime(2023, 7, 1, tzinfo=timezone.utc), 3.0),
            (datetime(2023, 10, 1, tzinfo=timezone.utc), 4.0),
        ]
        data = {"NAME": series}
        result = wrap_series(data, "quarter", tz=timezone.utc)
        assert set(result.keys()) == {
            "NAME (2023 Q1)",
            "NAME (2023 Q2)",
            "NAME (2023 Q3)",
            "NAME (2023 Q4)",
        }

    def test_all_quarters_overlay_onto_single_reference_window(self) -> None:
        """Every quarter should land in the same Jan-Mar reference window,
        not spread across the full reference year by real calendar month."""
        series = [
            (datetime(2023, 1, 15, tzinfo=timezone.utc), 1.0),  # Q1
            (datetime(2023, 4, 15, tzinfo=timezone.utc), 2.0),  # Q2
            (datetime(2023, 7, 15, tzinfo=timezone.utc), 3.0),  # Q3
            (datetime(2023, 10, 15, tzinfo=timezone.utc), 4.0),  # Q4
        ]
        data = {"NAME": series}
        result = wrap_series(data, "quarter", tz=timezone.utc)
        for key, points in result.items():
            (dt, _value) = points[0]
            assert dt.year == REFERENCE_YEAR
            assert dt.month in (1, 2, 3), f"{key} landed outside Jan-Mar: {dt}"

    def test_quarter_day_offset_preserved(self) -> None:
        # 15th day into the quarter (day-of-quarter, not day-of-month) should
        # land on the 15th day of the reference window for every quarter.
        series = [
            (datetime(2023, 1, 15, tzinfo=timezone.utc), 1.0),  # Q1, day 15
            (datetime(2023, 4, 15, tzinfo=timezone.utc), 2.0),  # Q2, day 15
        ]
        data = {"NAME": series}
        result = wrap_series(data, "quarter", tz=timezone.utc)
        dt_q1, _ = result["NAME (2023 Q1)"][0]
        dt_q2, _ = result["NAME (2023 Q2)"][0]
        assert (dt_q1.month, dt_q1.day) == (1, 15)
        assert (dt_q2.month, dt_q2.day) == (1, 15)


class TestWrapSeriesDuration:
    def test_chunk_count_and_labels(self) -> None:
        series = _daily(datetime(2023, 1, 1, tzinfo=timezone.utc), 200)
        data = {"NAME": series}
        result = wrap_series(data, "90d", tz=timezone.utc)
        assert list(result.keys()) == [
            "NAME (chunk 1)",
            "NAME (chunk 2)",
            "NAME (chunk 3)",
        ]

    def test_trailing_partial_chunk_kept(self) -> None:
        series = _daily(datetime(2023, 1, 1, tzinfo=timezone.utc), 100)
        data = {"NAME": series}
        result = wrap_series(data, "90d", tz=timezone.utc)
        # 100 days / 90d cycle -> chunk 1 (90 pts), chunk 2 (10 pts, partial)
        assert len(result["NAME (chunk 1)"]) == 90
        assert len(result["NAME (chunk 2)"]) == 10

    def test_chunk_label_ordering_numeric_not_alphabetic(self) -> None:
        series = _daily(datetime(2023, 1, 1, tzinfo=timezone.utc), 12 * 90)
        data = {"NAME": series}
        result = wrap_series(data, "90d", tz=timezone.utc)
        keys = list(result.keys())
        assert keys.index("NAME (chunk 2)") < keys.index("NAME (chunk 10)")


class TestWrapSeriesWeek:
    def test_calendar_aligned_to_monday(self) -> None:
        # 2023-01-01 is a Sunday; 2023-01-02 is the following Monday.
        series = _daily(datetime(2023, 1, 1, tzinfo=timezone.utc), 15)
        data = {"NAME": series}
        result = wrap_series(data, "1w", tz=timezone.utc)
        assert set(result.keys()) == {
            "NAME (2022-W52)",
            "NAME (2023-W01)",
            "NAME (2023-W02)",
        }

    def test_7d_and_1w_are_equivalent(self) -> None:
        series = _daily(datetime(2023, 1, 2, tzinfo=timezone.utc), 14)
        data = {"NAME": series}
        result_1w = wrap_series(data, "1w", tz=timezone.utc)
        result_7d = wrap_series(data, "7d", tz=timezone.utc)
        assert set(result_1w.keys()) == set(result_7d.keys())

    def test_week_start_lands_on_reference_monday(self) -> None:
        # 2023-01-02 is a Monday -> should be the first point in its week.
        series = _daily(datetime(2023, 1, 2, tzinfo=timezone.utc), 7)
        data = {"NAME": series}
        result = wrap_series(data, "1w", tz=timezone.utc)
        dt, _ = result["NAME (2023-W01)"][0]
        assert dt.year == REFERENCE_YEAR
        assert dt.month == 1
        assert dt.day == 1  # elapsed offset 0 within the reference window

    def test_weeks_chain_across_month_boundary(self) -> None:
        series = _daily(datetime(2023, 1, 2, tzinfo=timezone.utc), 21)
        data = {"NAME": series}
        result = wrap_series(data, "1w", tz=timezone.utc)
        assert set(result.keys()) == {
            "NAME (2023-W01)",
            "NAME (2023-W02)",
            "NAME (2023-W03)",
        }
        for points in result.values():
            for dt, _ in points:
                assert dt.year == REFERENCE_YEAR
                assert dt.month == 1
                assert 1 <= dt.day <= 7


class TestCountCycles:
    def test_matches_number_of_wrapped_chunks_single_series(self) -> None:
        series = _daily(datetime(2022, 1, 1, tzinfo=timezone.utc), 3 * 365 + 1)
        data = {"NAME": series}
        assert count_cycles(data, "year", tz=timezone.utc) == len(
            wrap_series(data, "year", tz=timezone.utc)
        )

    def test_counts_union_across_multiple_series_not_total_keys(self) -> None:
        # Same date range for both series -> same 3 years, not 6.
        series_a = _daily(datetime(2022, 1, 1, tzinfo=timezone.utc), 3 * 365 + 1)
        series_b = _daily(datetime(2022, 1, 1, tzinfo=timezone.utc), 3 * 365 + 1)
        data = {"AAA": series_a, "BBB": series_b}
        assert count_cycles(data, "year", tz=timezone.utc) == 3
        assert len(wrap_series(data, "year", tz=timezone.utc)) == 6

    def test_counts_weeks(self) -> None:
        series = _daily(datetime(2023, 1, 2, tzinfo=timezone.utc), 21)
        data = {"NAME": series}
        assert count_cycles(data, "1w", tz=timezone.utc) == 3

    def test_counts_quarters(self) -> None:
        series = _daily(datetime(2023, 11, 1, tzinfo=timezone.utc), 90)
        data = {"NAME": series}
        assert count_cycles(data, "quarter", tz=timezone.utc) == 2

    def test_empty_data_is_zero(self) -> None:
        assert count_cycles({}, "year", tz=timezone.utc) == 0

    def test_empty_series_is_zero(self) -> None:
        assert count_cycles({"NAME": []}, "year", tz=timezone.utc) == 0


class TestCLI:
    def _multi_year_data(self) -> dict[str, TimeSeries]:
        return {"NAME": _daily(datetime(2022, 1, 1, tzinfo=timezone.utc), 3 * 365)}

    def test_cycle_without_seasonal_mode_rejected(self) -> None:
        result = runner.invoke(app, ["--cycle", "year", "yahoo", "FAKE"])
        assert result.exit_code != 0

    def test_seasonal_mode_defaults_cycle_to_year(self) -> None:
        captured: dict[str, object] = {}

        def mock_render(
            data: dict[str, TimeSeries], *args: object, **kwargs: object
        ) -> bytes:
            captured["keys"] = set(data.keys())
            return _FAKE_PNG

        with (
            patch(
                "termseries.cli.fetch_yahoo_series",
                return_value=self._multi_year_data(),
            ),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["--mode", "seasonal", "yahoo", "NAME"])

        assert result.exit_code == 0, _plain_output(result.output)
        assert captured["keys"] == {"NAME (2022)", "NAME (2023)", "NAME (2024)"}

    def test_seasonal_mode_with_explicit_cycle(self) -> None:
        captured: dict[str, object] = {}

        def mock_render(
            data: dict[str, TimeSeries], *args: object, **kwargs: object
        ) -> bytes:
            captured["keys"] = set(data.keys())
            return _FAKE_PNG

        with (
            patch(
                "termseries.cli.fetch_yahoo_series",
                return_value=self._multi_year_data(),
            ),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(
                app, ["--mode", "seasonal", "--cycle", "quarter", "yahoo", "NAME"]
            )

        assert result.exit_code == 0, _plain_output(result.output)
        keys = captured["keys"]
        assert isinstance(keys, set)
        assert keys
        assert all(" Q" in key for key in keys)

    def test_seasonal_mode_invalid_cycle_rejected(self) -> None:
        result = runner.invoke(
            app, ["--mode", "seasonal", "--cycle", "bogus", "yahoo", "FAKE"]
        )
        assert result.exit_code != 0

    def test_seasonal_mode_interactive_launches_tui_with_cycle(self) -> None:
        with (
            patch("termseries.cli._run_interactive") as run_tui,
            patch(
                "termseries.cli.fetch_yahoo_series",
                return_value=self._multi_year_data(),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "--mode",
                    "seasonal",
                    "--cycle",
                    "quarter",
                    "--interactive",
                    "yahoo",
                    "NAME",
                ],
            )
        assert result.exit_code == 0, _plain_output(result.output)
        run_tui.assert_called_once()
        assert run_tui.call_args.kwargs["mode"] == "seasonal"
        assert run_tui.call_args.kwargs["cycle"] == "quarter"

    def test_cycle_longer_than_span_warns(self) -> None:
        short_data = {"NAME": _daily(datetime(2023, 1, 1, tzinfo=timezone.utc), 10)}
        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=short_data),
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["--mode", "seasonal", "yahoo", "NAME"])

        assert result.exit_code == 0
        assert "only one chunk was produced" in result.output


def _plain_output(output: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", output)
