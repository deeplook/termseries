"""Tests for termseries helper functions (no network access required)."""

import base64
import struct
from unittest.mock import patch

import pytest
import typer

from termseries import (
    _detect_dark_terminal,
    _is_iterm2,
    _is_kitty,
    _is_sixel_terminal,
    _is_ssh_session,
    _output_png,
    _parse_ratio,
    _png_dimensions,
    _print_iterm2_png,
    _print_kitty_png,
    _print_sixel_png,
    _render_png,
)
from tests.conftest import make_series

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# ===================================================================
# _is_kitty
# ===================================================================


@pytest.mark.usefixtures("_clean_env")
class TestIsKitty:
    def test_xterm_kitty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm-kitty")
        assert _is_kitty() is True

    def test_term_program_kitty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "kitty")
        assert _is_kitty() is True

    def test_neither(self) -> None:
        assert _is_kitty() is False

    def test_other_term(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm-256color")
        assert _is_kitty() is False

    def test_xterm_kitty_suffix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm-kitty-direct")
        assert _is_kitty() is True


# ===================================================================
# _is_iterm2
# ===================================================================


@pytest.mark.usefixtures("_clean_env")
class TestIsIterm2:
    def test_term_program(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        assert _is_iterm2() is True

    def test_lc_terminal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LC_TERMINAL", "iTerm2")
        assert _is_iterm2() is True

    def test_session_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ITERM_SESSION_ID", "w0t0p0:GUID")
        assert _is_iterm2() is True

    def test_none(self) -> None:
        assert _is_iterm2() is False


# ===================================================================
# _is_sixel_terminal
# ===================================================================


@pytest.mark.usefixtures("_clean_env")
class TestIsSixelTerminal:
    def test_wezterm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "WezTerm")
        assert _is_sixel_terminal() is True

    def test_vscode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM_PROGRAM", "vscode")
        assert _is_sixel_terminal() is True

    def test_foot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "foot")
        assert _is_sixel_terminal() is True

    def test_foot_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "foot-extra")
        assert _is_sixel_terminal() is True

    def test_mlterm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "mlterm")
        assert _is_sixel_terminal() is True

    def test_xterm_exact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm")
        assert _is_sixel_terminal() is True

    def test_xterm_256color_not_matched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERM", "xterm-256color")
        assert _is_sixel_terminal() is False

    def test_none(self) -> None:
        assert _is_sixel_terminal() is False


# ===================================================================
# _is_ssh_session
# ===================================================================


@pytest.mark.usefixtures("_clean_env")
class TestIsSshSession:
    def test_ssh_connection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 12345 5.6.7.8 22")
        assert _is_ssh_session() is True

    def test_ssh_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SSH_CLIENT", "1.2.3.4 12345 22")
        assert _is_ssh_session() is True

    def test_no_ssh(self) -> None:
        assert _is_ssh_session() is False


# ===================================================================
# _detect_dark_terminal
# ===================================================================


@pytest.mark.usefixtures("_clean_env")
class TestDetectDarkTerminal:
    def test_force_dark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERMSERIES_DARK", "1")
        assert _detect_dark_terminal() is True

    def test_force_light(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERMSERIES_LIGHT", "1")
        assert _detect_dark_terminal() is False

    def test_dark_overrides_light(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TERMSERIES_DARK", "1")
        monkeypatch.setenv("TERMSERIES_LIGHT", "1")
        assert _detect_dark_terminal() is True

    def test_colorfgbg_dark_bg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "15;0")
        assert _detect_dark_terminal() is True

    def test_colorfgbg_light_bg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "0;15")
        assert _detect_dark_terminal() is False

    def test_colorfgbg_three_parts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "15;0;0")
        assert _detect_dark_terminal() is True

    def test_colorfgbg_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "garbage")
        assert _detect_dark_terminal() is True

    def test_iterm_profile_dark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ITERM_PROFILE", "Solarized Dark")
        assert _detect_dark_terminal() is True

    def test_iterm_profile_light(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ITERM_PROFILE", "Solarized Light")
        assert _detect_dark_terminal() is False

    def test_default_is_dark(self) -> None:
        assert _detect_dark_terminal() is True


# ===================================================================
# _parse_ratio
# ===================================================================


class TestParseRatio:
    def test_basic(self) -> None:
        assert _parse_ratio("4:1") == (4, 1)

    def test_larger(self) -> None:
        assert _parse_ratio("16:10") == (16, 10)

    def test_whitespace(self) -> None:
        assert _parse_ratio("  4 : 1  ") == (4, 1)

    def test_not_enough_parts(self) -> None:
        with pytest.raises(typer.BadParameter):
            _parse_ratio("4")

    def test_too_many_parts(self) -> None:
        with pytest.raises(typer.BadParameter):
            _parse_ratio("4:1:2")

    def test_empty_parts(self) -> None:
        with pytest.raises(typer.BadParameter):
            _parse_ratio(":")

    def test_non_integer(self) -> None:
        with pytest.raises(typer.BadParameter):
            _parse_ratio("4.5:1")

    def test_zero_width(self) -> None:
        with pytest.raises(typer.BadParameter):
            _parse_ratio("0:1")

    def test_negative(self) -> None:
        with pytest.raises(typer.BadParameter):
            _parse_ratio("-1:5")

    def test_letters(self) -> None:
        with pytest.raises(typer.BadParameter):
            _parse_ratio("a:b")


# ===================================================================
# _png_dimensions
# ===================================================================


class TestPngDimensions:
    def test_small_png(self, small_png: bytes) -> None:
        assert _png_dimensions(small_png) == (2, 3)

    def test_large_png(self, large_png: bytes) -> None:
        assert _png_dimensions(large_png) == (200, 200)

    def test_manual_ihdr(self) -> None:
        header = PNG_SIGNATURE + b"\x00\x00\x00\rIHDR"
        header += struct.pack(">II", 640, 480)
        header += b"\x08\x02\x00\x00\x00"
        assert _png_dimensions(header) == (640, 480)


# ===================================================================
# _print_iterm2_png
# ===================================================================


class TestPrintIterm2Png:
    def test_format(self, small_png: bytes, capsys: pytest.CaptureFixture[str]) -> None:
        _print_iterm2_png(small_png)
        out = capsys.readouterr().out
        assert out.startswith(
            "\033]1337;File=inline=1;width=100%;preserveAspectRatio=1:"
        )
        assert out.endswith("\a\n")
        b64_part = out[
            len("\033]1337;File=inline=1;width=100%;preserveAspectRatio=1:") : -2
        ]
        decoded = base64.b64decode(b64_part)
        assert decoded == small_png


# ===================================================================
# _print_kitty_png
# ===================================================================


class TestPrintKittyPng:
    def test_single_chunk(
        self, small_png: bytes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A small PNG fits in one chunk: first (and only) chunk has m=0."""
        _print_kitty_png(small_png)
        out = capsys.readouterr().out
        assert out.startswith("\033_Ga=T,f=100,m=0;")
        assert out.endswith("\033\\\n")
        payload = out[len("\033_Ga=T,f=100,m=0;") : -len("\033\\\n")]
        assert base64.b64decode(payload) == small_png

    def test_multi_chunk(
        self, large_png: bytes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A large PNG produces multiple chunks with correct m= flags."""
        _print_kitty_png(large_png)
        out = capsys.readouterr().out

        chunks = out.split("\033_G")
        chunks = [c for c in chunks if c]

        assert len(chunks) >= 2, "Expected at least 2 chunks for a large PNG"

        first = chunks[0]
        assert first.startswith("a=T,f=100,m=1;")

        for middle in chunks[1:-1]:
            assert middle.startswith("m=1;")

        last = chunks[-1]
        assert last.startswith("m=0;")

        assert out.endswith("\n")

    def test_chunk_payload_size(
        self, large_png: bytes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Each chunk's base64 payload must be at most 4096 chars."""
        _print_kitty_png(large_png)
        out = capsys.readouterr().out

        chunks = [c for c in out.split("\033_G") if c]
        for chunk in chunks:
            semi = chunk.index(";")
            end = chunk.index("\033\\")
            payload = chunk[semi + 1 : end]
            assert len(payload) <= 4096

    def test_roundtrip(
        self, large_png: bytes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Concatenating all chunk payloads and decoding gives back the PNG."""
        _print_kitty_png(large_png)
        out = capsys.readouterr().out

        chunks = [c for c in out.split("\033_G") if c]
        b64_all = ""
        for chunk in chunks:
            semi = chunk.index(";")
            end = chunk.index("\033\\")
            b64_all += chunk[semi + 1 : end]
        assert base64.b64decode(b64_all) == large_png


# ===================================================================
# _print_sixel_png
# ===================================================================


class TestPrintSixelPng:
    @pytest.mark.filterwarnings("ignore::DeprecationWarning:textual_image")
    def test_dcs_framing(
        self, small_png: bytes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sixel output should start with DCS (ESC P) and end with ST (ESC \\)."""
        _print_sixel_png(small_png)
        out = capsys.readouterr().out
        assert "\x1bP" in out or "\x90" in out, "Sixel output should contain DCS"
        assert "\x1b\\" in out or "\x9c" in out, "Sixel output should contain ST"


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
        written = tmp_path / "termseries_TSLA_7d_4x1.png"  # type: ignore[operator]
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
        written = tmp_path / "termseries_AAPL-MSFT_1mo_16x9.png"  # type: ignore[operator]
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
        written = tmp_path / "termseries_A-B-C-D-E-F-plus2_7d_4x1.png"  # type: ignore[operator]
        assert written.exists()
