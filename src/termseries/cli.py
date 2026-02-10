"""Typer CLI application for termseries."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from termseries._render import _output_png, _render_png
from termseries._terminal import _parse_ratio
from termseries._tui import _run_interactive
from termseries._csv_source import fetch_csv_series
from termseries._ha_source import _detect_unit, fetch_ha_series
from termseries._types import ColorCycle, LastPeriod, Mode, YahooPeriod
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


@app.command(name="csv")
def csv_cmd(
    ctx: typer.Context,
    files: Annotated[
        list[str], typer.Argument(help="CSV file paths (timestamp, value)")
    ],
    last: Annotated[
        LastPeriod, typer.Option(help="Show last N period")
    ] = LastPeriod.all,
    unit: Annotated[str, typer.Option(help="Value unit label")] = "value",
) -> None:
    """Plot time-series data from local CSV files."""
    opts = ctx.obj
    if opts["interactive"]:
        _run_interactive(
            files,
            period_choices=[p.value for p in LastPeriod],
            period=last.value,
            ratio=opts["ratio"],
            mode=opts["mode"],
            colors=opts["colors"],
            fetch_fn=fetch_csv_series,
            value_unit=unit,
        )
        raise typer.Exit()

    data = fetch_csv_series(files, last.value)
    png = _render_png(
        data,
        opts["ratio"],
        last.value,
        color_cycle=opts["colors"],
        mode=opts["mode"],
        value_unit=unit,
    )
    labels = [Path(f).stem for f in files]
    _output_png(png, labels, opts["ratio"], last.value, copy=opts["copy"])


@app.command()
def ha(
    ctx: typer.Context,
    entities: Annotated[
        list[str], typer.Argument(help="HA entity IDs (e.g. sensor.temperature)")
    ],
    last: Annotated[
        LastPeriod, typer.Option(help="Show last N period")
    ] = LastPeriod.d7,
    unit: Annotated[
        str | None, typer.Option(help="Value unit (auto-detect if omitted)")
    ] = None,
) -> None:
    """Plot sensor data from a Home Assistant instance.

    Requires HASS_URL and HASS_TOKEN environment variables.
    """
    opts = ctx.obj
    resolved_unit = unit if unit is not None else _detect_unit(entities[0])

    if opts["interactive"]:
        _run_interactive(
            entities,
            period_choices=[p.value for p in LastPeriod],
            period=last.value,
            ratio=opts["ratio"],
            mode=opts["mode"],
            colors=opts["colors"],
            fetch_fn=fetch_ha_series,
            value_unit=resolved_unit,
        )
        raise typer.Exit()

    data = fetch_ha_series(entities, last.value)
    png = _render_png(
        data,
        opts["ratio"],
        last.value,
        color_cycle=opts["colors"],
        mode=opts["mode"],
        value_unit=resolved_unit,
    )
    labels = list(data.keys())
    _output_png(png, labels, opts["ratio"], last.value, copy=opts["copy"])


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
