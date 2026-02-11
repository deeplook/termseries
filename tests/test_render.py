"""Tests for termseries._render functions."""

from unittest.mock import patch

import matplotlib.pyplot as plt
import pytest

from termseries._render import _output_png, _render_png
from termseries._terminal import _png_dimensions
from tests.conftest import make_series

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ===================================================================
# _render_png
# ===================================================================


class TestRenderPng:
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

    def test_mode_relative(self) -> None:
        series = {"A": make_series(base=100), "B": make_series(base=50)}
        png = _render_png(series, (4, 1), "7d", mode="relative")
        assert png[:8] == PNG_SIGNATURE

    def test_relative_wrong_count(self) -> None:
        series = {"A": make_series()}
        with pytest.raises(ValueError, match="exactly 2"):
            _render_png(series, (4, 1), "7d", mode="relative")

    def test_empty_series(self) -> None:
        with pytest.raises(ValueError, match="No data"):
            _render_png({}, (4, 1), "7d")

    def test_multiple_series(self) -> None:
        series = {"X": make_series(base=10), "Y": make_series(base=200)}
        png = _render_png(series, (4, 1), "7d")
        assert png[:8] == PNG_SIGNATURE

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
        with patch("termseries._render._print_kitty_png") as mock:
            _output_png(small_png, ["A"], (4, 1), "7d")
        mock.assert_called_once_with(small_png)

    def test_iterm2_dispatch(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        with patch("termseries._render._print_iterm2_png") as mock:
            _output_png(small_png, ["A"], (4, 1), "7d")
        mock.assert_called_once_with(small_png)

    def test_sixel_dispatch(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "WezTerm")
        with patch("termseries._render._print_sixel_png") as mock:
            _output_png(small_png, ["A"], (4, 1), "7d")
        mock.assert_called_once_with(small_png)

    def test_force_inline_falls_back_to_iterm2(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TERMSERIES_FORCE_INLINE", "1")
        with patch("termseries._render._print_iterm2_png") as mock:
            _output_png(small_png, ["A"], (4, 1), "7d")
        mock.assert_called_once_with(small_png)

    def test_no_inline_writes_file(
        self,
        small_png: bytes,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        monkeypatch.setenv("TERMSERIES_NO_INLINE", "1")
        monkeypatch.setenv("TERM", "xterm-kitty")
        monkeypatch.chdir(tmp_path)
        _output_png(small_png, ["TSLA"], (4, 1), "7d")
        written = tmp_path / "termseries_TSLA_7d_4x1.png"
        assert written.exists()
        assert written.read_bytes() == small_png

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

    def test_cascade_kitty_before_iterm2(
        self, small_png: bytes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both Kitty and iTerm2 env vars are set, Kitty wins."""
        monkeypatch.setenv("TERM", "xterm-kitty")
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        with (
            patch("termseries._render._print_kitty_png") as kitty_mock,
            patch("termseries._render._print_iterm2_png") as iterm_mock,
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
            patch("termseries._render._print_iterm2_png") as iterm_mock,
            patch("termseries._render._print_sixel_png") as sixel_mock,
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
        from termseries._terminal import _png_dimensions

        w, _h = _png_dimensions(png)
        assert w == 1200  # 12in * 100dpi
