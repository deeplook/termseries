"""Tests for termseries.terminal helper functions."""

import base64
import struct
from pathlib import Path

import pytest
import typer

from termseries.terminal import (
    _detect_dark_terminal,
    _is_docker,
    _is_iterm2,
    _is_kitty,
    _is_sixel_terminal,
    _is_ssh_session,
    _load_config,
    _parse_ratio,
    _png_dimensions,
    _print_iterm2_png,
    _print_kitty_png,
    _print_sixel_png,
)

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
# _is_docker
# ===================================================================


class TestIsDocker:
    def test_inside_docker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dockerenv = tmp_path / ".dockerenv"
        dockerenv.touch()
        monkeypatch.setattr(
            "termseries.terminal.Path", lambda p: tmp_path / p.lstrip("/")
        )
        assert _is_docker() is True

    def test_outside_docker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "termseries.terminal.Path", lambda p: tmp_path / p.lstrip("/")
        )
        assert _is_docker() is False


# ===================================================================
# _detect_dark_terminal
# ===================================================================


@pytest.mark.usefixtures("_clean_env")
class TestDetectDarkTerminal:
    def test_theme_dark(self) -> None:
        assert _detect_dark_terminal("dark") is True

    def test_theme_light(self) -> None:
        assert _detect_dark_terminal("light") is False

    def test_colorfgbg_dark_bg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "15;0")
        assert _detect_dark_terminal("auto") is True

    def test_colorfgbg_light_bg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "0;15")
        assert _detect_dark_terminal("auto") is False

    def test_colorfgbg_three_parts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "15;0;0")
        assert _detect_dark_terminal("auto") is True

    def test_colorfgbg_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "garbage")
        assert _detect_dark_terminal("auto") is True

    def test_iterm_profile_dark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ITERM_PROFILE", "Solarized Dark")
        assert _detect_dark_terminal("auto") is True

    def test_iterm_profile_light(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ITERM_PROFILE", "Solarized Light")
        assert _detect_dark_terminal("auto") is False

    def test_auto_default_is_dark(self) -> None:
        assert _detect_dark_terminal("auto") is True


# ===================================================================
# _load_config
# ===================================================================


class TestLoadConfig:
    def test_no_file_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        assert _load_config() == {}

    def test_cwd_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".termseries.env").write_text("THEME=dark\n")
        assert _load_config().get("theme") == "dark"

    def test_global_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        home = tmp_path / "home"
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        global_conf = home / ".config" / "termseries" / "termseries.env"
        global_conf.parent.mkdir(parents=True)
        global_conf.write_text("THEME=light\n")
        assert _load_config().get("theme") == "light"

    def test_cwd_overrides_global(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        home = tmp_path / "home"
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: home)
        (tmp_path / ".termseries.env").write_text("THEME=dark\n")
        global_conf = home / ".config" / "termseries" / "termseries.env"
        global_conf.parent.mkdir(parents=True)
        global_conf.write_text("THEME=light\n")
        assert _load_config().get("theme") == "dark"

    def test_unknown_keys_present_in_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".termseries.env").write_text("THEME=dark\nFOO=bar\n")
        cfg = _load_config()
        assert cfg.get("theme") == "dark"
        assert "foo" in cfg  # unknown keys are lowercased and returned, just unused

    def test_keys_are_lowercased(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".termseries.env").write_text("THEME=light\n")
        assert _load_config().get("theme") == "light"


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
    @pytest.mark.filterwarnings("ignore::DeprecationWarning:textual_image")  # type: ignore[misc]
    def test_dcs_framing(
        self, small_png: bytes, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Sixel output should start with DCS (ESC P) and end with ST (ESC \\)."""
        _print_sixel_png(small_png)
        out = capsys.readouterr().out
        assert "\x1bP" in out or "\x90" in out, "Sixel output should contain DCS"
        assert "\x1b\\" in out or "\x9c" in out, "Sixel output should contain ST"
