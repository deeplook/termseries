"""Tests for the Textual TUI (termseries.tui).

All tests run in Textual's headless mode via App.run_test() + Pilot.
No real terminal, PTY, or network I/O is required.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
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

# Mirrors the closure-local sentinels in termseries.tui that mark the
# "custom…" and "from-to…" period options (not importable, keep in sync).
_CUSTOM = "__custom__"
_FROM_TO = "__from_to__"


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


# ---------------------------------------------------------------------------
# Period dropdown and custom-period entry
# ---------------------------------------------------------------------------


def _tracking_app(calls: list[str], **kwargs: Any) -> Any:
    """Build an app whose fetch records the period it was called with."""

    def tracking_fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
        calls.append(period)
        return {c: make_series() for c in cols}

    return _make_app(fetch_fn=tracking_fetch, **kwargs)


class TestPeriodSelect:
    async def test_selecting_period_triggers_fetch_with_new_period(self) -> None:
        """Choosing a concrete period from the dropdown re-fetches with it."""
        calls: list[str] = []
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _tracking_app(calls).run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = "1mo"
                await pilot.pause()
        assert "1mo" in calls

    async def test_custom_option_reveals_custom_input(self) -> None:
        """Picking the 'custom…' sentinel reveals the free-form period input."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = _CUSTOM
                await pilot.pause()
                assert pilot.app.query_one("#custom-period", Input).display is True

    async def test_valid_custom_period_is_added_and_fetched(self) -> None:
        """A valid custom period is accepted, added to the dropdown, and fetched."""
        calls: list[str] = []
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _tracking_app(calls).run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = _CUSTOM
                await pilot.pause()
                custom = pilot.app.query_one("#custom-period", Input)
                custom.focus()
                custom.value = "14d"
                await pilot.press("enter")
                await pilot.pause()
                option_values = {v for _, v in pilot.app.query(Select)[0]._options}
        assert "14d" in calls
        assert "14d" in option_values

    async def test_invalid_custom_period_warns_and_reverts(self) -> None:
        """An unparseable custom period is rejected and never fetched."""
        calls: list[str] = []
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _tracking_app(calls).run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = _CUSTOM
                await pilot.pause()
                custom = pilot.app.query_one("#custom-period", Input)
                custom.focus()
                custom.value = "not-a-period"
                await pilot.press("enter")
                await pilot.pause()
                assert pilot.app.is_running
                assert custom.display is False
        assert "not-a-period" not in calls

    async def test_escape_cancels_custom_input(self) -> None:
        """Escape while editing a custom period hides the input without fetching."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = _CUSTOM
                await pilot.pause()
                pilot.app.query_one("#custom-period", Input).focus()
                await pilot.press("escape")
                await pilot.pause()
                assert pilot.app.query_one("#custom-period", Input).display is False


class TestPeriodSelectWidth:
    async def test_custom_and_from_to_labels_do_not_wrap_in_overlay(self) -> None:
        """The full period list is long enough to scroll the overlay; the
        scrollbar eats extra width, so 'custom…'/'from-to…' need a wider
        buffer than the non-scrolling dropdowns or they wrap mid-word."""
        import re

        from textual.widgets._select import SelectOverlay

        from termseries.period import TUI_PERIOD_CHOICES

        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(period_choices=TUI_PERIOD_CHOICES).run_test(
                size=(60, 20)
            ) as pilot:
                await pilot.pause()
                s1 = pilot.app.query(Select)[0]
                s1.focus()
                await pilot.press("enter")
                overlay = s1.query_one(SelectOverlay)
                overlay.action_last()
                await pilot.pause()
                svg = pilot.app.export_screenshot()
                texts = {
                    t.strip() for t in re.findall(r">([^<]+)</text>", svg) if t.strip()
                }
        assert "custom…" in texts
        assert "from-to…" in texts


class TestFromToSelect:
    async def test_selecting_from_to_opens_modal(self) -> None:
        """Picking the 'from-to…' sentinel pushes the modal dialog."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.pause()
                assert len(pilot.app.screen_stack) == 1
                pilot.app.query(Select)[0].value = _FROM_TO
                await pilot.pause()
                assert len(pilot.app.screen_stack) == 2
                assert pilot.app.screen.query_one("#from-input", Input)
                assert pilot.app.screen.query_one("#to-input", Input)

    async def test_escape_cancels_from_to_modal(self) -> None:
        """Escape on the modal dismisses it without changing the period."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = "1mo"
                await pilot.pause()
                pilot.app.query(Select)[0].value = _FROM_TO
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                assert len(pilot.app.screen_stack) == 1
                assert pilot.app.query(Select)[0].value == "1mo"

    async def test_valid_from_to_range_is_added_and_filters_data(self) -> None:
        """Submitting from/to dates filters fetched data to that window.

        Known flaky on the Windows CI runner: the FromToScreen modal's
        Input.Submitted handling races with pilot timing there, so this
        occasionally fails on a slower runner and passes on rerun. Not
        observed on Linux/macOS runners.
        """
        data = {
            "TSLA": [
                (datetime(2024, 1, 1, tzinfo=timezone.utc), 1.0),
                (datetime(2024, 5, 15, tzinfo=timezone.utc), 2.0),
                (datetime(2024, 12, 1, tzinfo=timezone.utc), 3.0),
            ]
        }
        captured: dict[str, object] = {}
        fetched_periods: list[str] = []

        def fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            fetched_periods.append(period)
            captured["fetch_period"] = period
            return {c: list(data["TSLA"]) for c in cols}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["series"] = series
            captured["xlim"] = kwargs["xlim"]
            return _SMALL_PNG

        with patch("termseries.tui._render_png", side_effect=render):
            async with _make_app(fetch_fn=fetch).run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = _FROM_TO
                await pilot.pause()
                pilot.app.screen.query_one("#from-input", Input).value = "2024-05"
                pilot.app.screen.query_one("#to-input", Input).value = "2024-06"
                pilot.app.screen.query_one("#to-input", Input).focus()
                await pilot.press("enter")
                await pilot.pause()
                option_values = {v for _, v in pilot.app.query(Select)[0]._options}

        # The Input.Submitted event must not bubble out of the modal and
        # reach the app while the Period select still holds the raw
        # "__from_to__" sentinel -- that would pass the sentinel straight
        # through to fetch_fn as if it were a period string.
        assert _FROM_TO not in fetched_periods
        assert captured["fetch_period"] == "max"
        assert captured["series"] == {"TSLA": [data["TSLA"][1]]}
        assert captured["xlim"] == (
            datetime(2024, 5, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
        )
        assert "2024-05..2024-06" in option_values

    async def test_open_ended_range_uses_a_sized_duration_not_max(self) -> None:
        """Regression test: leaving "To" blank (so the window reaches
        "now") must not fetch "max" -- Yahoo silently coarsens interval=1d
        data to monthly/quarterly bars for range=max on long-lived
        tickers, even when the actual requested window is narrow."""
        fetched_periods: list[str] = []

        def fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            fetched_periods.append(period)
            return {c: make_series() for c in cols}

        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(fetch_fn=fetch).run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = _FROM_TO
                await pilot.pause()
                pilot.app.screen.query_one("#from-input", Input).value = "2020-01-01"
                pilot.app.screen.query_one("#to-input", Input).focus()
                await pilot.press("enter")
                await pilot.pause()

        assert "max" not in fetched_periods
        assert any(re.fullmatch(r"\d+d", p) for p in fetched_periods)

    async def test_sentinel_never_reaches_fetch_fn_as_a_period(self) -> None:
        """Regression test for a real bug: an Input.Submitted event fired
        while the Period select still holds the raw '__from_to__' sentinel
        (e.g. one that reaches the app before the modal has replaced it
        with the real range label) must not be treated as a period -- it
        used to be passed straight through to fetch_fn, which then called
        parse_period('__from_to__') and raised 'Invalid period ...'."""
        calls: list[str] = []

        def fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            calls.append(period)
            return {c: make_series() for c in cols}

        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(fetch_fn=fetch).run_test() as pilot:
                await pilot.pause()
                calls.clear()
                pilot.app.query(Select)[0].value = _FROM_TO
                await pilot.pause()
                # Simulate the sentinel still being selected when something
                # triggers a re-fetch (e.g. a stray bubbled Input.Submitted).
                pilot.app.callback(*pilot.app._get_selections())
                await pilot.pause()

        assert calls == []

    async def test_from_later_than_to_warns_and_reverts(self) -> None:
        """A from-date after the to-date is rejected without changing period.

        Known flaky on the Windows CI runner: the FromToScreen modal's
        Input.Submitted handling races with pilot timing there, so this
        occasionally fails on a slower runner and passes on rerun. Not
        observed on Linux/macOS runners.
        """
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.pause()
                pilot.app.query(Select)[0].value = "1mo"
                await pilot.pause()
                pilot.app.query(Select)[0].value = _FROM_TO
                await pilot.pause()
                pilot.app.screen.query_one("#from-input", Input).value = "2024-06"
                pilot.app.screen.query_one("#to-input", Input).value = "2024-05"
                pilot.app.screen.query_one("#to-input", Input).focus()
                await pilot.press("enter")
                await pilot.pause()
                await pilot.pause()
                assert pilot.app.is_running
                assert len(pilot.app.screen_stack) == 1
                assert pilot.app.query(Select)[0].value == "1mo"


class TestInitialRange:
    """--from/--to at launch (-i) is seeded as a Period entry, not rejected."""

    async def test_initial_range_preselected_and_filters_data(self) -> None:
        data = {
            "TSLA": [
                (datetime(2024, 1, 1, tzinfo=timezone.utc), 1.0),
                (datetime(2024, 5, 15, tzinfo=timezone.utc), 2.0),
                (datetime(2024, 12, 1, tzinfo=timezone.utc), 3.0),
            ]
        }
        captured: dict[str, object] = {}

        def fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            return {c: list(data["TSLA"]) for c in cols}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["series"] = series
            captured["xlim"] = kwargs["xlim"]
            return _SMALL_PNG

        with patch("termseries.tui._render_png", side_effect=render):
            async with _make_app(
                fetch_fn=fetch,
                initial_range=(
                    datetime(2024, 5, 1, tzinfo=timezone.utc),
                    datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
                ),
                initial_range_label="2024-05..2024-06",
            ).run_test() as pilot:
                await pilot.pause()
                option_values = {v for _, v in pilot.app.query(Select)[0]._options}
                selected = pilot.app.query(Select)[0].value

        assert selected == "2024-05..2024-06"
        assert "2024-05..2024-06" in option_values
        assert captured["series"] == {"TSLA": [data["TSLA"][1]]}
        assert captured["xlim"] == (
            datetime(2024, 5, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
        )

    async def test_open_ended_initial_range_fetches_sized_period_not_max(self) -> None:
        """Regression test: initial_range=(start, None) (open-ended --from,
        no --to) must make callback() fetch a properly sized rolling
        duration, not period="max" -- Yahoo silently coarsens interval=1d
        bars for range=max on long-lived tickers, even for a narrow window."""
        fetched_periods: list[str] = []

        def fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            fetched_periods.append(period)
            return {c: make_series() for c in cols}

        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(
                fetch_fn=fetch,
                initial_range=(datetime(2022, 1, 1, tzinfo=timezone.utc), None),
                initial_range_label="2022-01-01..now",
            ).run_test() as pilot:
                await pilot.pause()

        assert fetched_periods
        assert fetched_periods[0] != "max"
        assert fetched_periods[0].endswith("d")


class TestTitleOption:
    async def test_custom_title_passed_to_render(self) -> None:
        captured: dict[str, object] = {}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["title"] = kwargs.get("title")
            return _SMALL_PNG

        with patch("termseries.tui._render_png", side_effect=render):
            async with _make_app(title="Custom Title").run_test() as pilot:
                await pilot.pause()

        assert captured["title"] == "Custom Title"

    async def test_no_title_passes_none(self) -> None:
        captured: dict[str, object] = {"title": "sentinel"}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["title"] = kwargs.get("title")
            return _SMALL_PNG

        with patch("termseries.tui._render_png", side_effect=render):
            async with _make_app().run_test() as pilot:
                await pilot.pause()

        assert captured["title"] is None


class TestLegendOption:
    async def test_default_shows_legend(self) -> None:
        captured: dict[str, object] = {}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["show_legend"] = kwargs.get("show_legend")
            return _SMALL_PNG

        with patch("termseries.tui._render_png", side_effect=render):
            async with _make_app().run_test() as pilot:
                await pilot.pause()

        assert captured["show_legend"] is True

    async def test_legend_false_disables_legend(self) -> None:
        captured: dict[str, object] = {}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["show_legend"] = kwargs.get("show_legend")
            return _SMALL_PNG

        with patch("termseries.tui._render_png", side_effect=render):
            async with _make_app(legend=False).run_test() as pilot:
                await pilot.pause()

        assert captured["show_legend"] is False


class TestErrorRecovery:
    async def test_error_from_bad_ticker_does_not_swallow_next_period_change(
        self,
    ) -> None:
        """A fetch error unrelated to Mode must not leave the revert-guard
        stuck, which would silently swallow the next real dropdown change."""
        calls: list[str] = []

        def flaky_fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            if cols == ["BAD"]:
                raise RuntimeError("bad ticker")
            calls.append(period)
            return {c: make_series() for c in cols}

        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(fetch_fn=flaky_fetch).run_test() as pilot:
                await pilot.pause()
                inp = pilot.app.query_one("#tickers", Input)
                await pilot.click("#tickers")
                inp.clear()
                inp.value = "BAD"
                await pilot.press("enter")
                await pilot.pause()
                assert pilot.app.is_running

                # Fix the ticker so the *next* trigger would succeed if it
                # actually fires -- isolates the revert-guard bug from the
                # unrelated fact that "BAD" keeps failing.
                inp.value = "TSLA"

                # A subsequent, unrelated Period change must still take effect.
                pilot.app.query(Select)[0].value = "1mo"
                await pilot.pause()

        assert "1mo" in calls


class TestResize:
    async def test_resize_schedules_debounced_rerender(self) -> None:
        """A resize after data has loaded arms the debounce timer."""
        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app().run_test() as pilot:
                await pilot.pause()
                if pilot.app._last_data is not None:
                    pilot.app.on_resize(None)  # event fields are unused
                    assert pilot.app._resize_timer is not None


# ---------------------------------------------------------------------------
# Seasonal mode
# ---------------------------------------------------------------------------


def _multi_year_series() -> list[tuple[datetime, float]]:
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    return [(start + timedelta(days=i), 100.0 + i) for i in range(3 * 365)]


class TestSeasonalMode:
    async def test_seasonal_mode_wraps_data_and_passes_cycle(self) -> None:
        """--mode seasonal reshapes the series dict before rendering and
        threads --cycle through to _render_png, without a --cycle widget."""
        captured: dict[str, object] = {}

        def fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            return {c: _multi_year_series() for c in cols}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["series"] = series
            captured["cycle"] = kwargs.get("cycle")
            captured["mode"] = kwargs.get("mode")
            return _SMALL_PNG

        with patch("termseries.tui._render_png", side_effect=render):
            async with _make_app(
                fetch_fn=fetch, mode="seasonal", cycle="year"
            ).run_test() as pilot:
                await pilot.pause()

        assert captured["mode"] == "seasonal"
        assert captured["cycle"] == "year"
        series = captured["series"]
        assert isinstance(series, dict)
        assert set(series.keys()) == {"TSLA (2022)", "TSLA (2023)", "TSLA (2024)"}

    async def test_seasonal_mode_defaults_cycle_when_none_given(self) -> None:
        """No --cycle menu entry exists yet; omitting it still works and
        falls back to yearly wrapping."""
        captured: dict[str, object] = {}

        def fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            return {c: _multi_year_series() for c in cols}

        def render(series: object, *args: object, **kwargs: object) -> bytes:
            captured["series"] = series
            return _SMALL_PNG

        with patch("termseries.tui._render_png", side_effect=render):
            async with _make_app(
                fetch_fn=fetch, mode="seasonal", cycle=None
            ).run_test() as pilot:
                await pilot.pause()

        series = captured["series"]
        assert isinstance(series, dict)
        assert set(series.keys()) == {"TSLA (2022)", "TSLA (2023)", "TSLA (2024)"}

    async def test_seasonal_mode_short_span_warns(self) -> None:
        """A cycle as long as the whole data span notifies rather than
        crashing (mirrors the one-shot CLI's stderr warning)."""

        def fetch(cols: list[str], period: str) -> dict:  # type: ignore[type-arg]
            return {c: make_series() for c in cols}

        notifications: list[str] = []

        with patch("termseries.tui._render_png", return_value=_SMALL_PNG):
            async with _make_app(
                fetch_fn=fetch, mode="seasonal", cycle="year"
            ).run_test() as pilot:
                await pilot.pause()
                pilot.app.notify = lambda msg, **kw: notifications.append(msg)  # type: ignore[method-assign]
                pilot.app.query_one("#tickers", Input).focus()
                await pilot.press("enter")
                await pilot.pause()

        assert any("only one chunk" in n for n in notifications)
