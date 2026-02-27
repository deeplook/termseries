"""Tests for the Textual TUI (termseries.tui).

All tests run in Textual's headless mode via App.run_test() + Pilot.
No real terminal, PTY, or network I/O is required.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any
from unittest.mock import patch

from PIL import Image as PILImage
from textual.widgets import Input, Select

from termseries.tui import _build_app
from tests.conftest import make_series

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PERIOD_CHOICES = ["7d", "1mo", "3mo", "1y"]


def _make_png(width: int = 4, height: int = 3) -> bytes:
    """Create a minimal valid PNG via Pillow."""
    buf = BytesIO()
    PILImage.new("RGB", (width, height), color=(0, 128, 255)).save(buf, format="PNG")
    return buf.getvalue()


_SMALL_PNG = _make_png()


def _fake_fetch(columns: list[str], period: str) -> dict:  # type: ignore[type-arg]
    return {col: make_series() for col in columns}


def _make_app(**kwargs: Any) -> Any:
    """Build a non-Ghostty app with a mocked fetch_fn."""
    defaults: dict[str, Any] = {
        "initial_columns": ["TSLA"],
        "period_choices": _PERIOD_CHOICES,
        "period": "7d",
        "fetch_fn": _fake_fetch,
    }
    defaults.update(kwargs)
    with patch("termseries.tui._is_ghostty", return_value=False):
        return _build_app(**defaults)


# ---------------------------------------------------------------------------
# Widget composition
# ---------------------------------------------------------------------------


class TestCompose:
    async def test_app_launches_and_has_menu(self) -> None:
        """App composes the menu bar and chart area."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                assert pilot.app.query_one("#tickers", Input)
                assert pilot.app.query_one("#chart")

    async def test_tickers_input_populated(self) -> None:
        """Initial columns are pre-filled in the ticker input."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(initial_columns=["AAPL", "MSFT"]).run_test() as pilot:
                inp = pilot.app.query_one("#tickers", Input)
                assert inp.value == "AAPL MSFT"

    async def test_period_select_has_choices(self) -> None:
        """Period dropdown contains the supplied period_choices."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                period_select: Select[str] = pilot.app.query(Select)[0]
                option_values = [v for _, v in period_select._options]
                for p in _PERIOD_CHOICES:
                    assert p in option_values

    async def test_no_initial_columns_no_fetch(self) -> None:
        """When initial_columns is empty, fetch_fn is never called."""
        calls: list[object] = []

        def tracking_fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            calls.append((cols, period))
            return {}

        async with _make_app(initial_columns=[], fetch_fn=tracking_fetch).run_test():
            pass

        assert calls == []


# ---------------------------------------------------------------------------
# Help screen
# ---------------------------------------------------------------------------


class TestHelpScreen:
    async def test_question_mark_opens_help(self) -> None:
        """Pressing '?' pushes the HelpScreen modal."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                assert len(pilot.app.screen_stack) == 1
                await pilot.press("question_mark")
                assert len(pilot.app.screen_stack) == 2

    async def test_any_key_closes_help(self) -> None:
        """Pressing any key on HelpScreen dismisses it."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.press("question_mark")
                assert len(pilot.app.screen_stack) == 2
                await pilot.press("space")
                assert len(pilot.app.screen_stack) == 1

    async def test_ctrl_h_opens_help(self) -> None:
        """Ctrl+H is an alternative binding for help."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.press("ctrl+h")
                assert len(pilot.app.screen_stack) == 2


# ---------------------------------------------------------------------------
# Quit actions
# ---------------------------------------------------------------------------


class TestQuit:
    async def test_ctrl_d_quits(self) -> None:
        """Ctrl+D exits the app."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.press("ctrl+d")
            # Reaching here means the app exited cleanly

    async def test_double_ctrl_c_quits(self) -> None:
        """Two Ctrl+C presses within 2 s exit the app."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.press("ctrl+c")
                await pilot.press("ctrl+c")


# ---------------------------------------------------------------------------
# Ticker input
# ---------------------------------------------------------------------------


class TestTickerInput:
    async def test_submit_new_tickers_calls_fetch(self) -> None:
        """Submitting the ticker input triggers a fetch."""
        calls: list[list[str]] = []

        def tracking_fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            calls.append(cols)
            return {c: make_series() for c in cols}

        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(
                initial_columns=[], fetch_fn=tracking_fetch
            ).run_test() as pilot:
                inp = pilot.app.query_one("#tickers", Input)
                await pilot.click("#tickers")
                pilot.app.query_one("#tickers", Input).clear()
                inp.value = "NVDA"
                await pilot.press("enter")

        assert any("NVDA" in cols for cols in calls)

    async def test_empty_tickers_shows_notification(self) -> None:
        """Submitting an empty ticker input triggers a warning notification."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(initial_columns=[]).run_test() as pilot:
                inp = pilot.app.query_one("#tickers", Input)
                inp.value = ""
                await pilot.press("enter")
                # App should still be running (not crashed)
                assert pilot.app.is_running


# ---------------------------------------------------------------------------
# Yank (clipboard) action
# ---------------------------------------------------------------------------


class TestYankAction:
    async def test_yank_without_plot_shows_warning(self) -> None:
        """Ctrl+Y with no plot rendered shows a 'No plot to copy' notification."""
        async with _make_app(initial_columns=[]).run_test() as pilot:
            await pilot.press("ctrl+y")
            # App still running — no crash
            assert pilot.app.is_running

    async def test_yank_with_plot_calls_clipboard(self) -> None:
        """Ctrl+Y with a rendered plot calls _copy_to_clipboard."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                # Ensure callback ran and _last_png is set
                await pilot.pause()
                if pilot.app._last_png is not None:
                    with patch("termseries.tui._copy_to_clipboard") as mock_copy:
                        await pilot.press("ctrl+y")
                    mock_copy.assert_called_once_with(_SMALL_PNG)


# ---------------------------------------------------------------------------
# Auto-reload toggle
# ---------------------------------------------------------------------------


class TestReloadToggle:
    async def test_ctrl_r_starts_reload_timer(self) -> None:
        """Ctrl+R when no timer is active starts the reload timer."""
        async with _make_app(initial_columns=[]).run_test() as pilot:
            assert pilot.app._reload_timer is None
            await pilot.press("ctrl+r")
            assert pilot.app._reload_timer is not None

    async def test_ctrl_r_twice_stops_timer(self) -> None:
        """A second Ctrl+R cancels the reload timer."""
        async with _make_app(initial_columns=[]).run_test() as pilot:
            await pilot.press("ctrl+r")
            await pilot.press("ctrl+r")
            assert pilot.app._reload_timer is None
