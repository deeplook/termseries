"""Interactive Textual TUI (launched with -i / --interactive)."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from termseries._render import _render_png
from termseries._terminal import (
    _copy_to_clipboard,
    _is_docker,
    _is_ssh_session,
    _parse_ratio,
    _png_dimensions,
)
from termseries._types import TimeSeries


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
) -> None:
    """Launch the Textual-based interactive chart viewer."""
    from PIL import Image as PILImage
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal
    from textual.widgets import Input, Select
    from textual.widgets._select import SelectOverlay
    from textual_image.widget import Image

    class TermSeriesApp(App):  # type: ignore[misc]
        BINDINGS = [
            ("escape", "quit", "Quit"),
            ("ctrl+d", "quit", "Quit"),
            ("left", "focus_previous", "Previous"),
            ("right", "focus_next", "Next"),
            ("ctrl+y", "yank", "Copy"),
        ]

        _last_png: bytes | None = None
        _last_mode: str = "absolute"
        _reverting: bool = False

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
        """

        def compose(self) -> ComposeResult:
            has_columns = bool(initial_columns)
            with Horizontal(id="menu"):
                periods = period_choices
                s1 = Select.from_values(periods, prompt="Period", allow_blank=True)
                if period and period in periods:
                    s1.value = period
                elif has_columns:
                    s1.value = periods[0]
                max_len1 = max(len(v) for v in [*periods, "Period"])
                s1.styles.width = max_len1 + 6
                yield s1

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
        ) -> None:
            if period is None:
                return
            chart = self.query_one("#chart", Image)
            if ratio == "fit":
                w_cells = chart.size.width or self.size.width
                h_cells = chart.size.height or (self.size.height - 2)
                width_in = 12.0
                height_in = width_in * (h_cells * 2) / w_cells
                figsize: tuple[float, float] | None = (width_in, height_in)
                ratio_tuple = (4, 1)
            else:
                ratio_tuple = _parse_ratio(ratio) if ratio else (4, 1)
                figsize = None
            if ratio == "fit":
                chart.styles.width = "1fr"
                chart.styles.height = "1fr"
            else:
                chart.styles.width = "auto"
                chart.styles.height = "auto"
            tickers_str = self.query_one("#tickers", Input).value.strip()
            if not tickers_str:
                self.notify("Enter at least one ticker symbol", severity="warning")
                return
            columns = tickers_str.split()
            try:
                data = fetch_fn(columns, period)
                png_bytes = _render_png(
                    data,
                    ratio_tuple,
                    period,
                    figsize=figsize,
                    color_cycle=color_cycle,
                    mode=mode or "absolute",
                    value_unit=value_unit,
                    style_override=style_override,
                )
            except (ValueError, RuntimeError) as e:
                self.notify(str(e), severity="warning")
                self._reverting = True
                mode_select = self.query(Select)[2]
                mode_select.value = self._last_mode
                return
            self._last_mode = mode or "absolute"
            self._last_png = png_bytes
            img = PILImage.open(BytesIO(png_bytes))
            chart.image = img

        def _get_selections(
            self,
        ) -> tuple[str | None, str | None, str | None, str | None]:
            selects = self.query(Select)
            period: str | None = (
                str(selects[0].value) if selects[0].value != Select.BLANK else None
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

        def on_mount(self) -> None:
            for sel in self.query(Select):
                sel.query_one(SelectOverlay).disable_option_at_index(0)
            if initial_columns:
                self.callback(*self._get_selections())

        def on_select_changed(self, event: Select.Changed) -> None:  # type: ignore[type-arg,unused-ignore]
            if self._reverting:
                self._reverting = False
                return
            self.callback(*self._get_selections())

        def on_input_submitted(self, event: Input.Submitted) -> None:
            self.callback(*self._get_selections())

    TermSeriesApp().run()
