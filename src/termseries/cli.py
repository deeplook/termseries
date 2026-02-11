"""Typer CLI application for termseries."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from termseries._csv_source import fetch_csv_series
from termseries._ha_source import _detect_unit, fetch_ha_series
from termseries._render import _output_png, _render_png
from termseries._terminal import _parse_ratio
from termseries._tui import _run_interactive
from termseries._types import ColorCycle, LastPeriod, Mode, YahooPeriod
from termseries.yahoo import fetch_yahoo_series

app = typer.Typer(help="Render time-series data as terminal plots.")


@app.callback()  # type: ignore[misc]
def main(
    ctx: typer.Context,
    ratio: Annotated[
        str | None, typer.Option(help='Aspect ratio "W:H" or "fit"')
    ] = None,
    mode: Annotated[Mode, typer.Option(help="Chart mode")] = Mode.absolute,
    colors: Annotated[ColorCycle, typer.Option(help="Color cycle")] = ColorCycle.tab10,
    style: Annotated[
        Path | None,
        typer.Option(help="Extra .mplstyle file layered on top of the base theme"),
    ] = None,
    copy: Annotated[
        bool, typer.Option("--copy", "-c", help="Copy to clipboard")
    ] = False,
    interactive: Annotated[
        bool, typer.Option("--interactive", "-i", help="Launch TUI")
    ] = False,
    reload: Annotated[
        int, typer.Option(help="Auto-reload interval in seconds (0=off, TUI only)")
    ] = 0,
    tz: Annotated[
        str, typer.Option(help='Timezone for x-axis: "UTC", "local", or IANA name')
    ] = "UTC",
) -> None:
    ctx.ensure_object(dict)
    effective_ratio = ("fit" if interactive else "4:1") if ratio is None else ratio
    ctx.obj["ratio"] = (
        None
        if effective_ratio.strip().lower() == "fit"
        else _parse_ratio(effective_ratio)
    )
    ctx.obj["mode"] = mode.value
    ctx.obj["colors"] = colors.value
    ctx.obj["style"] = style
    ctx.obj["copy"] = copy
    ctx.obj["interactive"] = interactive
    ctx.obj["reload"] = reload
    ctx.obj["tz"] = tz


@app.command()  # type: ignore[misc]
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
            style_override=opts["style"],
            reload_interval=opts["reload"],
            tz=opts["tz"],
        )
        raise typer.Exit()

    data = fetch_yahoo_series(tickers, period.value)
    r = opts["ratio"] or (4, 1)
    png = _render_png(
        data,
        r,
        period.value,
        color_cycle=opts["colors"],
        mode=opts["mode"],
        style_override=opts["style"],
        tz=opts["tz"],
    )
    _output_png(png, tickers, r, period.value, copy=opts["copy"])


@app.command(name="csv")  # type: ignore[misc]
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
            style_override=opts["style"],
            reload_interval=opts["reload"],
            tz=opts["tz"],
        )
        raise typer.Exit()

    data = fetch_csv_series(files, last.value)
    r = opts["ratio"] or (4, 1)
    png = _render_png(
        data,
        r,
        last.value,
        color_cycle=opts["colors"],
        mode=opts["mode"],
        value_unit=unit,
        style_override=opts["style"],
        tz=opts["tz"],
    )
    labels = [Path(f).stem for f in files]
    _output_png(png, labels, r, last.value, copy=opts["copy"])


@app.command()  # type: ignore[misc]
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
            style_override=opts["style"],
            reload_interval=opts["reload"],
            tz=opts["tz"],
        )
        raise typer.Exit()

    data = fetch_ha_series(entities, last.value)
    r = opts["ratio"] or (4, 1)
    png = _render_png(
        data,
        r,
        last.value,
        color_cycle=opts["colors"],
        mode=opts["mode"],
        value_unit=resolved_unit,
        style_override=opts["style"],
        tz=opts["tz"],
    )
    labels = list(data.keys())
    _output_png(png, labels, r, last.value, copy=opts["copy"])


@app.command()  # type: ignore[misc]
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
