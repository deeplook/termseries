"""Tests for CLI theme, output, and protocol resolution and precedence."""

from __future__ import annotations

import io
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import Result
from typer.testing import CliRunner

from termseries.cli import app
from termseries.render import _output_png

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    """Strip ANSI color codes Rich adds when it detects a color-capable terminal.

    Typer's error rendering styles individual `--flag` tokens with their own
    color runs, splitting substrings like '--last' across escape sequences;
    whether that happens depends on the environment (e.g. GitHub Actions
    forces color even for captured, non-tty output), so assertions against
    raw result.output are flaky across environments.
    """
    return _ANSI_RE.sub("", output)


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
        ):
            result = runner.invoke(app, ["yahoo", "FAKE"])

        assert "midnight" in result.output, (
            f"Expected warning about 'midnight' in output, got: {result.output!r}"
        )
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


class TestTitleOption:
    def test_default_omits_title_kwarg(self) -> None:
        """No --title given: _render_png isn't passed a title override."""
        captured: dict[str, object] = {"title": "sentinel"}

        def mock_render(*args: object, **kwargs: object) -> bytes:
            captured["title"] = kwargs.get("title")
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["yahoo", "FAKE"])

        assert result.exit_code == 0
        assert captured["title"] is None

    def test_custom_title_passed_through(self) -> None:
        captured: dict[str, object] = {}

        def mock_render(*args: object, **kwargs: object) -> bytes:
            captured["title"] = kwargs.get("title")
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["--title", "My Custom Title", "yahoo", "FAKE"])

        assert result.exit_code == 0
        assert captured["title"] == "My Custom Title"

    def test_custom_title_forwarded_to_interactive(self) -> None:
        with (
            patch("termseries.cli._run_interactive") as run_tui,
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
        ):
            result = runner.invoke(
                app, ["--title", "Custom", "--interactive", "yahoo", "FAKE"]
            )

        assert result.exit_code == 0
        run_tui.assert_called_once()
        assert run_tui.call_args.kwargs["title"] == "Custom"


class TestLegendOption:
    def test_default_shows_legend(self) -> None:
        captured: dict[str, object] = {"show_legend": "sentinel"}

        def mock_render(*args: object, **kwargs: object) -> bytes:
            captured["show_legend"] = kwargs.get("show_legend")
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["yahoo", "FAKE"])

        assert result.exit_code == 0
        assert captured["show_legend"] is True

    def test_no_legend_flag_disables_legend(self) -> None:
        captured: dict[str, object] = {}

        def mock_render(*args: object, **kwargs: object) -> bytes:
            captured["show_legend"] = kwargs.get("show_legend")
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["--no-legend", "yahoo", "FAKE"])

        assert result.exit_code == 0
        assert captured["show_legend"] is False

    def test_no_legend_forwarded_to_interactive(self) -> None:
        with (
            patch("termseries.cli._run_interactive") as run_tui,
            patch("termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA),
        ):
            result = runner.invoke(
                app, ["--no-legend", "--interactive", "yahoo", "FAKE"]
            )

        assert result.exit_code == 0
        run_tui.assert_called_once()
        assert run_tui.call_args.kwargs["legend"] is False


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
) -> tuple[Result, dict[str, object]]:
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

        result, captured = _run_yahoo_with_output_capture(
            ["yahoo", "FAKE"], tmp_path, monkeypatch
        )

        assert "xterm" in result.output
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

    def test_validate_tz_invalid_iana_name_raises(self) -> None:
        """`_validate_tz` with a bogus IANA zone raises BadParameter cleanly,
        instead of crashing deep inside rendering with ZoneInfoNotFoundError."""
        result = runner.invoke(app, ["--tz", "Not/ARealZone", "yahoo", "FAKE"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_validate_tz_accepts_utc_local_and_iana(self) -> None:
        for value in ("UTC", "local", "Europe/Berlin"):
            result = runner.invoke(app, ["--tz", value, "--version"])
            assert result.exit_code == 0

    def test_version_flag(self) -> None:
        """--version prints the version string and exits 0."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "termseries" in result.output


class TestTimeRangeOptions:
    def test_last_is_the_canonical_rolling_window_option(self) -> None:
        with (
            patch(
                "termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA
            ) as fetch,
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["yahoo", "FAKE", "--last", "2w"])

        assert result.exit_code == 0
        fetch.assert_called_once_with(["FAKE"], "2w", interval="auto", tz="UTC")

    def test_fixed_bounds_fetch_max_then_apply_an_inclusive_range(self) -> None:
        data = {
            "FAKE": [
                (datetime(2024, 1, 1, tzinfo=timezone.utc), 1.0),
                (datetime(2024, 1, 2, tzinfo=timezone.utc), 2.0),
                (datetime(2024, 1, 3, tzinfo=timezone.utc), 3.0),
            ]
        }
        captured: dict[str, object] = {}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["series"] = series
            captured["xlim"] = kwargs["xlim"]
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=data) as fetch,
            patch("termseries.cli._render_png", side_effect=render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(
                app,
                [
                    "yahoo",
                    "FAKE",
                    "--from",
                    "2024-01-02",
                    "--to",
                    "2024-01-03",
                ],
            )

        assert result.exit_code == 0
        fetch.assert_called_once_with(["FAKE"], "max", interval="auto", tz="UTC")
        assert captured["series"] == {"FAKE": data["FAKE"][1:]}
        assert captured["xlim"] == (
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 23, 59, 59, tzinfo=timezone.utc),
        )

    def test_open_ended_bound_uses_a_sized_duration_not_max(self) -> None:
        """Regression test: --from with no --to (so the window reaches
        "now") must not fetch range=max -- Yahoo silently coarsens
        interval=1d data to monthly/quarterly bars for range=max on
        long-lived tickers, even when the actual requested window is
        narrow. A day-count duration lets Yahoo pick a properly sized
        native range instead, so interval=1d is honored."""
        with (
            patch(
                "termseries.cli.fetch_yahoo_series", return_value=_FAKE_DATA
            ) as fetch,
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["yahoo", "FAKE", "--from", "2020-01-01"])

        assert result.exit_code == 0
        fetch_period = fetch.call_args.args[1]
        assert fetch_period != "max"
        assert re.fullmatch(r"\d+d", fetch_period)

    def test_past_to_bound_still_fetches_max(self) -> None:
        """A window anchored to a --to in the past can't use the sized-
        duration trick (Yahoo's range parameter always means "ending
        today"), so it must keep fetching full history to correctly
        locate an arbitrary historical window."""
        data = {"FAKE": [(datetime(2020, 3, 1, tzinfo=timezone.utc), 100.0)]}
        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=data) as fetch,
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(
                app, ["yahoo", "FAKE", "--from", "2020-01-01", "--to", "2020-06-01"]
            )

        assert result.exit_code == 0
        fetch.assert_called_once_with(["FAKE"], "max", interval="auto", tz="UTC")

    def test_year_only_to_bound_covers_the_whole_year(self) -> None:
        """Regression test: a ticker that only trades within the --to year
        (e.g. it IPO'd there) must not be dropped by --from 2025 --to 2026
        just because --to 2026 used to mean "2026-01-01T00:00:00"."""
        data = {
            "TSLA": [(datetime(2025, 6, 1, tzinfo=timezone.utc), 1.0)],
            "SPCX": [(datetime(2026, 3, 1, tzinfo=timezone.utc), 1.0)],
        }
        captured: dict[str, object] = {}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["series"] = series
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=data),
            patch("termseries.cli._render_png", side_effect=render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(
                app,
                ["yahoo", "TSLA", "SPCX", "--from", "2025", "--to", "2026"],
            )

        assert result.exit_code == 0, _plain(result.output)
        assert captured["series"] == data

    def test_last_cannot_be_combined_with_explicit_bounds(self) -> None:
        result = runner.invoke(
            app, ["yahoo", "FAKE", "--last", "7d", "--from", "2024-01-01"]
        )
        assert result.exit_code != 0
        assert "either --last or --from/--to" in _plain(result.output)

    def test_first_uses_the_earliest_returned_point_as_its_anchor(self) -> None:
        data = {
            "FAKE": [
                (datetime(2024, 1, 1, tzinfo=timezone.utc), 1.0),
                (datetime(2024, 1, 2, tzinfo=timezone.utc), 2.0),
                (datetime(2024, 1, 3, tzinfo=timezone.utc), 3.0),
            ]
        }
        captured: dict[str, object] = {}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["series"] = series
            captured["xlim"] = kwargs["xlim"]
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=data) as fetch,
            patch("termseries.cli._render_png", side_effect=render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["yahoo", "FAKE", "--first", "1d"])

        assert result.exit_code == 0
        fetch.assert_called_once_with(["FAKE"], "max", interval="auto", tz="UTC")
        assert captured["series"] == {"FAKE": data["FAKE"][:2]}
        assert captured["xlim"] == (
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )

    def test_first_cannot_be_combined_with_other_range_options(self) -> None:
        result = runner.invoke(
            app, ["yahoo", "FAKE", "--first", "7d", "--from", "2024-01-01"]
        )
        assert result.exit_code != 0
        assert "Use --first by itself" in _plain(result.output)


class TestYahooCommand:
    def test_output_filename_uses_resolved_tickers_not_raw_input(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auto-filename must reflect the deduped/uppercased fetched tickers,
        not the raw (possibly duplicate, differently-cased) CLI arguments."""
        monkeypatch.chdir(tmp_path)
        fake_data = {"TSLA": [(datetime(2024, 1, 1, tzinfo=timezone.utc), 100.0)]}
        captured: dict[str, object] = {}

        def mock_output(
            png: object, names: object, ratio: object, period: object, **kwargs: object
        ) -> None:
            captured["names"] = names

        with (
            patch("termseries.cli.fetch_yahoo_series", return_value=fake_data),
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png", side_effect=mock_output),
        ):
            result = runner.invoke(app, ["yahoo", "tsla", "TSLA"])

        assert result.exit_code == 0
        # Raw input was ["tsla", "TSLA"] (duplicate, mixed case); the fetched/
        # rendered data only has one deduped "TSLA" series.
        assert captured["names"] == ["TSLA"]


class TestPolymarketCommand:
    def test_polymarket_command_wires_fetch_and_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The polymarket command passes Polymarket-specific options through."""
        monkeypatch.chdir(tmp_path)
        captured: dict[str, object] = {}

        def mock_output(
            png: object, names: object, ratio: object, period: object, **kwargs: object
        ) -> None:
            captured["names"] = names
            captured.update(kwargs)

        with (
            patch(
                "termseries.cli.fetch_polymarket_series", return_value=_FAKE_DATA
            ) as fetch_mock,
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png", side_effect=mock_output),
        ):
            result = runner.invoke(
                app,
                [
                    "polymarket",
                    "btc-150k",
                    "--period",
                    "7d",
                    "--outcome",
                    "no",
                    "--interval",
                    "1h",
                    "--fidelity",
                    "5",
                ],
            )

        assert result.exit_code == 0
        fetch_mock.assert_called_once_with(
            ["btc-150k"], "7d", outcome="no", interval="1h", fidelity=5, tz="UTC"
        )
        assert captured["names"] == ["FAKE"]


# ---------------------------------------------------------------------------
# csv and hass commands
# ---------------------------------------------------------------------------


class TestCsvCommand:
    def test_csv_command_wires_fetch_and_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The csv command reads files and derives labels from the data
        returned by fetch_csv_series (which labels by file stem, or by
        stem.column when columns are selected)."""
        monkeypatch.chdir(tmp_path)
        captured: dict[str, object] = {}

        def mock_output(
            png: object, names: object, ratio: object, period: object, **kwargs: object
        ) -> None:
            captured["names"] = names

        with (
            patch(
                "termseries.cli.fetch_csv_series", return_value=_FAKE_DATA
            ) as fetch_mock,
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png", side_effect=mock_output),
        ):
            result = runner.invoke(
                app,
                [
                    "csv",
                    "temp.csv",
                    "--period",
                    "7d",
                    "--resample",
                    "1m",
                    "--aggregate",
                    "median",
                ],
            )

        assert result.exit_code == 0
        fetch_mock.assert_called_once_with(
            ["temp.csv"], "7d", tz="UTC", resample="1m", aggregate="median"
        )
        # Labels come from fetch_csv_series's returned keys.
        assert captured["names"] == ["FAKE"]


class TestHassCommand:
    def test_hass_command_wires_fetch_and_autodetects_unit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The hass command auto-detects the unit when --unit is omitted."""
        monkeypatch.chdir(tmp_path)
        captured: dict[str, object] = {}

        def mock_render(*args: object, **kwargs: object) -> bytes:
            captured["value_unit"] = str(kwargs.get("value_unit"))
            return _FAKE_PNG

        with (
            patch(
                "termseries.cli.fetch_hass_series", return_value=_FAKE_DATA
            ) as fetch_mock,
            patch("termseries.cli._detect_unit", return_value="°C") as detect_mock,
            patch("termseries.cli._render_png", mock_render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(
                app, ["hass", "sensor.temperature", "--period", "30d"]
            )

        assert result.exit_code == 0
        fetch_mock.assert_called_once_with(["sensor.temperature"], "30d", tz="UTC")
        detect_mock.assert_called_once_with("sensor.temperature")
        assert captured["value_unit"] == "°C"

    def test_global_tz_flag_is_threaded_to_fetch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--tz must reach fetch_hass_series, not just chart display."""
        monkeypatch.chdir(tmp_path)
        with (
            patch(
                "termseries.cli.fetch_hass_series", return_value=_FAKE_DATA
            ) as fetch_mock,
            patch("termseries.cli._detect_unit", return_value="value"),
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(
                app,
                [
                    "--tz",
                    "America/Los_Angeles",
                    "hass",
                    "sensor.temperature",
                    "--period",
                    "ytd",
                ],
            )

        assert result.exit_code == 0
        fetch_mock.assert_called_once_with(
            ["sensor.temperature"], "ytd", tz="America/Los_Angeles"
        )

    def test_hass_interactive_also_autodetects_unit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`hass -i` must auto-detect the unit too, not just the one-shot path."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("termseries.cli._run_interactive") as run_tui,
            patch("termseries.cli._detect_unit", return_value="°C") as detect_mock,
        ):
            result = runner.invoke(
                app, ["-i", "hass", "sensor.temperature", "--period", "30d"]
            )

        assert result.exit_code == 0
        detect_mock.assert_called_once_with("sensor.temperature")
        assert run_tui.call_args.kwargs["value_unit"] == "°C"

    def test_hass_last_max_anchors_xlim_to_now(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Like csv, hass's chart x-axis should reach "now" for --last max
        (not just tightly fit the returned data), so a sensor that stopped
        reporting shows up as a visible trailing gap instead of being
        silently rescaled away."""
        monkeypatch.chdir(tmp_path)
        data = {
            "Living Room": [
                (datetime(2024, 1, 1, tzinfo=timezone.utc), 20.0),
                (datetime(2024, 1, 2, tzinfo=timezone.utc), 21.0),
            ]
        }
        captured: dict[str, object] = {}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["xlim"] = kwargs["xlim"]
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_hass_series", return_value=data),
            patch("termseries.cli._detect_unit", return_value="°C"),
            patch("termseries.cli._render_png", side_effect=render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, ["hass", "sensor.temperature", "--last", "max"])

        assert result.exit_code == 0
        xlim = captured["xlim"]
        assert xlim is not None
        start, end = xlim
        assert start == datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert end > datetime(2024, 1, 2, tzinfo=timezone.utc)

    def test_hass_last_auto_leaves_xlim_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--last auto should tightly fit the data with no forced "now" edge."""
        monkeypatch.chdir(tmp_path)
        captured: dict[str, object] = {}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["xlim"] = kwargs["xlim"]
            return _FAKE_PNG

        with (
            patch("termseries.cli.fetch_hass_series", return_value=_FAKE_DATA),
            patch("termseries.cli._detect_unit", return_value="°C"),
            patch("termseries.cli._render_png", side_effect=render),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(
                app, ["hass", "sensor.temperature", "--last", "auto"]
            )

        assert result.exit_code == 0
        assert captured["xlim"] is None


class TestObsidianCommand:
    def test_obsidian_command_wires_fetch_and_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The obsidian command reads the dir:field arg through and derives
        labels from the data returned by fetch_obsidian_series."""
        monkeypatch.chdir(tmp_path)
        captured: dict[str, object] = {}

        def mock_output(
            png: object, names: object, ratio: object, period: object, **kwargs: object
        ) -> None:
            captured["names"] = names

        with (
            patch(
                "termseries.cli.fetch_obsidian_series", return_value=_FAKE_DATA
            ) as fetch_mock,
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png", side_effect=mock_output),
        ):
            result = runner.invoke(
                app,
                ["obsidian", f"{tmp_path}:mood", "--period", "30d"],
            )

        assert result.exit_code == 0
        fetch_mock.assert_called_once_with([f"{tmp_path}:mood"], "30d", tz="UTC")
        assert captured["names"] == ["FAKE"]


# ---------------------------------------------------------------------------
# error propagation and interactive mode (shared across data commands)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv,fetch_target",
    [
        (["yahoo", "FAKE"], "fetch_yahoo_series"),
        (["polymarket", "some-market"], "fetch_polymarket_series"),
        (["csv", "data.csv"], "fetch_csv_series"),
        (["hass", "sensor.x"], "fetch_hass_series"),
        (["obsidian", "some_dir:mood"], "fetch_obsidian_series"),
    ],
)
class TestDataCommandBehaviors:
    def test_fetch_error_exits_nonzero_with_message(
        self,
        argv: list[str],
        fetch_target: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A fetch failure is reported and exits 1 for every data command."""
        monkeypatch.chdir(tmp_path)
        with (
            patch(
                f"termseries.cli.{fetch_target}",
                side_effect=RuntimeError("boom"),
            ),
            # hass resolves the unit before fetching; keep it off the network.
            patch("termseries.cli._detect_unit", return_value="value"),
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, argv)
        assert result.exit_code == 1
        assert "Error: boom" in result.output

    def test_render_error_exits_nonzero_with_message_not_a_crash(
        self,
        argv: list[str],
        fetch_target: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A _render_png failure (e.g. --mode relative with the wrong ticker
        count) must be reported cleanly too, not just fetch failures -- the
        render step used to be outside the try/except entirely."""
        monkeypatch.chdir(tmp_path)
        with (
            patch(f"termseries.cli.{fetch_target}", return_value=_FAKE_DATA),
            patch("termseries.cli._detect_unit", return_value="value"),
            patch(
                "termseries.cli._render_png",
                side_effect=ValueError("Relative mode requires exactly 2 series."),
            ),
            patch("termseries.cli._output_png"),
        ):
            result = runner.invoke(app, argv)
        assert result.exit_code == 1
        assert "Error: Relative mode requires exactly 2 series." in result.output

    def test_output_error_exits_nonzero_with_message_not_a_crash(
        self,
        argv: list[str],
        fetch_target: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A _output_png failure (e.g. --output to a nonexistent directory)
        must be reported cleanly too -- the output step used to be outside
        the try/except entirely."""
        monkeypatch.chdir(tmp_path)
        with (
            patch(f"termseries.cli.{fetch_target}", return_value=_FAKE_DATA),
            patch("termseries.cli._detect_unit", return_value="value"),
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch(
                "termseries.cli._output_png",
                side_effect=RuntimeError("Could not write to /no/such/dir/out.png"),
            ),
        ):
            result = runner.invoke(app, argv)
        assert result.exit_code == 1
        assert "Error: Could not write to /no/such/dir/out.png" in result.output

    def test_interactive_flag_launches_tui(
        self,
        argv: list[str],
        fetch_target: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`-i` routes every data command to the TUI instead of rendering once."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("termseries.cli._run_interactive") as run_tui,
            patch(f"termseries.cli.{fetch_target}", return_value=_FAKE_DATA),
            patch("termseries.cli._detect_unit", return_value="value"),
            patch("termseries.cli._render_png", return_value=_FAKE_PNG),
            patch("termseries.cli._output_png") as output,
        ):
            result = runner.invoke(app, ["-i", *argv])
        assert result.exit_code == 0
        run_tui.assert_called_once()
        # Interactive mode hands off to the TUI rather than the one-shot renderer.
        output.assert_not_called()

    def test_interactive_with_from_to_seeds_initial_range(
        self,
        argv: list[str],
        fetch_target: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--from/--to with -i is forwarded into the TUI as a pre-seeded
        Period entry instead of being rejected."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("termseries.cli._run_interactive") as run_tui,
            patch(f"termseries.cli.{fetch_target}", return_value=_FAKE_DATA),
            patch("termseries.cli._detect_unit", return_value="value"),
        ):
            result = runner.invoke(
                app, ["-i", *argv, "--from", "2024-01-01", "--to", "2024-06-01"]
            )
        assert result.exit_code == 0, _plain(result.output)
        run_tui.assert_called_once()
        assert (
            run_tui.call_args.kwargs["initial_range_label"] == "2024-01-01..2024-06-01"
        )
        assert run_tui.call_args.kwargs["initial_range"] == (
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 1, 23, 59, 59, tzinfo=timezone.utc),
        )

    def test_interactive_with_open_ended_from_keeps_range_end_none(
        self,
        argv: list[str],
        fetch_target: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression test: an omitted --to must stay None in the range
        forwarded to the TUI, not get frozen to the CLI-invocation-time
        "now" -- a frozen end quickly looks "in the past" to the TUI's own
        live re-fetch check, which then fetches period="max" instead of a
        properly sized window (and Yahoo silently coarsens interval=1d bars
        for range=max on long-lived tickers)."""
        monkeypatch.chdir(tmp_path)
        with (
            patch("termseries.cli._run_interactive") as run_tui,
            patch(f"termseries.cli.{fetch_target}", return_value=_FAKE_DATA),
            patch("termseries.cli._detect_unit", return_value="value"),
        ):
            result = runner.invoke(app, ["-i", *argv, "--from", "2022-01-01"])
        assert result.exit_code == 0, _plain(result.output)
        run_tui.assert_called_once()
        initial_range = run_tui.call_args.kwargs["initial_range"]
        assert initial_range[0] == datetime(2022, 1, 1, tzinfo=timezone.utc)
        assert initial_range[1] is None

    def test_interactive_with_first_still_rejected(
        self,
        argv: list[str],
        fetch_target: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--first stays data-anchored (depends on the freshly fetched
        series' earliest timestamp), which doesn't fit the TUI's live
        re-fetch model the way a fixed --from/--to range does."""
        monkeypatch.chdir(tmp_path)
        with (
            patch(f"termseries.cli.{fetch_target}", return_value=_FAKE_DATA),
            patch("termseries.cli._detect_unit", return_value="value"),
        ):
            result = runner.invoke(app, ["-i", *argv, "--first", "30d"])
        assert result.exit_code != 0
        assert "--first cannot be used with --interactive" in _plain(result.output)


class TestDemoCommand:
    def test_demo_runs_three_subprocesses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The demo command shells out to three example invocations."""
        with patch("termseries.cli.subprocess.run") as run_mock:
            result = runner.invoke(app, ["demo"])
        assert result.exit_code == 0
        assert run_mock.call_count == 3
        assert "Demo 1/3" in result.output


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
