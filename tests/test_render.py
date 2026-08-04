"""Tests for termseries.render functions."""

import math
import warnings
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pytest

from termseries.render import (
    _calendar_divider_locator,
    _display_series_name,
    _legend_layout,
    _output_png,
    _render_png,
    _transform_cumulative,
    _transform_delta,
    _transform_drawdown,
    _transform_indexed,
    _transform_returns,
)
from termseries.terminal import _png_dimensions
from tests.conftest import make_series

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ===================================================================
# _render_png
# ===================================================================


class TestRenderPng:
    def test_calendar_dividers_use_daily_lines_for_week_views(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        locator = _calendar_divider_locator(
            start, start + timedelta(days=7), timezone.utc
        )
        assert isinstance(locator, mdates.DayLocator)
        assert locator.tz is timezone.utc

    def test_calendar_dividers_adapt_to_visible_span(self) -> None:
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert isinstance(
            _calendar_divider_locator(start, start + timedelta(hours=12), timezone.utc),
            mdates.HourLocator,
        )
        assert isinstance(
            _calendar_divider_locator(start, start + timedelta(days=90), timezone.utc),
            mdates.MonthLocator,
        )

    def test_display_series_name_truncates_long_label(self) -> None:
        name = "This is a deliberately long display label that should be truncated"
        assert _display_series_name(name).endswith("...")

    def test_legend_layout_keeps_compact_multi_series_inside(self) -> None:
        assert (
            _legend_layout(
                ["Alpha: Yes", "Beta: Yes", "Gamma: Yes", "Delta: Yes", "Epsilon: Yes"]
            )[0]
            == "inside-left"
        )

    def test_legend_layout_moves_long_labels_outside(self) -> None:
        placement, _cols, _rows = _legend_layout(
            ["This is a very long legend label", "Another very long legend label"] * 3
        )
        assert placement == "outside"

    def test_legend_layout_keeps_single_series_inside(self) -> None:
        assert (
            _legend_layout(["A long but single generic prediction market label: Yes"])[
                0
            ]
            == "inside-top-left"
        )

    def test_returns_valid_png(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d")
        assert png[:8] == PNG_SIGNATURE

    def test_dimensions_match_ratio(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d")
        w, h = _png_dimensions(png)
        assert w > 0 and h > 0
        assert w == 2400  # 12in * 200dpi

    def test_mode_indexed(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", mode="indexed")
        assert png[:8] == PNG_SIGNATURE

    def test_mode_log(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", mode="log")
        assert png[:8] == PNG_SIGNATURE

    def test_mode_drawdown(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", mode="drawdown")
        assert png[:8] == PNG_SIGNATURE

    def test_mode_returns(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", mode="returns")
        assert png[:8] == PNG_SIGNATURE

    @pytest.mark.parametrize("mode", ["indexed", "drawdown", "returns"])
    def test_zero_value_does_not_crash(self, mode: str) -> None:
        """A series that legitimately touches 0 must render, not raise."""
        from datetime import datetime, timezone

        series = {
            "A": [
                (datetime(2024, 1, 1, tzinfo=timezone.utc), 0.0),
                (datetime(2024, 1, 2, tzinfo=timezone.utc), 10.0),
                (datetime(2024, 1, 3, tzinfo=timezone.utc), 20.0),
            ]
        }
        png = _render_png(series, (4, 1), "7d", mode=mode)
        assert png[:8] == PNG_SIGNATURE

    def test_mode_relative(self) -> None:
        series = {"A": make_series(base=100), "B": make_series(base=50)}
        png = _render_png(series, (4, 1), "7d", mode="relative")
        assert png[:8] == PNG_SIGNATURE

    def test_mode_cumulative(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", mode="cumulative")
        assert png[:8] == PNG_SIGNATURE

    def test_mode_delta(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", mode="delta")
        assert png[:8] == PNG_SIGNATURE

    def test_relative_wrong_count(self) -> None:
        series = {"A": make_series()}
        with pytest.raises(ValueError, match="exactly 2"):
            _render_png(series, (4, 1), "7d", mode="relative")

    def test_relative_wrong_count_does_not_leak_figure(self) -> None:
        """A validation error after fig creation must still close the figure."""
        series = {"A": make_series()}
        open_before = len(plt.get_fignums())
        with pytest.raises(ValueError, match="exactly 2"):
            _render_png(series, (4, 1), "7d", mode="relative")
        assert len(plt.get_fignums()) == open_before

    def test_relative_no_overlap_does_not_leak_figure(self) -> None:
        from datetime import datetime, timezone

        series_a = [(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0)]
        series_b = [(datetime(2020, 1, 1, tzinfo=timezone.utc), 200.0)]
        open_before = len(plt.get_fignums())
        with pytest.raises(RuntimeError, match="No overlapping dates"):
            _render_png({"A": series_a, "B": series_b}, (4, 1), "7d", mode="relative")
        assert len(plt.get_fignums()) == open_before

    def test_empty_series(self) -> None:
        with pytest.raises(ValueError, match="No data"):
            _render_png({}, (4, 1), "7d")

    def test_multiple_series(self) -> None:
        series = {"X": make_series(base=10), "Y": make_series(base=200)}
        png = _render_png(series, (4, 1), "7d")
        assert png[:8] == PNG_SIGNATURE

    def test_many_long_series_do_not_emit_layout_warning(self) -> None:
        series = {
            (
                "candidate-alpha-with-a-very-long-generic-election-market-label:Yes"
            ): make_series(base=10),
            (
                "candidate-beta-with-a-very-long-generic-election-market-label:Yes"
            ): make_series(base=20),
            (
                "candidate-gamma-with-a-very-long-generic-election-market-label:Yes"
            ): make_series(base=30),
            (
                "candidate-delta-with-a-very-long-generic-election-market-label:Yes"
            ): make_series(base=40),
            (
                "candidate-epsilon-with-a-very-long-generic-election-market-label:Yes"
            ): make_series(base=50),
        }
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            png = _render_png(series, (4, 1), "30d")
        assert png[:8] == PNG_SIGNATURE
        assert not any("layout" in str(w.message).lower() for w in record)

    def test_custom_figsize(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", figsize=(8.0, 4.0))
        w, h = _png_dimensions(png)
        assert w == 1600  # 8in * 200dpi
        assert h == 800  # 4in * 200dpi

    def test_color_cycle(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", color_cycle="Dark2")
        assert png[:8] == PNG_SIGNATURE

    def test_value_unit(self) -> None:
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", value_unit="C")
        assert png[:8] == PNG_SIGNATURE


# ===================================================================
# _output_png -- dispatch logic
# ===================================================================


@pytest.mark.usefixtures("_clean_env")
class TestOutputPng:
    def test_kitty_dispatch(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TERM", "xterm-kitty")
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._print_kitty_png") as mock,
        ):
            _output_png(small_png, ["A"], (4, 1), "7d")
        mock.assert_called_once_with(small_png)

    def test_iterm2_dispatch(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._print_iterm2_png") as mock,
        ):
            _output_png(small_png, ["A"], (4, 1), "7d")
        mock.assert_called_once_with(small_png)

    def test_sixel_dispatch(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "WezTerm")
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._print_sixel_png") as mock,
        ):
            _output_png(small_png, ["A"], (4, 1), "7d")
        mock.assert_called_once_with(small_png)

    def test_explicit_sixel_protocol_bypasses_auto_detection(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--output inline --protocol sixel is the escape hatch for terminals
        (e.g. a Sixel-patched xterm build) that auto-detection can't
        recognize -- unlike output="auto", output="inline" always honors an
        explicit protocol without gating on auto-detection first."""
        monkeypatch.setenv("TERM", "xterm")  # auto-detection alone says False
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._print_sixel_png") as mock,
        ):
            _output_png(
                small_png, ["A"], (4, 1), "7d", output="inline", protocol="sixel"
            )
        mock.assert_called_once_with(small_png)

    def test_fallback_writes_file(
        self,
        small_png: bytes,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _output_png(small_png, ["AAPL", "MSFT"], (16, 9), "1mo")
        written = tmp_path / "termseries_AAPL-MSFT_1mo_16x9.png"
        assert written.exists()
        assert written.read_bytes() == small_png

    def test_named_output_bad_path_raises_runtime_error(self, small_png: bytes) -> None:
        """A named output path whose parent directory doesn't exist must
        raise a clean RuntimeError, not a raw FileNotFoundError."""
        with pytest.raises(RuntimeError, match="Could not write to"):
            _output_png(small_png, ["A"], (4, 1), "7d", output="/no/such/dir/out.png")

    def test_cascade_kitty_before_iterm2(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both Kitty and iTerm2 env vars are set, Kitty wins."""
        monkeypatch.setenv("TERM", "xterm-kitty")
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._print_kitty_png") as kitty_mock,
            patch("termseries.render._print_iterm2_png") as iterm_mock,
        ):
            _output_png(small_png, ["A"], (4, 1), "7d")
        kitty_mock.assert_called_once()
        iterm_mock.assert_not_called()

    def test_cascade_iterm2_before_sixel(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both iTerm2 and Sixel env vars are set, iTerm2 wins."""
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        monkeypatch.setenv("TERM", "foot")
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._print_iterm2_png") as iterm_mock,
            patch("termseries.render._print_sixel_png") as sixel_mock,
        ):
            _output_png(small_png, ["A"], (4, 1), "7d")
        iterm_mock.assert_called_once()
        sixel_mock.assert_not_called()

    def test_many_tickers_filename(
        self,
        small_png: bytes,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Filenames with >6 tickers get truncated with a 'plus' suffix."""
        monkeypatch.chdir(tmp_path)
        tickers = ["A", "B", "C", "D", "E", "F", "G", "H"]
        _output_png(small_png, tickers, (4, 1), "7d")
        written = tmp_path / "termseries_A-B-C-D-E-F-plus2_7d_4x1.png"
        assert written.exists()

    def test_long_series_names_filename_is_shortened(
        self,
        small_png: bytes,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Very long series names are shortened to avoid OS filename limits."""
        monkeypatch.chdir(tmp_path)
        names = [
            "VERY-LONG-GENERIC-PREDICTION-MARKET-LABEL-FOR-CANDIDATE-ALPHA-WITH-EXTRA-DESCRIPTIVE-TEXT:YES",
            "VERY-LONG-GENERIC-PREDICTION-MARKET-LABEL-FOR-CANDIDATE-BETA-WITH-EXTRA-DESCRIPTIVE-TEXT:YES",
            "VERY-LONG-GENERIC-PREDICTION-MARKET-LABEL-FOR-CANDIDATE-GAMMA-WITH-EXTRA-DESCRIPTIVE-TEXT:YES",
            "VERY-LONG-GENERIC-PREDICTION-MARKET-LABEL-FOR-CANDIDATE-DELTA-WITH-EXTRA-DESCRIPTIVE-TEXT:YES",
            "VERY-LONG-GENERIC-PREDICTION-MARKET-LABEL-FOR-CANDIDATE-EPSILON-WITH-EXTRA-DESCRIPTIVE-TEXT:YES",
            "VERY-LONG-GENERIC-PREDICTION-MARKET-LABEL-FOR-CANDIDATE-ZETA-WITH-EXTRA-DESCRIPTIVE-TEXT:YES",
            "VERY-LONG-GENERIC-PREDICTION-MARKET-LABEL-FOR-CANDIDATE-ETA-WITH-EXTRA-DESCRIPTIVE-TEXT:YES",
        ]
        _output_png(small_png, names, (4, 1), "30d")
        written = next(tmp_path.glob("termseries_*_30d_4x1.png"))
        assert written.exists()
        assert len(written.name) < 180


# ===================================================================
# Style files
# ===================================================================


class TestStyleFiles:
    def test_dark_style_loadable(self) -> None:
        plt.style.use("termseries.dark")

    def test_light_style_loadable(self) -> None:
        plt.style.use("termseries.light")

    def test_dark_sets_black_facecolor(self) -> None:
        with plt.style.context("termseries.dark"):
            assert plt.rcParams["figure.facecolor"] == "black"

    def test_light_sets_white_facecolor(self) -> None:
        with plt.style.context("termseries.light"):
            assert plt.rcParams["figure.facecolor"] == "white"

    def test_style_sets_dpi(self) -> None:
        with plt.style.context("termseries.dark"):
            assert plt.rcParams["figure.dpi"] == 200

    def test_style_override(self, tmp_path: pytest.TempPathFactory) -> None:
        override = tmp_path / "custom.mplstyle"
        override.write_text("figure.dpi: 100\n")
        series = {"A": make_series()}
        png = _render_png(series, (4, 1), "7d", style_override=override)
        from termseries.terminal import _png_dimensions

        w, _h = _png_dimensions(png)
        assert w == 1200  # 12in * 100dpi


# ===================================================================
# Transform functions
# ===================================================================


class TestTransforms:
    def test_indexed(self) -> None:
        xs = [1, 2, 3]
        _, ys = _transform_indexed(xs, [50, 75, 100])
        assert ys == [100.0, 150.0, 200.0]

    def test_indexed_empty(self) -> None:
        xs, ys = _transform_indexed([], [])
        assert xs == [] and ys == []

    def test_drawdown(self) -> None:
        xs = [1, 2, 3]
        _, ys = _transform_drawdown(xs, [100, 80, 90])
        assert ys == pytest.approx([0.0, -20.0, -10.0])

    def test_drawdown_empty(self) -> None:
        xs, ys = _transform_drawdown([], [])
        assert xs == [] and ys == []

    def test_returns(self) -> None:
        xs = [1, 2, 3]
        rx, ry = _transform_returns(xs, [100, 110, 99])
        assert rx == [2, 3]
        assert ry == pytest.approx([10.0, -10.0])

    def test_returns_empty(self) -> None:
        xs, ys = _transform_returns([], [])
        assert xs == [] and ys == []

    def test_returns_single(self) -> None:
        xs, ys = _transform_returns([1], [100])
        assert xs == [1] and ys == [100]

    def test_cumulative(self) -> None:
        xs = [1, 2, 3]
        _, ys = _transform_cumulative(xs, [10, 20, 30])
        assert ys == [10, 30, 60]

    def test_cumulative_empty(self) -> None:
        xs, ys = _transform_cumulative([], [])
        assert xs == [] and ys == []

    def test_delta(self) -> None:
        xs = [1, 2, 3]
        dx, dy = _transform_delta(xs, [100, 110, 105])
        assert dx == [2, 3]
        assert dy == [10, -5]

    def test_delta_empty(self) -> None:
        xs, ys = _transform_delta([], [])
        assert xs == [] and ys == []

    def test_delta_single(self) -> None:
        xs, ys = _transform_delta([1], [100])
        assert xs == [1] and ys == [100]

    # --- NaN propagation tests ---

    def test_indexed_nan_propagates(self) -> None:
        _, ys = _transform_indexed([1, 2, 3], [50, float("nan"), 100])
        assert ys[0] == 100.0
        assert math.isnan(ys[1])
        assert ys[2] == 200.0

    def test_returns_nan_propagates(self) -> None:
        _, ys = _transform_returns([1, 2, 3], [100, float("nan"), 110])
        assert math.isnan(ys[0])  # nan / 100
        assert math.isnan(ys[1])  # 110 / nan

    def test_delta_nan_propagates(self) -> None:
        _, ys = _transform_delta([1, 2, 3], [100, float("nan"), 110])
        assert math.isnan(ys[0])  # nan - 100
        assert math.isnan(ys[1])  # 110 - nan

    def test_drawdown_nan_skipped(self) -> None:
        _, ys = _transform_drawdown([1, 2, 3, 4], [100, float("nan"), 80, 90])
        assert ys[0] == pytest.approx(0.0)
        assert math.isnan(ys[1])
        assert ys[2] == pytest.approx(-20.0)  # peak stays at 100
        assert ys[3] == pytest.approx(-10.0)

    # --- zero-division guards (a legitimate 0 reading must not crash) ---

    def test_indexed_zero_base_yields_nan_not_crash(self) -> None:
        _, ys = _transform_indexed([1, 2, 3], [0, 10, 20])
        assert all(math.isnan(y) for y in ys)

    def test_drawdown_zero_peak_yields_nan_not_crash(self) -> None:
        _, ys = _transform_drawdown([1, 2, 3], [0, 0, 5])
        assert math.isnan(ys[0])
        assert math.isnan(ys[1])
        assert ys[2] == pytest.approx(0.0)  # peak became 5, at peak

    def test_returns_zero_prev_yields_nan_not_crash(self) -> None:
        _, ys = _transform_returns([1, 2, 3], [0, 10, 20])
        assert math.isnan(ys[0])  # 10 / 0
        assert ys[1] == pytest.approx(100.0)  # 20 / 10

    def test_cumulative_nan_skipped(self) -> None:
        _, ys = _transform_cumulative([1, 2, 3, 4], [10, float("nan"), 20, 30])
        assert ys[0] == 10
        assert math.isnan(ys[1])
        assert ys[2] == 30  # 10 + 20, NaN skipped
        assert ys[3] == 60  # 10 + 20 + 30
