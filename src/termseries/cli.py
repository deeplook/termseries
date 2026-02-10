"""Typer CLI application for termseries."""

from __future__ import annotations

import subprocess
import sys
from typing import Annotated

import typer

from termseries._render import _output_png, _render_png
from termseries._terminal import _parse_ratio
from termseries._tui import _run_interactive
from termseries._types import ColorCycle, Mode, YahooPeriod
from termseries.yahoo import fetch_yahoo_series

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
