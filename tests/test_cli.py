"""Tests for CLI theme, output, and protocol resolution and precedence."""

from __future__ import annotations

import io
import warnings
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from termseries.cli import app
from termseries.render import _output_png

runner = CliRunner()

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 25  # minimal non-empty bytes
_FAKE_DATA = {"FAKE": [(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0)]}


class TestThemeResolution:
    def test_invalid_theme_in_config_warns_and_falls_back_to_auto(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid THEME in config emits a warning and resolves to 'auto'."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".termseries.env").write_text("THEME=midnight\n")

        captured: dict[str, str] = {}

        def mock_render(*args: object, **kwargs: object) -> bytes:
            captured["theme"] = str(kwargs.get("theme", "auto"))
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            runner.invoke(app, ["yahoo", "FAKE"])

        assert any(
            "midnight" in str(x.message) for x in w
        ), f"Expected warning about 'midnight', got: {[str(x.message) for x in w]}"
        assert captured.get("theme") == "auto"

    def test_cli_flag_overrides_config_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--theme CLI flag takes precedence over config file value."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".termseries.env").write_text("THEME=light\n")

        captured: dict[str, str] = {}

        def mock_render(*args: object, **kwargs: object) -> bytes:
            captured["theme"] = str(kwargs.get("theme", ""))
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            runner.invoke(app, ["--theme", "dark", "yahoo", "FAKE"])

        assert captured.get("theme") == "dark"

    def test_config_file_overrides_auto_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Config file THEME is used when no --theme flag is given."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        (tmp_path / ".termseries.env").write_text("THEME=dark\n")

        captured: dict[str, str] = {}

        def mock_render(*args: object, **kwargs: object) -> bytes:
            captured["theme"] = str(kwargs.get("theme", ""))
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            runner.invoke(app, ["yahoo", "FAKE"])

        assert captured.get("theme") == "dark"


# ---------------------------------------------------------------------------
# Helpers shared by output/protocol tests
# ---------------------------------------------------------------------------

_REAL_PNG = (
    b"\x89PNG\r\n\x1a\n"  # PNG signature
    b"\x00\x00\x00\rIHDR"  # IHDR chunk length + type
    b"\x00\x00\x00\x02"  # width = 2
    b"\x00\x00\x00\x03"  # height = 3
    b"\x08\x02\x00\x00\x00"  # bit depth, color type, etc.
    b"\x12\x16\xe0\x00"  # CRC (not verified by our code)
    b"\x00" * 20  # padding
)


def _run_yahoo_with_output_capture(
    cli_args: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, dict[str, object]]:
    """Run 'termseries yahoo FAKE' with given args; returns (result, captured)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    captured: dict[str, object] = {}

    def mock_output(
        png: object, names: object, ratio: object, period: object, **kwargs: object
    ) -> None:
        captured.update(kwargs)
        captured["png"] = png

    with (
        patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
        patch("termseries.cli._render_png", return_value=_FAKE_PNG),
        patch("termseries.cli._output_png", side_effect=mock_output),
    ):
        result = runner.invoke(app, cli_args)
    return result, captured


# ---------------------------------------------------------------------------
# --output option tests
# ---------------------------------------------------------------------------


class TestOutputOption:
    def test_output_stdout_writes_raw_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--output - writes raw PNG bytes to sys.stdout.buffer."""
        monkeypatch.chdir(tmp_path)
        fake_buf = io.BytesIO()

        with (
            patch("termseries.render._is_kitty", return_value=False),
            patch("termseries.render._is_iterm2", return_value=False),
            patch("termseries.render._is_sixel_terminal", return_value=False),
            patch("sys.stdout") as mock_stdout,
        ):
            mock_stdout.buffer = fake_buf
            _output_png(_FAKE_PNG, ["A"], (4, 1), "7d", output="-")

        assert fake_buf.getvalue() == _FAKE_PNG

    def test_output_named_file_writes_png(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--output foo.png writes to the named file."""
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "myplot.png"
        _output_png(_FAKE_PNG, ["A"], (4, 1), "7d", output=str(out))
        assert out.exists()
        assert out.read_bytes() == _FAKE_PNG

    def test_output_inline_no_protocol_warns_and_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--output inline with no detectable protocol warns and falls back to file."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("termseries.render._is_kitty", return_value=False),
            patch("termseries.render._is_iterm2", return_value=False),
            patch("termseries.render._is_sixel_terminal", return_value=False),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            _output_png(_FAKE_PNG, ["TSLA"], (4, 1), "7d", output="inline")

        assert any("No inline protocol" in str(x.message) for x in w)
        written = tmp_path / "termseries_TSLA_7d_4x1.png"
        assert written.exists()

    def test_output_auto_no_terminal_writes_auto_named_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default output=auto with no detected terminal writes auto-named file."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("termseries.render._is_kitty", return_value=False),
            patch("termseries.render._is_iterm2", return_value=False),
            patch("termseries.render._is_sixel_terminal", return_value=False),
        ):
            _output_png(_FAKE_PNG, ["AAPL"], (4, 1), "30d")
        written = tmp_path / "termseries_AAPL_30d_4x1.png"
        assert written.exists()

    def test_cli_output_flag_passed_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--output CLI flag is wired through to _output_png."""
        out_path = str(tmp_path / "chart.png")
        _, captured = _run_yahoo_with_output_capture(
            ["--output", out_path, "yahoo", "FAKE"], tmp_path, monkeypatch
        )
        assert captured.get("output") == out_path

    def test_cli_output_inline_flag_passed_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--output inline CLI flag is passed through to _output_png."""
        _, captured = _run_yahoo_with_output_capture(
            ["--output", "inline", "yahoo", "FAKE"], tmp_path, monkeypatch
        )
        assert captured.get("output") == "inline"


# ---------------------------------------------------------------------------
# --protocol option tests
# ---------------------------------------------------------------------------


class TestProtocolOption:
    def test_protocol_kitty_overrides_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--protocol kitty calls _print_kitty_png regardless of detection."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._is_kitty", return_value=False),
            patch("termseries.render._is_iterm2", return_value=True),
            patch("termseries.render._print_kitty_png") as kitty_mock,
            patch("termseries.render._print_iterm2_png") as iterm_mock,
        ):
            _output_png(
                _FAKE_PNG, ["A"], (4, 1), "7d", output="inline", protocol="kitty"
            )
        kitty_mock.assert_called_once_with(_FAKE_PNG)
        iterm_mock.assert_not_called()

    def test_protocol_iterm2_overrides_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--protocol iterm2 calls _print_iterm2_png regardless of detection."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._is_kitty", return_value=True),
            patch("termseries.render._print_kitty_png") as kitty_mock,
            patch("termseries.render._print_iterm2_png") as iterm_mock,
        ):
            _output_png(
                _FAKE_PNG, ["A"], (4, 1), "7d", output="inline", protocol="iterm2"
            )
        iterm_mock.assert_called_once_with(_FAKE_PNG)
        kitty_mock.assert_not_called()

    def test_protocol_sixel_overrides_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--protocol sixel calls _print_sixel_png regardless of detection."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._is_kitty", return_value=True),
            patch("termseries.render._print_kitty_png") as kitty_mock,
            patch("termseries.render._print_sixel_png") as sixel_mock,
        ):
            _output_png(
                _FAKE_PNG, ["A"], (4, 1), "7d", output="inline", protocol="sixel"
            )
        sixel_mock.assert_called_once_with(_FAKE_PNG)
        kitty_mock.assert_not_called()

    def test_protocol_ignored_for_file_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--protocol has no effect when --output is a file path."""
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "out.png"
        with patch("termseries.render._print_kitty_png") as kitty_mock:
            _output_png(
                _FAKE_PNG, ["A"], (4, 1), "7d", output=str(out), protocol="kitty"
            )
        kitty_mock.assert_not_called()
        assert out.read_bytes() == _FAKE_PNG

    def test_invalid_protocol_cli_flag_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrecognized --protocol value causes a usage error."""
        _, captured = _run_yahoo_with_output_capture(
            ["--protocol", "xterm", "yahoo", "FAKE"], tmp_path, monkeypatch
        )
        # _output_png should not have been called due to validation failure
        assert "output" not in captured

    def test_cli_protocol_flag_passed_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--protocol CLI flag is wired through to _output_png."""
        _, captured = _run_yahoo_with_output_capture(
            ["--protocol", "kitty", "yahoo", "FAKE"], tmp_path, monkeypatch
        )
        assert captured.get("protocol") == "kitty"

    def test_auto_output_explicit_protocol_uses_protocol_when_terminal_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """output=auto + explicit protocol uses that protocol when terminal detected."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch("termseries.render._is_kitty", return_value=False),
            patch("termseries.render._is_iterm2", return_value=True),
            patch("termseries.render._is_sixel_terminal", return_value=False),
            patch("termseries.render._print_kitty_png") as kitty_mock,
        ):
            _output_png(_FAKE_PNG, ["A"], (4, 1), "7d", output="auto", protocol="kitty")
        kitty_mock.assert_called_once_with(_FAKE_PNG)

    def test_auto_output_explicit_protocol_falls_back_when_no_terminal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """output=auto + protocol=kitty falls back to file when no terminal detected."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("termseries.render._is_kitty", return_value=False),
            patch("termseries.render._is_iterm2", return_value=False),
            patch("termseries.render._is_sixel_terminal", return_value=False),
            patch("termseries.render._print_kitty_png") as kitty_mock,
        ):
            _output_png(_FAKE_PNG, ["A"], (4, 1), "7d", output="auto", protocol="kitty")
        kitty_mock.assert_not_called()
        assert (tmp_path / "termseries_A_7d_4x1.png").exists()


# ---------------------------------------------------------------------------
# termseries.env config file tests for output/protocol
# ---------------------------------------------------------------------------


class TestOutputProtocolConfigFile:
    def test_config_protocol_used_when_no_cli_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """protocol=kitty in termseries.env is used when --protocol is not passed."""
        (tmp_path / ".termseries.env").write_text("PROTOCOL=kitty\n")
        _, captured = _run_yahoo_with_output_capture(
            ["yahoo", "FAKE"], tmp_path, monkeypatch
        )
        assert captured.get("protocol") == "kitty"

    def test_config_output_used_when_no_cli_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """output=inline in termseries.env is used when --output is not passed."""
        (tmp_path / ".termseries.env").write_text("OUTPUT=inline\n")
        _, captured = _run_yahoo_with_output_capture(
            ["yahoo", "FAKE"], tmp_path, monkeypatch
        )
        assert captured.get("output") == "inline"

    def test_cli_protocol_overrides_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--protocol CLI flag takes precedence over config file."""
        (tmp_path / ".termseries.env").write_text("PROTOCOL=iterm2\n")
        _, captured = _run_yahoo_with_output_capture(
            ["--protocol", "kitty", "yahoo", "FAKE"], tmp_path, monkeypatch
        )
        assert captured.get("protocol") == "kitty"

    def test_invalid_protocol_in_config_warns_and_falls_back(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid protocol in termseries.env emits a warning and resolves to 'auto'."""
        (tmp_path / ".termseries.env").write_text("PROTOCOL=xterm\n")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _, captured = _run_yahoo_with_output_capture(
                ["yahoo", "FAKE"], tmp_path, monkeypatch
            )

        assert any("xterm" in str(x.message) for x in w)
        assert captured.get("protocol") == "auto"


# ---------------------------------------------------------------------------
# Validator callbacks
# ---------------------------------------------------------------------------


class TestValidators:
    def test_validate_period_invalid_raises(self) -> None:
        """`_validate_period` with a garbage string raises BadParameter."""
        result = runner.invoke(app, ["--period", "xyz123", "yahoo", "FAKE"])
        assert result.exit_code != 0

    def test_validate_theme_invalid_raises(self) -> None:
        """`_validate_theme` with an unknown theme raises BadParameter."""
        result = runner.invoke(app, ["--theme", "neon", "yahoo", "FAKE"])
        assert result.exit_code != 0

    def test_version_flag(self) -> None:
        """--version prints the version string and exits 0."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "termseries" in result.output


# ---------------------------------------------------------------------------
# info command
# ---------------------------------------------------------------------------


class TestInfoCommand:
    def test_info_runs_and_shows_terminal_info(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The info command exits 0 and includes key labels in output."""
        with (
            patch("termseries.cli.supports_kitty_graphics", return_value=False),
            patch("termseries.cli.supports_iterm2_inline_images", return_value=False),
            patch("termseries.cli.supports_sixel", return_value=False),
        ):
            result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Terminal info" in result.output
        assert "Kitty protocol" in result.output
        assert "Inline rendering" in result.output

    def test_info_shows_env_vars_when_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Info command prints env vars that are set."""
        monkeypatch.setenv("TERM", "xterm-kitty")
        with (
            patch("termseries.cli.supports_kitty_graphics", return_value=True),
            patch("termseries.cli.supports_iterm2_inline_images", return_value=False),
            patch("termseries.cli.supports_sixel", return_value=False),
        ):
            result = runner.invoke(app, ["info"])
        assert "TERM=xterm-kitty" in result.output
