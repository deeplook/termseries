"""Interactive Textual TUI (launched with -i / --interactive)."""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

from termseries.period import parse_period, resolve_tz, xlim_now
from termseries.render import _render_png
from termseries.terminal import (
    _copy_to_clipboard,
    _is_docker,
    _is_ghostty,
    _is_ssh_session,
    _parse_ratio,
    _png_dimensions,
)
from termseries.types import TimeSeries


def _build_app(
    initial_columns: list[str] | None = None,
    *,
    period_choices: list[str],
    period: str | None = None,
    ratio: tuple[int, int] | None = None,
    mode: str | None = None,
    colors: str | None = None,
    fetch_fn: Callable[[list[str], str], dict[str, TimeSeries]],
    value_unit: str = "USD",
    style_override: Path | None = None,
    reload_interval: int = 0,
    tz: str = "UTC",
    line_style: str = "linear",
    anchor_now: bool = False,
    theme: str = "auto",
) -> Any:
    """Build and return the TermSeriesApp without running it.

    Useful for testing via ``App.run_test()``.  All parameters are identical
    to :func:`_run_interactive`.
    """
    from PIL import Image as PILImage
    from textual import events
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.screen import ModalScreen
    from textual.timer import Timer
    from textual.widgets import Input, Select, Static
    from textual.widgets._select import SelectOverlay

    if _is_ghostty():
        from textual.geometry import Region
        from textual.strip import Strip
        from textual.widget import Widget

        class Image(Widget):  # type: ignore[misc,no-redef]
            """Placeholder widget for Ghostty inline image rendering.

            The actual image is sent out-of-band by TermSeriesApp._img_cycle()
            via driver.write() after every Textual render cycle.
            """

            can_focus = False

            def __init__(
                self,
                image: PILImage.Image | None = None,
                *,
                name: str | None = None,
                id: str | None = None,
                classes: str | None = None,
                disabled: bool = False,
            ) -> None:
                super().__init__(name=name, id=id, classes=classes, disabled=disabled)
                self.png_bytes: bytes | None = None
                self._image_version: int = 0
                if image is not None:
                    self.image = image

            @property  # type: ignore[no-redef]
            def image(self) -> PILImage.Image | None:
                return getattr(self, "_pil_image", None)

            @image.setter
            def image(self, value: PILImage.Image | None) -> None:
                self._pil_image = value  # type: ignore[attr-defined]
                self.png_bytes = None
                if value is not None:
                    buf = BytesIO()
                    value.save(buf, format="PNG")
                    self.png_bytes = buf.getvalue()
                self._image_version += 1
                self.refresh()

            def render_lines(self, crop: Region) -> list[Strip]:
                return [Strip([])] * crop.height

    else:
        from textual_image.widget import Image  # type: ignore[no-redef,assignment]

    _CUSTOM = "__custom__"

    _HELP_TEXT = """\
[bold]termseries — interactive mode[/bold]

[bold cyan]Controls[/bold cyan]
  [bold]Tab[/bold]             Move focus between controls
  [bold]←  →[/bold]            Move focus between controls
  [bold]↑  ↓[/bold]            Navigate dropdown options
  [bold]Enter[/bold]           Select current option

[bold cyan]Chart[/bold cyan]
  [bold]Ctrl + y[/bold]        Copy current plot to clipboard
  [bold]Ctrl + r[/bold]        Toggle auto-reload

[bold cyan]Help & Quit[/bold cyan]
  [bold]?  Ctrl + h[/bold]     Show this help screen
  [bold]Escape[/bold]          Quit
  [bold]Ctrl + d[/bold]        Quit
  [bold]Ctrl + c[/bold]        Quit (press twice to confirm)

[dim]Press any key to close[/dim]\
"""

    class HelpScreen(ModalScreen):  # type: ignore
        CSS = """
        HelpScreen {
            align: center middle;
        }
        #help-panel {
            background: $surface;
            border: round $primary;
            padding: 1 3;
            width: auto;
            height: auto;
        }
        """

        def compose(self) -> ComposeResult:
            yield Static(_HELP_TEXT, id="help-panel")

        def on_key(self, event: events.Key) -> None:
            event.stop()
            self.dismiss()

    class TermSeriesApp(App):  # type: ignore
        BINDINGS = [
            ("escape", "quit", "Quit"),
            ("ctrl+d", "quit", "Quit"),
            ("ctrl+c", "request_quit", "Quit"),
            # override Textual's built-in ctrl+q quit
            Binding("ctrl+q", "noop", show=False, priority=True),
            ("?", "show_help", "Help"),
            ("ctrl+h", "show_help", "Help"),
            ("left", "focus_previous", "Previous"),
            ("right", "focus_next", "Next"),
            ("ctrl+y", "yank", "Copy"),
            ("ctrl+r", "toggle_reload", "Reload"),
        ]

        _last_png: bytes | None = None
        _last_ctrl_c: float | None = None
        _last_data: dict[str, TimeSeries] | None = None
        _last_mode: str = "absolute"
        _reverting: bool = False
        _reload_timer: Timer | None = None
        _reload_interval: int = reload_interval or 30
        _resize_timer: Timer | None = None
        # Ghostty out-of-band image state (only used when _is_ghostty())
        _img_drawn: bool = False
        _last_img_version: int = -1
        _overlay_was_active: bool = False

        CSS = """
        Select {
            border: none;
            margin-right: 1;
        }
        SelectCurrent {
            border: none;
            background: #4a6a8a;
        }
        Select:focus SelectCurrent {
            background: #6a9aca;
        }
        #menu {
            height: auto;
        }
        #tickers {
            border: none;
            background: #4a6a8a;
            width: 1fr;
            height: 1;
        }
        #tickers:focus {
            background: #6a9aca;
        }
        #chart {
            width: 1fr;
            height: 1fr;
        }
        #custom-period {
            display: none;
            width: 20;
            height: 1;
            border: none;
            background: #6a9aca;
            padding: 0 1;
        }
        """

        _last_period_value: str | None = None

        def compose(self) -> ComposeResult:
            has_columns = bool(initial_columns)
            with Horizontal(id="menu"):
                periods = list(period_choices)
                if period and period not in periods:
                    periods.append(period)
                options = [(p, p) for p in periods] + [("custom...", _CUSTOM)]
                s1: Select[str] = Select(options, prompt="Period", allow_blank=True)
                if period and period in periods:
                    s1.value = period
                elif has_columns:
                    s1.value = periods[0]
                max_len1 = max(len(v) for v in [*periods, "Period", "custom..."])
                s1.styles.width = max_len1 + 6
                yield s1
                yield Input(placeholder="e.g. 14d, 2w", id="custom-period")

                ratios = ["fit", "4:1", "3:1", "2:1"]
                s2 = Select.from_values(ratios, prompt="Ratio", allow_blank=True)
                if ratio:
                    ratio_str = f"{ratio[0]}:{ratio[1]}"
                    if ratio_str in ratios:
                        s2.value = ratio_str
                    else:
                        s2 = Select.from_values(
                            [ratio_str, *ratios], prompt="Ratio", allow_blank=True
                        )
                        s2.value = ratio_str
                elif has_columns:
                    s2.value = "fit"
                max_len2 = max(len(v) for v in [*ratios, "Ratio"])
                s2.styles.width = max_len2 + 6
                yield s2

                modes = [
                    "absolute",
                    "indexed",
                    "log",
                    "drawdown",
                    "returns",
                    "relative",
                    "cumulative",
                    "delta",
                ]
                s_mode = Select.from_values(modes, prompt="Mode", allow_blank=True)
                s_mode.value = mode if mode and mode in modes else "absolute"
                max_len_mode = max(len(v) for v in [*modes, "Mode"])
                s_mode.styles.width = max_len_mode + 6
                yield s_mode

                color_options = [
                    "tab10",
                    "Set1",
                    "Set2",
                    "Dark2",
                    "Accent",
                    "Pastel1",
                    "tab20",
                ]
                s3 = Select.from_values(
                    color_options, prompt="Colors", allow_blank=True
                )
                s3.value = colors if colors and colors in color_options else "tab10"
                max_len3 = max(len(v) for v in [*color_options, "Colors"])
                s3.styles.width = max_len3 + 6
                yield s3

                default_text = " ".join(initial_columns) if initial_columns else ""
                yield Input(placeholder="...", value=default_text, id="tickers")

            yield Image(id="chart")

        def callback(
            self,
            period: str | None,
            ratio: str | None,
            mode: str | None = None,
            color_cycle: str | None = None,
            *,
            data: dict[str, TimeSeries] | None = None,
        ) -> None:
            if period is None:
                return
            chart = self.query_one("#chart", Image)
            from textual_image._terminal import get_cell_size

            cell = get_cell_size()
            w_cells = self.size.width
            h_cells = self.size.height - 2  # subtract menu row
            w_px = max(w_cells * cell.width, 1)
            h_px = max(h_cells * cell.height, 1)
            # Keep figure at a fixed 12-inch width and scale DPI to hit the
            # target pixel width.  This keeps font sizes proportional.
            _base_width_in = 12.0
            _save_dpi = w_px / _base_width_in
            if ratio == "fit":
                # Pass pixel dimensions as the ratio so height scales correctly.
                ratio_tuple = (w_px, h_px)
                chart.styles.width = "1fr"
                chart.styles.height = "1fr"
            else:
                ratio_tuple = _parse_ratio(ratio) if ratio else (4, 1)
                chart.styles.width = "auto"
                chart.styles.height = "auto"
            tickers_str = self.query_one("#tickers", Input).value.strip()
            if not tickers_str:
                self.notify("Enter at least one ticker symbol", severity="warning")
                return
            columns = tickers_str.split()
            try:
                if data is None:
                    data = fetch_fn(columns, period)
                png_bytes = _render_png(
                    data,
                    ratio_tuple,
                    period,
                    color_cycle=color_cycle,
                    mode=mode or "absolute",
                    value_unit=value_unit,
                    style_override=style_override,
                    tz=tz,
                    line_style=line_style,
                    xlim=xlim_now(period, data, tz=resolve_tz(tz))
                    if anchor_now
                    else None,
                    theme=theme,
                    save_dpi=_save_dpi,
                )
            except (ValueError, RuntimeError) as e:
                self.notify(str(e), severity="warning")
                mode_select = self.query(Select)[2]
                # Only arm the revert guard if this assignment will actually
                # change the value: Select.value doesn't emit Changed for a
                # no-op assignment, so _reverting would otherwise get stuck
                # True and silently swallow the next real dropdown change.
                if mode_select.value != self._last_mode:
                    self._reverting = True
                    mode_select.value = self._last_mode
                return
            self._last_data = data
            self._last_mode = mode or "absolute"
            self._last_png = png_bytes
            img = PILImage.open(BytesIO(png_bytes))
            chart.image = img

        def _get_selections(
            self,
        ) -> tuple[str | None, str | None, str | None, str | None]:
            selects = self.query(Select)
            raw_period = selects[0].value
            period: str | None = (
                str(raw_period) if raw_period not in (Select.BLANK, _CUSTOM) else None
            )
            ratio: str | None = (
                str(selects[1].value) if selects[1].value != Select.BLANK else None
            )
            mode: str | None = (
                str(selects[2].value) if selects[2].value != Select.BLANK else None
            )
            color_cycle: str | None = (
                str(selects[3].value) if selects[3].value != Select.BLANK else None
            )
            return period, ratio, mode, color_cycle

        def action_noop(self) -> None:
            pass

        def action_show_help(self) -> None:
            self.push_screen(HelpScreen())

        _QUIT_NOTIFY_TIMEOUT = 3.0

        def action_request_quit(self) -> None:
            now = time.monotonic()
            if self._last_ctrl_c is not None and now - self._last_ctrl_c < 2.0:
                self.exit()
            else:
                self._last_ctrl_c = now
                self.notify(
                    "Press Ctrl+C again to quit", timeout=self._QUIT_NOTIFY_TIMEOUT
                )
                self.set_timer(self._QUIT_NOTIFY_TIMEOUT + 0.1, self._redraw_chart)

        def _redraw_chart(self) -> None:
            self.query_one("#chart", Image).refresh()

        def action_yank(self) -> None:
            if self._last_png is None:
                self.notify("No plot to copy", severity="warning")
                return
            try:
                _copy_to_clipboard(self._last_png)
                w, h = _png_dimensions(self._last_png)
                msg = f"Plot ({w}x{h}) copied to clipboard"
                if _is_docker():
                    msg += " (Docker -- may not reach your local machine)"
                elif _is_ssh_session():
                    msg += " (remote -- may not reach your local machine)"
                self.notify(msg)
            except Exception as e:
                self.notify(f"Copy failed: {e}", severity="error")

        def action_toggle_reload(self) -> None:
            if self._reload_timer is not None:
                self._reload_timer.stop()
                self._reload_timer = None
                self.notify("Auto-reload off")
            else:
                self._reload_timer = self.set_interval(
                    self._reload_interval, self._reload_tick
                )
                self.notify(f"Auto-reload every {self._reload_interval}s")

        def _reload_tick(self) -> None:
            try:
                self.callback(*self._get_selections())
            except Exception as e:
                self.notify(f"Reload failed: {e}", severity="warning")

        def on_mount(self) -> None:
            for sel in self.query(Select):
                sel.query_one(SelectOverlay).disable_option_at_index(0)
            if initial_columns:
                self.callback(*self._get_selections())
            if reload_interval > 0:
                self._reload_timer = self.set_interval(
                    reload_interval, self._reload_tick
                )
            if _is_ghostty():
                self.call_after_refresh(self._img_cycle)

        def _img_cycle(self) -> None:
            """App-level TGP image management for Ghostty.

            Self-rescheduled after every render via call_after_refresh.
            Sends the chart via Kitty TGP APC sequences through driver.write().
            TGP images are persistent overlays (z=0) above terminal text.
            We delete them while any overlay is active so dropdown/modal text
            is not obscured, then redraw automatically once the overlay closes.
            """
            if not self._driver:
                self.call_after_refresh(self._img_cycle)
                return
            driver = self._driver
            try:
                chart = self.query_one("#chart", Image)
            except Exception:
                self.call_after_refresh(self._img_cycle)
                return

            overlay_active = len(self.screen_stack) > 1 or any(
                w.display for w in self.query(SelectOverlay)
            )

            if overlay_active:
                if self._img_drawn:
                    # Delete all TGP images so the dropdown/modal text is visible.
                    driver.write("\x1b_Ga=d,d=a\x1b\\")
                    driver.flush()
                    self._img_drawn = False
                self._overlay_was_active = True
            elif chart.png_bytes is not None:
                version = chart._image_version
                needs_draw = (
                    not self._img_drawn
                    or version != self._last_img_version
                    or self._overlay_was_active
                )
                if needs_draw:
                    r = chart.region
                    # Position cursor at chart top-left, then send TGP image.
                    driver.write(f"\x1b7\x1b[{r.y + 1};{r.x + 1}H")
                    b64 = base64.b64encode(chart.png_bytes).decode("ascii")
                    first = True
                    while b64:
                        chunk, b64 = b64[:4096], b64[4096:]
                        m = 1 if b64 else 0
                        if first:
                            driver.write(f"\x1b_Ga=T,f=100,m={m};{chunk}\x1b\\")
                            first = False
                        else:
                            driver.write(f"\x1b_Gm={m};{chunk}\x1b\\")
                    driver.write("\x1b8")
                    driver.flush()
                    self._img_drawn = True
                    self._last_img_version = version
                self._overlay_was_active = False

            self.call_after_refresh(self._img_cycle)

        def on_select_changed(self, event: Select.Changed) -> None:  # type: ignore[type-arg,unused-ignore]
            if self._reverting:
                self._reverting = False
                return
            period_select: Select[str] = self.query(Select)[0]
            if period_select.value == _CUSTOM:
                custom_input = self.query_one("#custom-period", Input)
                custom_input.value = ""
                custom_input.display = True
                custom_input.focus()
                return
            self._last_period_value = (
                str(period_select.value)
                if period_select.value != Select.BLANK
                else None
            )
            self.callback(*self._get_selections())

        def _hide_custom_input(self) -> None:
            self.query_one("#custom-period", Input).display = False

        def _accept_custom_period(self, value: str) -> None:
            period_select: Select[str] = self.query(Select)[0]
            self._hide_custom_input()
            if not value:
                self._reverting = True
                period_select.value = (
                    self._last_period_value if self._last_period_value else Select.BLANK
                )
                return
            try:
                parse_period(value)
            except ValueError as e:
                self.notify(str(e), severity="warning")
                self._reverting = True
                period_select.value = (
                    self._last_period_value if self._last_period_value else Select.BLANK
                )
                return
            # Add the custom value to the dropdown if not already present
            current_options = list(period_select._options)
            existing_values = {v for _, v in current_options}
            if value not in existing_values:
                new_options = [o for o in current_options if o[1] != _CUSTOM] + [
                    (value, value),
                    ("custom...", _CUSTOM),
                ]
                period_select.set_options(new_options)  # type: ignore[arg-type]
            self._reverting = True
            period_select.value = value
            self._last_period_value = value
            self._reverting = False
            self.callback(*self._get_selections())

        def on_input_submitted(self, event: Input.Submitted) -> None:
            if event.input.id == "custom-period":
                self._accept_custom_period(event.value.strip())
            else:
                self.callback(*self._get_selections())

        def on_key(self, event: events.Key) -> None:
            if event.key == "escape":
                custom_input = self.query_one("#custom-period", Input)
                if custom_input.display:
                    self._accept_custom_period("")
                    event.prevent_default()
                    event.stop()

        def _debounced_rerender(self) -> None:
            self._resize_timer = None
            # self.query() targets the topmost screen; skip while a modal
            # (e.g. HelpScreen) is on top, since it has no Select widgets.
            if self._last_data is not None and len(self.screen_stack) == 1:
                self.callback(*self._get_selections(), data=self._last_data)

        def on_resize(self, event: events.Resize) -> None:
            if self._last_data is None:
                return
            if self._resize_timer is not None:
                self._resize_timer.stop()
            self._resize_timer = self.set_timer(0.15, self._debounced_rerender)

    return TermSeriesApp()


def _run_interactive(
    initial_columns: list[str] | None = None,
    *,
    period_choices: list[str],
    period: str | None = None,
    ratio: tuple[int, int] | None = None,
    mode: str | None = None,
    colors: str | None = None,
    fetch_fn: Callable[[list[str], str], dict[str, TimeSeries]],
    value_unit: str = "USD",
    style_override: Path | None = None,
    reload_interval: int = 0,
    tz: str = "UTC",
    line_style: str = "linear",
    anchor_now: bool = False,
    theme: str = "auto",
) -> None:
    """Launch the Textual-based interactive chart viewer."""
    _build_app(
        initial_columns,
        period_choices=period_choices,
        period=period,
        ratio=ratio,
        mode=mode,
        colors=colors,
        fetch_fn=fetch_fn,
        value_unit=value_unit,
        style_override=style_override,
        reload_interval=reload_interval,
        tz=tz,
        line_style=line_style,
        anchor_now=anchor_now,
        theme=theme,
    ).run()
