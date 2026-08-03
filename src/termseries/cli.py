"""Typer CLI application for termseries."""

from __future__ import annotations

import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Annotated

import typer

from termseries.csv_source import fetch_csv_series
from termseries.detect import (
    supports_iterm2_inline_images,
    supports_kitty_graphics,
    supports_sixel,
)
from termseries.gaps import insert_gaps
from termseries.hass_source import _detect_unit, expand_entities, fetch_hass_series
from termseries.period import (
    TUI_PERIOD_CHOICES,
    parse_period,
    polymarket_auto_interval,
    resolve_tz,
    xlim_now,
    yahoo_auto_interval,
)
from termseries.polymarket import fetch_polymarket_series
from termseries.render import _output_png, _render_png
from termseries.terminal import (
    _VALID_PROTOCOLS,
    _VALID_THEMES,
    _is_docker,
    _is_iterm2,
    _is_kitty,
    _is_sixel_terminal,
    _is_ssh_session,
    _load_config,
    _parse_ratio,
    _terminal_pixel_width,
)
from termseries.tui import _run_interactive
from termseries.types import (
    ColorCycle,
    LineStyle,
    Mode,
    PolymarketInterval,
    TimeSeries,
    YahooInterval,
)
from termseries.yahoo import fetch_yahoo_series

app = typer.Typer(
    help="Render time-series data as terminal plots.",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog=(
        "Examples:\n\n"
        "  termseries yahoo TSLA AAPL MSFT\n"
        "  termseries --mode indexed yahoo --period 1mo TSLA AAPL\n"
        "  termseries --mode drawdown yahoo --period 1y TSLA AAPL\n"
        "  termseries polymarket will-bitcoin-hit-150k-in-2026\n"
        "  termseries csv data.csv --period 30d\n"
        "  termseries hass sensor.temperature --period 7d\n"
    ),
)


def _apply_gaps(data: dict[str, TimeSeries], gaps: str) -> dict[str, TimeSeries]:
    """Apply gap processing to all series based on the --gaps value."""
    if gaps == "connect":
        return data
    max_gap = None if gaps == "show" else parse_period(gaps)
    return {name: insert_gaps(series, max_gap=max_gap) for name, series in data.items()}


def _validate_period(value: str) -> str:
    """Typer callback that validates a free-form period string."""
    try:
        parse_period(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return value


def _validate_tz(value: str) -> str:
    """Typer callback that validates the --tz option.

    Catches ``ValueError`` (malformed key) and ``LookupError`` (unknown IANA
    zone, e.g. ``ZoneInfoNotFoundError``) so a bad --tz value fails cleanly
    at option-parsing time instead of crashing deep inside rendering.
    """
    try:
        resolve_tz(value)
    except (ValueError, LookupError) as exc:
        raise typer.BadParameter(
            f'{value!r} is not "UTC", "local", or a valid IANA zone name '
            "(e.g. Europe/Berlin)."
        ) from exc
    return value


def _validate_theme(value: str | None) -> str | None:
    """Typer callback that validates the --theme option."""
    if value is not None and value not in _VALID_THEMES:
        raise typer.BadParameter('theme must be "dark", "light", or "auto"')
    return value


def _validate_protocol(value: str | None) -> str | None:
    """Typer callback that validates the --protocol option."""
    if value is not None and value not in _VALID_PROTOCOLS:
        raise typer.BadParameter(
            'protocol must be "auto", "kitty", "iterm2", or "sixel"'
        )
    return value


def _validate_output(value: str | None) -> str | None:
    """Typer callback that validates the --output option.

    Keywords "auto", "inline", and "-" are reserved; any other value is treated
    as a file path and accepted as-is.
    """
    return value


def _validate_gaps(value: str) -> str:
    """Typer callback that validates the --gaps option."""
    if value in ("connect", "show"):
        return value
    try:
        td = parse_period(value)
        if td is None:
            msg = "Invalid gaps value. Use 'connect', 'show', or a duration."
            raise typer.BadParameter(msg)
    except ValueError as exc:
        msg = f"Invalid gaps value {value!r}. Use 'connect', 'show', or a duration."
        raise typer.BadParameter(msg) from exc
    return value


def _debug_echo(msg: str) -> None:
    """Print a debug line to stderr when the DEBUG env var is set."""
    import os

    if os.environ.get("DEBUG"):
        typer.echo(f"[debug] {msg}", err=True)


def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version

        typer.echo(f"termseries {version('termseries')}")
        raise typer.Exit()


@app.callback()  # type: ignore[misc]
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version and exit",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
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
        str,
        typer.Option(
            help='Timezone for x-axis: "UTC", "local", or IANA name',
            callback=_validate_tz,
        ),
    ] = "UTC",
    line_style: Annotated[
        LineStyle, typer.Option(help="Line connection style")
    ] = LineStyle.linear,
    gaps: Annotated[
        str,
        typer.Option(
            help='Gap handling: "connect", "show", or duration (e.g. 1h, 30m)',
            callback=_validate_gaps,
        ),
    ] = "connect",
    theme: Annotated[
        str | None,
        typer.Option(
            help='Plot theme: "dark", "light", or "auto" (follow terminal, default)',
            callback=_validate_theme,
        ),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option(
            help='Output: "auto" (default), "inline", "-" (stdout), or a file path',
            callback=_validate_output,
        ),
    ] = None,
    protocol: Annotated[
        str | None,
        typer.Option(
            help='Inline protocol: "auto" (default), "kitty", "iterm2", or "sixel"',
            callback=_validate_protocol,
        ),
    ] = None,
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
    ctx.obj["line_style"] = line_style.value
    ctx.obj["gaps"] = gaps

    cfg: dict[str, str] | None = None

    if theme is None:
        cfg = _load_config()
        raw = cfg.get("theme", "auto")
        if raw not in _VALID_THEMES:
            typer.echo(
                f"Warning: invalid theme {raw!r} in termseries.env, using 'auto'",
                err=True,
            )
            raw = "auto"
        theme = raw
    ctx.obj["theme"] = theme

    if output is None:
        if cfg is None:
            cfg = _load_config()
        output = cfg.get("output", "auto")
    ctx.obj["output"] = output

    if protocol is None:
        if cfg is None:
            cfg = _load_config()
        raw_protocol = cfg.get("protocol", "auto")
        if raw_protocol not in _VALID_PROTOCOLS:
            typer.echo(
                f"Warning: invalid protocol {raw_protocol!r} in termseries.env,"
                " using 'auto'",
                err=True,
            )
            raw_protocol = "auto"
        protocol = raw_protocol
    ctx.obj["protocol"] = protocol

    _debug_echo(f"theme={theme} output={output} protocol={protocol}")
    _debug_echo(f"mode={ctx.obj['mode']} ratio={ctx.obj['ratio']} tz={ctx.obj['tz']}")

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command(  # type: ignore[misc]
    epilog=(
        "Examples:\n\n"
        "  termseries yahoo TSLA\n"
        "  termseries yahoo TSLA AAPL MSFT --period 1mo\n"
        "  termseries --mode indexed yahoo --period 1y TSLA AAPL\n"
        "  termseries yahoo TSLA --interval 1d --period max\n"
    )
)
def yahoo(
    ctx: typer.Context,
    tickers: Annotated[
        list[str], typer.Argument(help="Ticker symbols (e.g. TSLA AAPL)")
    ],
    period: Annotated[
        str,
        typer.Option(
            help="Chart range (e.g. 7d, 2w, 3mo, max)",
            callback=_validate_period,
        ),
    ] = "7d",
    interval: Annotated[
        YahooInterval, typer.Option(help="Chart interval (auto picks by period)")
    ] = YahooInterval.auto,
) -> None:
    """Fetch and plot stock data from Yahoo Finance."""
    opts = ctx.obj
    if interval.value == "auto":
        resolved = yahoo_auto_interval(period)
    else:
        resolved = interval.value
    interval_label = "Daily" if resolved == "1d" else resolved

    if opts["interactive"]:
        _run_interactive(
            tickers,
            period_choices=TUI_PERIOD_CHOICES,
            period=period,
            ratio=opts["ratio"],
            mode=opts["mode"],
            colors=opts["colors"],
            fetch_fn=partial(
                fetch_yahoo_series, interval=interval.value, tz=opts["tz"]
            ),
            style_override=opts["style"],
            reload_interval=opts["reload"],
            tz=opts["tz"],
            line_style=opts["line_style"],
            theme=opts["theme"],
        )
        raise typer.Exit()

    _debug_echo(f"yahoo: period={period} interval={interval.value} resolved={resolved}")
    typer.echo(f"Fetching {', '.join(tickers)} from Yahoo Finance…", err=True)
    try:
        data = fetch_yahoo_series(
            tickers, period, interval=interval.value, tz=opts["tz"]
        )
        data = _apply_gaps(data, opts["gaps"])
        r = opts["ratio"] or (4, 1)
        png = _render_png(
            data,
            r,
            period,
            color_cycle=opts["colors"],
            mode=opts["mode"],
            style_override=opts["style"],
            tz=opts["tz"],
            interval_label=interval_label,
            line_style=opts["line_style"],
            theme=opts["theme"],
        )
        _output_png(
            png,
            list(data.keys()),
            r,
            period,
            copy=opts["copy"],
            output=opts["output"],
            protocol=opts["protocol"],
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None


@app.command(  # type: ignore[misc]
    epilog=(
        "Examples:\n\n"
        "  termseries polymarket will-bitcoin-hit-150k-in-2026\n"
        "  termseries polymarket will-bitcoin-hit-150k-in-2026 --outcome no\n"
        "  termseries polymarket will-bitcoin-hit-150k-in-2026 --period 30d\n"
    )
)
def polymarket(
    ctx: typer.Context,
    markets: Annotated[
        list[str],
        typer.Argument(
            help="Polymarket market slugs (e.g. will-bitcoin-hit-150k-in-2026)"
        ),
    ],
    period: Annotated[
        str,
        typer.Option(
            help="Chart range (e.g. 7d, 2w, 3mo, max)",
            callback=_validate_period,
        ),
    ] = "7d",
    outcome: Annotated[
        str,
        typer.Option(
            help='Outcome label to chart, usually "yes" or "no" for binary markets'
        ),
    ] = "yes",
    interval: Annotated[
        PolymarketInterval,
        typer.Option(help="Aggregation interval (auto picks by period)"),
    ] = PolymarketInterval.auto,
    fidelity: Annotated[
        int,
        typer.Option(help="Data fidelity in minutes for the Polymarket history API"),
    ] = 1,
) -> None:
    """Fetch and plot market price data from Polymarket."""
    opts = ctx.obj
    resolved = (
        polymarket_auto_interval(period) if interval.value == "auto" else interval.value
    )

    if opts["interactive"]:
        _run_interactive(
            markets,
            period_choices=TUI_PERIOD_CHOICES,
            period=period,
            ratio=opts["ratio"],
            mode=opts["mode"],
            colors=opts["colors"],
            fetch_fn=partial(
                fetch_polymarket_series,
                outcome=outcome,
                interval=interval.value,
                fidelity=fidelity,
                tz=opts["tz"],
            ),
            style_override=opts["style"],
            reload_interval=opts["reload"],
            tz=opts["tz"],
            line_style=opts["line_style"],
            theme=opts["theme"],
        )
        raise typer.Exit()

    _debug_echo(
        f"polymarket: period={period} interval={interval.value} resolved={resolved}"
    )
    typer.echo(f"Fetching {', '.join(markets)} from Polymarket…", err=True)
    try:
        data = fetch_polymarket_series(
            markets,
            period,
            outcome=outcome,
            interval=interval.value,
            fidelity=fidelity,
            tz=opts["tz"],
        )
        data = _apply_gaps(data, opts["gaps"])
        r = opts["ratio"] or (4, 1)
        png = _render_png(
            data,
            r,
            period,
            color_cycle=opts["colors"],
            mode=opts["mode"],
            style_override=opts["style"],
            tz=opts["tz"],
            interval_label=resolved,
            line_style=opts["line_style"],
            theme=opts["theme"],
        )
        labels = list(data.keys())
        _output_png(
            png,
            labels,
            r,
            period,
            copy=opts["copy"],
            output=opts["output"],
            protocol=opts["protocol"],
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None


@app.command(  # type: ignore[misc]
    name="csv",
    epilog=(
        "Examples:\n\n"
        "  termseries csv data.csv\n"
        "  termseries csv data.csv --period 30d --unit °C\n"
        "  termseries csv temp.csv humidity.csv --period 7d\n"
    ),
)
def csv_cmd(
    ctx: typer.Context,
    files: Annotated[
        list[str], typer.Argument(help="CSV file paths (timestamp, value)")
    ],
    period: Annotated[
        str,
        typer.Option(
            help="Show last N period (e.g. 7d, 2w, max)",
            callback=_validate_period,
        ),
    ] = "max",
    unit: Annotated[str, typer.Option(help="Value unit label")] = "value",
) -> None:
    """Plot time-series data from local CSV files."""
    opts = ctx.obj
    if opts["interactive"]:
        _run_interactive(
            files,
            period_choices=TUI_PERIOD_CHOICES,
            period=period,
            ratio=opts["ratio"],
            mode=opts["mode"],
            colors=opts["colors"],
            fetch_fn=partial(fetch_csv_series, tz=opts["tz"]),
            value_unit=unit,
            style_override=opts["style"],
            reload_interval=opts["reload"],
            tz=opts["tz"],
            line_style=opts["line_style"],
            anchor_now=True,
            theme=opts["theme"],
        )
        raise typer.Exit()

    typer.echo(f"Reading {', '.join(files)}…", err=True)
    try:
        data = fetch_csv_series(files, period, tz=opts["tz"])
        data = _apply_gaps(data, opts["gaps"])
        r = opts["ratio"] or (4, 1)
        png = _render_png(
            data,
            r,
            period,
            color_cycle=opts["colors"],
            mode=opts["mode"],
            value_unit=unit,
            style_override=opts["style"],
            tz=opts["tz"],
            line_style=opts["line_style"],
            xlim=xlim_now(period, data, tz=resolve_tz(opts["tz"])),
            theme=opts["theme"],
        )
        labels = [Path(f).stem for f in files]
        _output_png(
            png,
            labels,
            r,
            period,
            copy=opts["copy"],
            output=opts["output"],
            protocol=opts["protocol"],
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None


@app.command(  # type: ignore[misc]
    epilog=(
        "Examples:\n\n"
        "  termseries hass sensor.temperature\n"
        "  termseries hass sensor.temperature sensor.humidity --period 30d\n"
        "  termseries --mode absolute hass sensor.power --unit W\n"
    )
)
def hass(
    ctx: typer.Context,
    entities: Annotated[
        list[str], typer.Argument(help="HASS entity IDs (e.g. sensor.temperature)")
    ],
    period: Annotated[
        str,
        typer.Option(
            help="Show last N period (e.g. 7d, 2w, max)",
            callback=_validate_period,
        ),
    ] = "7d",
    unit: Annotated[
        str | None, typer.Option(help="Value unit (auto-detect if omitted)")
    ] = None,
) -> None:
    """Plot sensor data from a Home Assistant instance.

    Requires HASS_SERVER and HASS_TOKEN environment variables.
    """
    opts = ctx.obj

    if opts["interactive"]:
        try:
            resolved_entities = expand_entities(entities)
            resolved_unit = (
                unit if unit is not None else _detect_unit(resolved_entities[0])
            )
        except (RuntimeError, ValueError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from None
        _run_interactive(
            resolved_entities,
            period_choices=TUI_PERIOD_CHOICES,
            period=period,
            ratio=opts["ratio"],
            mode=opts["mode"],
            colors=opts["colors"],
            fetch_fn=partial(fetch_hass_series, tz=opts["tz"]),
            value_unit=resolved_unit,
            style_override=opts["style"],
            reload_interval=opts["reload"],
            tz=opts["tz"],
            line_style=opts["line_style"],
            theme=opts["theme"],
        )
        raise typer.Exit()

    try:
        resolved_entities = expand_entities(entities)
        typer.echo(
            f"Fetching {', '.join(resolved_entities)} from Home Assistant…", err=True
        )
        resolved_unit = unit if unit is not None else _detect_unit(resolved_entities[0])
        data = fetch_hass_series(resolved_entities, period, tz=opts["tz"])
        data = _apply_gaps(data, opts["gaps"])
        r = opts["ratio"] or (4, 1)
        png = _render_png(
            data,
            r,
            period,
            color_cycle=opts["colors"],
            mode=opts["mode"],
            value_unit=resolved_unit,
            style_override=opts["style"],
            tz=opts["tz"],
            line_style=opts["line_style"],
            theme=opts["theme"],
        )
        labels = list(data.keys())
        _output_png(
            png,
            labels,
            r,
            period,
            copy=opts["copy"],
            output=opts["output"],
            protocol=opts["protocol"],
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None


@app.command()  # type: ignore[misc]
def info() -> None:
    """Show terminal environment and inline image protocol support."""
    import os
    import sys

    rows: list[tuple[str, bool | str]] = [
        ("stdout is a TTY", sys.stdout.isatty()),
        ("Kitty protocol", _is_kitty()),
        ("Kitty protocol detect", supports_kitty_graphics()),
        ("iTerm2 protocol", _is_iterm2()),
        ("iTerm2 protocol detect", supports_iterm2_inline_images()),
        ("Sixel protocol", _is_sixel_terminal()),
        ("Sixel protocol detect", supports_sixel()),
        ("SSH session", _is_ssh_session()),
        ("Docker container", _is_docker()),
        ("Terminal pixel width", str(_terminal_pixel_width() or "unknown")),
    ]

    label_w = max(len(label) for label, _ in rows)
    print("Terminal info:")
    for label, value in rows:
        mark = value if isinstance(value, str) else ("yes" if value else "no")
        print(f"  {label:<{label_w}}  {mark}")

    print()
    print("Environment:")
    for var in (
        "TERM",
        "TERM_PROGRAM",
        "LC_TERMINAL",
        "ITERM_SESSION_ID",
        "COLORTERM",
        "COLORFGBG",
        "SSH_CONNECTION",
        "SSH_CLIENT",
    ):
        val = os.environ.get(var)
        if val is not None:
            print(f"  {var}={val}")

    print()
    if not sys.stdout.isatty():
        print("Inline rendering: no (stdout is not a TTY)")
    elif _is_kitty():
        print("Inline rendering: yes (kitty)")
    elif _is_iterm2():
        print("Inline rendering: yes (iterm2)")
    elif _is_sixel_terminal():
        print("Inline rendering: yes (sixel)")
    else:
        print("Inline rendering: no (no supported protocol detected)")


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
