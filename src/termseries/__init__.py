"""
Render time-series data as wide matplotlib plots.

The rendering engine (`_render_png`) is data-source agnostic -- it accepts a
dict of pre-fetched ``TimeSeries`` data and can be reused for any numeric time
series (e.g. stock prices, sensor readings, weather data).  A built-in Yahoo
Finance adapter (`fetch_yahoo_series`) provides stock close-price data out of
the box.

Supports both a one-shot CLI mode and an interactive Textual TUI.  Data sources
are exposed as subcommands (e.g. ``yahoo``); shared options like ``--mode``,
``--ratio``, ``--colors``, ``-c``, and ``-i`` live on the parent command.

Shared options (before subcommand):
- ``--ratio W:H`` controls figure aspect ratio (default: 4:1).
- ``--mode`` selects charting mode: absolute, indexed (rebased to 100%),
  log (logarithmic y-axis), drawdown (% decline from running peak),
  returns (day-over-day % change), or relative (price ratio of exactly
  2 series).
- ``--colors`` picks a matplotlib color cycle.
- ``-c`` / ``--copy`` copies the rendered plot to the system clipboard
  (macOS, Windows, Linux/X11, Linux/Wayland).  Warns when running over SSH.
- ``-i`` / ``--interactive`` launches a Textual TUI with dropdowns for period,
  ratio, mode, and colors, plus a series-name input field.  All other CLI
  options pre-select the corresponding TUI controls, and the plot is rendered
  immediately when series names are provided.  Press Ctrl+Y in the TUI to copy
  the current plot to the clipboard.

yahoo subcommand:
- Positional args are one-or-more ticker symbols.  Duplicate tickers are
  removed while preserving order.
- ``--period`` selects Yahoo's chart range (default: 7d).

Terminal output behavior (non-interactive):
- Auto-detects terminal image protocol support and displays plots inline:
  - Kitty (Terminal Graphics Protocol) -- detected via TERM/TERM_PROGRAM
  - iTerm2 (Inline Images Protocol) -- detected via TERM_PROGRAM/LC_TERMINAL
  - Sixel -- detected for WezTerm, foot, VS Code terminal, mlterm, xterm
- When no supported protocol is detected (or inline output is disabled),
  writes a PNG file (with a descriptive filename) and prints where it was
  written.

Environment variables:
- ``TERMSERIES_FORCE_INLINE=1``: try inline output even on unrecognized
  terminals (falls back to iTerm2 escape sequence).
- ``TERMSERIES_NO_INLINE=1``: never print inline image (always write PNG).
- ``TERMSERIES_DARK=1``: force dark plot theme/background.
- ``TERMSERIES_LIGHT=1``: force light plot theme/background.
"""

from __future__ import annotations

__version__ = "0.1.0"

import base64
import json
import os
import struct
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from typing import Annotated

import matplotlib
import typer

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

TimeSeries = list[tuple[datetime, float]]


# ---------------------------------------------------------------------------
# Enums for constrained CLI choices
# ---------------------------------------------------------------------------


class Mode(str, Enum):
    absolute = "absolute"
    indexed = "indexed"
    log = "log"
    drawdown = "drawdown"
    returns = "returns"
    relative = "relative"


class ColorCycle(str, Enum):
    tab10 = "tab10"
    Set1 = "Set1"
    Set2 = "Set2"
    Dark2 = "Dark2"
    Accent = "Accent"
    Pastel1 = "Pastel1"
    tab20 = "tab20"


class YahooPeriod(str, Enum):
    d1 = "1d"
    d5 = "5d"
    d7 = "7d"
    mo1 = "1mo"
    mo3 = "3mo"
    mo6 = "6mo"
    y1 = "1y"
    y2 = "2y"
    y5 = "5y"
    y10 = "10y"
    ytd = "ytd"
    max = "max"


# ---------------------------------------------------------------------------
# Terminal image output helpers
# ---------------------------------------------------------------------------


def _print_kitty_png(png_bytes: bytes) -> None:
    """Print a PNG inline using Kitty's Terminal Graphics Protocol."""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    first = True
    while b64:
        chunk, b64 = b64[:4096], b64[4096:]
        m = 1 if b64 else 0
        if first:
            sys.stdout.write(f"\033_Ga=T,f=100,m={m};{chunk}\033\\")
            first = False
        else:
            sys.stdout.write(f"\033_Gm={m};{chunk}\033\\")
    sys.stdout.write("\n")


def _print_sixel_png(png_bytes: bytes) -> None:
    """Print a PNG inline as Sixel graphics."""
    from PIL import Image as PILImage
    from textual_image.renderable.sixel import (  # type: ignore[attr-defined]
        image_to_sixels,
    )

    img = PILImage.open(BytesIO(png_bytes))
    sys.stdout.write(image_to_sixels(img))
    sys.stdout.write("\n")


def _print_iterm2_png(png_bytes: bytes) -> None:
    """Print a PNG to iTerm2 using the Inline Images Protocol.

    Uses width=100% to fill all available horizontal space.
    """
    b64 = base64.b64encode(png_bytes).decode("ascii")
    sys.stdout.write("\033]1337;File=inline=1;width=100%;preserveAspectRatio=1:")
    sys.stdout.write(b64)
    sys.stdout.write("\a\n")


def _is_kitty() -> bool:
    """Return True if running inside the Kitty terminal."""
    return (
        os.environ.get("TERM", "").startswith("xterm-kitty")
        or os.environ.get("TERM_PROGRAM") == "kitty"
    )


def _is_iterm2() -> bool:
    """Return True if the current process appears to be running under iTerm2."""
    return (
        os.environ.get("TERM_PROGRAM") == "iTerm.app"
        or os.environ.get("LC_TERMINAL") == "iTerm2"
        or "ITERM_SESSION_ID" in os.environ
    )


def _is_sixel_terminal() -> bool:
    """Return True for terminals known to support Sixel graphics."""
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program in ("WezTerm", "vscode"):
        return True
    term = os.environ.get("TERM", "")
    return term.startswith("foot") or term.startswith("mlterm") or term == "xterm"


def _png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    """Read width and height from a PNG's IHDR chunk."""
    w, h = struct.unpack(">II", png_bytes[16:24])
    return w, h


def _is_ssh_session() -> bool:
    """Return True if running inside an SSH session."""
    return bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"))


def _copy_to_clipboard(png_bytes: bytes) -> None:
    """Copy PNG image bytes to the system clipboard.

    Uses platform-specific commands via subprocess.
    """
    if sys.platform == "darwin":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            tmp = f.name
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    "set the clipboard to "
                    f'(read (POSIX file "{tmp}") as \u00abclass PNGf\u00bb)',
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        finally:
            os.unlink(tmp)
    elif sys.platform == "win32":
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes)
            tmp = f.name
        try:
            ps_script = (
                "Add-Type -Assembly System.Windows.Forms;"
                "[System.Windows.Forms.Clipboard]::SetImage("
                f"[System.Drawing.Image]::FromFile('{tmp}'))"
            )
            subprocess.run(["powershell", "-Command", ps_script], check=True)
        finally:
            os.unlink(tmp)
    elif os.environ.get("WAYLAND_DISPLAY"):
        subprocess.run(
            ["wl-copy", "--type", "image/png"],
            input=png_bytes,
            check=True,
        )
    else:
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png"],
            input=png_bytes,
            check=True,
        )


def _parse_ratio(value: str) -> tuple[int, int]:
    """Parse ratio strings like ``"4:1"`` or ``"16:10"`` into ``(w, h)``."""
    s = value.strip()
    parts = s.split(":")
    if len(parts) != 2:
        raise typer.BadParameter('ratio must look like "4:1" or "16:10"')
    w_s, h_s = (p.strip() for p in parts)
    if not w_s or not h_s:
        raise typer.BadParameter('ratio must look like "4:1" or "16:10"')
    try:
        w = int(w_s)
        h = int(h_s)
    except ValueError as e:
        raise typer.BadParameter('ratio must use integers like "4:1"') from e
    if w <= 0 or h <= 0:
        raise typer.BadParameter("ratio components must be positive")
    return w, h


def _detect_dark_terminal() -> bool:
    """Best-effort guess whether the terminal background is dark.

    Detection sources (in order):
    - TERMSERIES_DARK / TERMSERIES_LIGHT overrides
    - COLORFGBG (common in many terminals; last component is background color)
    - iTerm2 profile name hints
    - fallback: assume dark
    """
    if os.environ.get("TERMSERIES_DARK") == "1":
        return True
    if os.environ.get("TERMSERIES_LIGHT") == "1":
        return False

    colorfgbg = os.environ.get("COLORFGBG")
    if colorfgbg:
        parts = colorfgbg.split(";")
        try:
            bg = int(parts[-1])
        except ValueError:
            bg = None
        if bg is not None and 0 <= bg <= 15:
            return bg <= 8

    iterm_profile = (os.environ.get("ITERM_PROFILE") or "").lower()
    if "dark" in iterm_profile:
        return True
    return "light" not in iterm_profile


# ---------------------------------------------------------------------------
# Yahoo Finance data source
# ---------------------------------------------------------------------------


def _fetch_closes(ticker: str, period: str) -> list[tuple[datetime, float]]:
    """Return list of (UTC datetime, close) points for the requested period."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?range={period}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError(f"{ticker}: unexpected Yahoo response: {payload!r}")

    series = result[0]
    timestamps = series.get("timestamp") or []
    quotes = ((series.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quotes.get("close") or []

    points: list[tuple[datetime, float]] = []
    for ts, close in zip(timestamps, closes, strict=False):
        if close is None:
            continue
        points.append((datetime.fromtimestamp(ts, tz=timezone.utc), float(close)))

    if not points:
        raise RuntimeError(f"{ticker}: no close data returned for period={period}.")

    return points


def fetch_yahoo_series(tickers: list[str], period: str) -> dict[str, TimeSeries]:
    """Fetch close-price time series from Yahoo Finance for each ticker.

    Returns a dict mapping ticker symbol to its list of (datetime, close) points.
    Tickers are deduplicated and uppercased; order is preserved.
    """
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not tickers:
        raise ValueError(
            "No ticker symbols provided. Pass at least one ticker (e.g. TSLA)."
        )
    return {ticker: _fetch_closes(ticker, period) for ticker in tickers}


# ---------------------------------------------------------------------------
# Rendering (data-source agnostic)
# ---------------------------------------------------------------------------


def _render_png(
    series: dict[str, TimeSeries],
    ratio: tuple[int, int],
    period_label: str,
    figsize: tuple[float, float] | None = None,
    color_cycle: str | None = None,
    mode: str = "absolute",
    value_unit: str = "USD",
) -> bytes:
    """Render a time-series chart and return PNG bytes.

    This function is data-source agnostic -- it accepts pre-fetched data and
    does not perform any network I/O.

    Parameters
    ----------
    series : dict[str, TimeSeries]
        Mapping from series name (e.g. "TSLA", "Living Room") to data points.
    ratio : tuple[int, int]
        Aspect ratio (width, height) for the figure.
    period_label : str
        Human-readable period shown in the title (e.g. "7d", "last 24h").
    figsize : tuple[float, float] | None
        Explicit figure size in inches; overrides *ratio* when set.
    color_cycle : str | None
        Matplotlib colormap name for the line color cycle.
    mode : str
        Chart mode (absolute, indexed, log, drawdown, returns, relative).
    value_unit : str
        Unit label for the y-axis (e.g. "USD", "C"). Defaults to "USD".
    """
    names = list(series.keys())
    if not names:
        raise ValueError("No data series provided. Pass at least one series.")

    dark = _detect_dark_terminal()
    plt.style.use("dark_background" if dark else "default")

    if figsize:
        width_in, height_in = figsize
    else:
        ratio_w, ratio_h = ratio
        width_in = 12.0
        height_in = width_in * (ratio_h / ratio_w)
    if color_cycle:
        cmap = matplotlib.colormaps[color_cycle]
        plt.rcParams["axes.prop_cycle"] = plt.cycler(  # type: ignore[attr-defined]
            color=[cmap(i) for i in range(cmap.N)]
            if cmap.N <= 20
            else [cmap(x) for x in [i / 10 for i in range(10)]]
        )
    fig, ax = plt.subplots(figsize=(width_in, height_in), constrained_layout=True)
    if dark:
        fig.patch.set_facecolor("black")
        ax.set_facecolor("black")
    else:
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

    if mode == "relative":
        if len(names) != 2:
            raise ValueError(
                "Relative mode requires exactly 2 series (e.g. AAPL MSFT)."
            )
        pts_a = series[names[0]]
        pts_b = series[names[1]]
        closes_a = {dt.date(): c for dt, c in pts_a}
        closes_b = {dt.date(): c for dt, c in pts_b}
        common = sorted(closes_a.keys() & closes_b.keys())
        if not common:
            raise RuntimeError(f"No overlapping dates for {names[0]} and {names[1]}.")
        xs = common
        ys = [closes_a[d] / closes_b[d] for d in common]
        ax.plot(xs, ys, marker="o", linewidth=2, label=f"{names[0]}/{names[1]}")  # type: ignore[arg-type]
    else:
        for name, points in series.items():
            xs = [dt.date() for dt, _ in points]
            ys = [close for _, close in points]
            if mode == "indexed" and ys:
                base = ys[0]
                ys = [100.0 * y / base for y in ys]
            elif mode == "drawdown" and ys:
                peak = ys[0]
                dd = []
                for y in ys:
                    peak = max(peak, y)
                    dd.append((y / peak - 1.0) * 100.0)
                ys = dd
            elif mode == "returns" and len(ys) >= 2:
                xs = xs[1:]
                ys = [(ys[i] / ys[i - 1] - 1.0) * 100.0 for i in range(1, len(ys))]
            ax.plot(xs, ys, marker="o", linewidth=2, label=name)  # type: ignore[arg-type]

    if mode == "log":
        ax.set_yscale("log")

    title_labels = {
        "absolute": "Close",
        "indexed": "Indexed",
        "log": "Close (log)",
        "drawdown": "Drawdown",
        "returns": "Daily Returns",
        "relative": f"{names[0]}/{names[1]}" if mode == "relative" else "",
    }
    ax.set_title(
        f"{title_labels.get(mode, 'Close')} ({period_label}): {', '.join(names)}"
    )
    ax.set_xlabel("Date (UTC)")
    ylabel = {
        "absolute": f"Close ({value_unit})",
        "indexed": "% of start",
        "log": f"Close ({value_unit}, log)",
        "drawdown": "% from peak",
        "returns": "Daily change (%)",
        "relative": f"{names[0]}/{names[1]} ratio" if mode == "relative" else "",
    }
    ax.set_ylabel(ylabel.get(mode, f"Close ({value_unit})"))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", ncols=min(4, max(1, len(names))))
    fig.autofmt_xdate()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=200, facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def _output_png(
    png: bytes,
    series_names: list[str],
    ratio: tuple[int, int],
    period: str,
    *,
    copy: bool = False,
) -> None:
    """Handle output of rendered PNG: optional clipboard copy, inline display
    (Kitty TGP / iTerm2 / Sixel), or fallback file write.
    """
    if copy:
        _copy_to_clipboard(png)
        w, h = _png_dimensions(png)
        msg = f"Plot ({w}x{h}) copied to clipboard."
        if _is_ssh_session():
            msg += " (remote machine -- may not reach your local clipboard)"
        print(msg)

    force_inline = os.environ.get("TERMSERIES_FORCE_INLINE") == "1"
    no_inline = os.environ.get("TERMSERIES_NO_INLINE") == "1"

    if no_inline:
        pass  # fall through to file
    elif _is_kitty():
        _print_kitty_png(png)
        sys.stdout.flush()
        return
    elif _is_iterm2():
        _print_iterm2_png(png)
        sys.stdout.flush()
        return
    elif _is_sixel_terminal():
        _print_sixel_png(png)
        sys.stdout.flush()
        return
    elif force_inline:
        _print_iterm2_png(png)
        sys.stdout.flush()
        return

    # Fallback: write a file so the plot isn't lost.
    names = [n.strip().upper() for n in series_names if n.strip()]
    names_part = "-".join(names[:6])
    if len(names) > 6:
        names_part += f"-plus{len(names) - 6}"
    w, h = ratio
    out = f"termseries_{names_part}_{period}_{w}x{h}.png"
    with open(out, "wb") as f:
        f.write(png)
    print(f"Wrote plot to {out}")


# ---------------------------------------------------------------------------
# Interactive TUI (launched with -i / --interactive)
# ---------------------------------------------------------------------------


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
) -> None:
    """Launch the Textual-based interactive chart viewer."""
    from PIL import Image as PILImage
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal
    from textual.widgets import Input, Select
    from textual_image.widget import Image

    class TermSeriesApp(App):  # type: ignore[type-arg]
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
                s1 = Select.from_values(periods, prompt="Period")
                if period and period in periods:
                    s1.value = period
                elif has_columns:
                    s1.value = periods[0]
                max_len1 = max(len(v) for v in [*periods, "Period"])
                s1.styles.width = max_len1 + 6
                yield s1

                ratios = ["fit", "4:1", "3:1", "2:1"]
                s2 = Select.from_values(ratios, prompt="Ratio")
                if ratio:
                    ratio_str = f"{ratio[0]}:{ratio[1]}"
                    if ratio_str in ratios:
                        s2.value = ratio_str
                    else:
                        s2 = Select.from_values([ratio_str, *ratios], prompt="Ratio")
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
                s_mode = Select.from_values(modes, prompt="Mode")
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
                s3 = Select.from_values(color_options, prompt="Colors")
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
                if _is_ssh_session():
                    msg += " (remote -- may not reach your local machine)"
                self.notify(msg)
            except Exception as e:
                self.notify(f"Copy failed: {e}", severity="error")

        def on_mount(self) -> None:
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


# ---------------------------------------------------------------------------
# Typer CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="Render time-series data as terminal plots.")


@app.callback()
def main(
    ctx: typer.Context,
    ratio: Annotated[str, typer.Option(help='Aspect ratio "W:H"')] = "4:1",
    mode: Annotated[Mode, typer.Option(help="Chart mode")] = Mode.absolute,
    colors: Annotated[ColorCycle, typer.Option(help="Color cycle")] = ColorCycle.tab10,
    copy: Annotated[
        bool, typer.Option("--copy", "-c", help="Copy to clipboard")
    ] = False,
    interactive: Annotated[
        bool, typer.Option("--interactive", "-i", help="Launch TUI")
    ] = False,
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["ratio"] = _parse_ratio(ratio)
    ctx.obj["mode"] = mode.value
    ctx.obj["colors"] = colors.value
    ctx.obj["copy"] = copy
    ctx.obj["interactive"] = interactive


@app.command()
def yahoo(
    ctx: typer.Context,
    tickers: Annotated[
        list[str], typer.Argument(help="Ticker symbols (e.g. TSLA AAPL)")
    ],
    period: Annotated[
        YahooPeriod, typer.Option(help="Yahoo chart range")
    ] = YahooPeriod.d7,
) -> None:
    """Fetch and plot stock data from Yahoo Finance."""
    opts = ctx.obj
    if opts["interactive"]:
        _run_interactive(
            tickers,
            period_choices=[p.value for p in YahooPeriod],
            period=period.value,
            ratio=opts["ratio"],
            mode=opts["mode"],
            colors=opts["colors"],
            fetch_fn=fetch_yahoo_series,
        )
        raise typer.Exit()

    data = fetch_yahoo_series(tickers, period.value)
    png = _render_png(
        data,
        opts["ratio"],
        period.value,
        color_cycle=opts["colors"],
        mode=opts["mode"],
    )
    _output_png(png, tickers, opts["ratio"], period.value, copy=opts["copy"])


@app.command()
def demo() -> None:
    """Run three demo Yahoo Finance plots to showcase different modes."""
    import shlex

    demos = [
        ["yahoo", "TSLA", "AAPL", "MSFT"],
        ["--mode", "indexed", "yahoo", "--period", "1mo", "TSLA", "AAPL", "MSFT"],
        ["--mode", "drawdown", "yahoo", "--period", "1y", "TSLA", "AAPL"],
    ]

    for i, args in enumerate(demos, 1):
        cmd_display = f"termseries {shlex.join(args)}"
        print(f"\n{'=' * 60}")
        print(f"  Demo {i}/{len(demos)}: {cmd_display}")
        print(f"{'=' * 60}\n")
        subprocess.run([sys.executable, "-m", "termseries", *args])
