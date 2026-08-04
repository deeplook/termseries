"""Typer CLI application for termseries."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Annotated, Any

import typer

from termseries.csv_source import fetch_csv_series, resample_series
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
        "  termseries --mode indexed yahoo --last 1mo TSLA AAPL\n"
        "  termseries --mode drawdown yahoo --last 1y TSLA AAPL\n"
        "  termseries polymarket will-bitcoin-hit-150k-in-2026\n"
        "  termseries csv data.csv --last 30d\n"
        "  termseries hass sensor.temperature --last 7d\n"
    ),
)


def _apply_gaps(data: dict[str, TimeSeries], gaps: str) -> dict[str, TimeSeries]:
    """Apply gap processing to all series based on the --gaps value."""
    if gaps == "connect":
        return data
    max_gap = None if gaps == "show" else parse_period(gaps)
    return {name: insert_gaps(series, max_gap=max_gap) for name, series in data.items()}


def _run_source(
    ctx: typer.Context,
    items: list[str],
    period: str,
    fetch_fn: Callable[[list[str], str], dict[str, TimeSeries]],
    *,
    fetching_message: str,
    debug_msg: str | None = None,
    interval_label: str | None = None,
    value_unit: str | None = None,
    anchor_now: bool = False,
    xlim_fn: Callable[[dict[str, TimeSeries]], Any] | None = None,
    labels_fn: Callable[[dict[str, TimeSeries]], list[str]] | None = None,
    time_range: tuple[datetime | None, datetime | None] | None = None,
    first_period: str | None = None,
    period_label: str | None = None,
) -> None:
    """Run the shared fetch -> gaps -> render -> output pipeline for a source.

    Every source command (yahoo, polymarket, csv, hass, ...) shares this
    pipeline; only the fetch function and a handful of render/TUI options
    differ between them.
    """
    opts = ctx.obj
    display_period = period_label or period

    if opts["interactive"]:
        if time_range is not None or first_period is not None:
            raise typer.BadParameter(
                "--first and --from/--to cannot be used with --interactive; "
                "use --last instead."
            )
        interactive_kwargs: dict[str, Any] = {}
        if value_unit is not None:
            interactive_kwargs["value_unit"] = value_unit
        if anchor_now:
            interactive_kwargs["anchor_now"] = True
        _run_interactive(
            items,
            period_choices=TUI_PERIOD_CHOICES,
            period=period,
            ratio=opts["ratio"],
            mode=opts["mode"],
            colors=opts["colors"],
            fetch_fn=fetch_fn,
            style_override=opts["style"],
            reload_interval=opts["reload"],
            tz=opts["tz"],
            line_style=opts["line_style"],
            theme=opts["theme"],
            **interactive_kwargs,
        )
        raise typer.Exit()

    if debug_msg is not None:
        _debug_echo(debug_msg)
    typer.echo(fetching_message, err=True)
    try:
        data = fetch_fn(items, period)
        if first_period is not None:
            duration = parse_period(first_period)
            assert duration is not None  # validated by _validate_first
            all_ts = [dt for series in data.values() for dt, _ in series]
            first_start = min(all_ts)
            time_range = (first_start, first_start + duration)
        if time_range is not None:
            range_start, range_end = time_range
            data = {
                name: [
                    (dt, value)
                    for dt, value in series
                    if (range_start is None or dt >= range_start)
                    and (range_end is None or dt <= range_end)
                ]
                for name, series in data.items()
            }
            empty = [name for name, series in data.items() if not series]
            if empty:
                raise RuntimeError(
                    "No data left after applying the requested time range "
                    f"for: {', '.join(empty)}."
                )
        data = _apply_gaps(data, opts["gaps"])
        r = opts["ratio"] or (4, 1)
        render_kwargs: dict[str, Any] = {}
        if value_unit is not None:
            render_kwargs["value_unit"] = value_unit
        if interval_label is not None:
            render_kwargs["interval_label"] = interval_label
        if time_range is not None:
            range_start, range_end = time_range
            all_ts = [dt for series in data.values() for dt, _ in series]
            render_kwargs["xlim"] = (
                range_start or min(all_ts),
                range_end or max(all_ts),
            )
        elif xlim_fn is not None:
            render_kwargs["xlim"] = xlim_fn(data)
        png = _render_png(
            data,
            r,
            display_period,
            color_cycle=opts["colors"],
            mode=opts["mode"],
            style_override=opts["style"],
            tz=opts["tz"],
            line_style=opts["line_style"],
            theme=opts["theme"],
            **render_kwargs,
        )
        labels = labels_fn(data) if labels_fn is not None else list(data.keys())
        _output_png(
            png,
            labels,
            r,
            display_period,
            copy=opts["copy"],
            output=opts["output"],
            protocol=opts["protocol"],
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None


def _validate_period(value: str | None) -> str | None:
    """Typer callback that validates a free-form period string."""
    if value is None:
        return None
    try:
        parse_period(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return value


def _validate_first(value: str | None) -> str | None:
    """Validate a fixed duration for a data-anchored ``--first`` window."""
    if value is None:
        return None
    try:
        duration = parse_period(value)
    except ValueError as exc:
        raise typer.BadParameter("Use a duration such as 7d, 2w, or 3mo.") from exc
    if value in {"max", "auto", "ytd", "mtd", "wtd", "dtd", "htd"} or duration is None:
        raise typer.BadParameter("Use a duration such as 7d, 2w, or 3mo.")
    return value


def _parse_time_bound(value: str, *, now: datetime, tz: str) -> datetime:
    """Parse an ISO-8601 instant, ``now``, or a relative/anchored start."""
    if value == "now":
        return now
    try:
        delta = parse_period(value, tz=resolve_tz(tz))
    except ValueError:
        delta = None
    else:
        if value in {"max", "auto"}:
            raise typer.BadParameter("Time bounds cannot be 'max' or 'auto'.")
        return now - delta  # type: ignore[operator]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise typer.BadParameter(
            "Use an ISO-8601 date/time (e.g. 2026-07-01 or "
            "2026-07-01T12:00:00Z), 'now', or a value such as 7d/ytd."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=resolve_tz(tz))
    return parsed.astimezone(timezone.utc)


def _resolve_time_range(
    last: str | None,
    first: str | None,
    from_: str | None,
    to: str | None,
    *,
    default_last: str,
    tz: str,
) -> tuple[str, str, tuple[datetime | None, datetime | None] | None, str | None]:
    """Return fetch period, display label, and optional explicit bounds."""
    selected = sum(value is not None for value in (last, first, from_, to))
    if first is not None and selected > 1:
        raise typer.BadParameter(
            "Use --first by itself, not with --last or --from/--to."
        )
    if last is not None and (from_ is not None or to is not None):
        raise typer.BadParameter("Use either --last or --from/--to, not both.")
    if first is not None:
        return "max", f"first {first}", None, first
    if from_ is None and to is None:
        resolved_last = last or default_last
        return resolved_last, resolved_last, None, None
    now = datetime.now(timezone.utc)
    start = _parse_time_bound(from_, now=now, tz=tz) if from_ else None
    end = _parse_time_bound(to, now=now, tz=tz) if to else now
    if start is not None and end is not None and start > end:
        raise typer.BadParameter("--from must not be later than --to.")
    label = f"{from_ or 'start'}..{to or 'now'}"
    # Source APIs accept rolling-period tokens; fetch their full available range
    # and apply the exact interval once, consistently, in _run_source.
    return "max", label, (start, end), None


def _validate_resample(value: str | None) -> str | None:
    """Validate a positive fixed-width interval for CSV resampling."""
    if value is None:
        return None
    try:
        resample_series([], value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Use a positive duration such as 1m, 5m, or 1h. {exc}"
        ) from exc
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
        "  termseries yahoo TSLA AAPL MSFT --last 1mo\n"
        "  termseries --mode indexed yahoo --last 1y TSLA AAPL\n"
        "  termseries yahoo TSLA --interval 1d --last max\n"
    )
)
def yahoo(
    ctx: typer.Context,
    tickers: Annotated[
        list[str], typer.Argument(help="Ticker symbols (e.g. TSLA AAPL)")
    ],
    last: Annotated[
        str | None,
        typer.Option(
            "--last",
            "--period",
            help="Rolling window ending now (e.g. 7d, 2w, 3mo, max)",
            callback=_validate_period,
        ),
    ] = None,
    from_: Annotated[
        str | None, typer.Option("--from", help="Inclusive start time")
    ] = None,
    to: Annotated[
        str | None, typer.Option("--to", help="Inclusive end time (default: now)")
    ] = None,
    first: Annotated[
        str | None,
        typer.Option(
            "--first",
            help="Data-anchored duration; can change when history is backfilled",
            callback=_validate_first,
        ),
    ] = None,
    interval: Annotated[
        YahooInterval, typer.Option(help="Chart interval (auto picks by period)")
    ] = YahooInterval.auto,
) -> None:
    """Fetch and plot stock data from Yahoo Finance."""
    period, period_label, time_range, first_period = _resolve_time_range(
        last, first, from_, to, default_last="7d", tz=ctx.obj["tz"]
    )
    if interval.value == "auto":
        resolved = yahoo_auto_interval(period)
    else:
        resolved = interval.value
    interval_label = "Daily" if resolved == "1d" else resolved

    _run_source(
        ctx,
        tickers,
        period,
        partial(fetch_yahoo_series, interval=interval.value, tz=ctx.obj["tz"]),
        fetching_message=f"Fetching {', '.join(tickers)} from Yahoo Finance…",
        debug_msg=(
            f"yahoo: period={period} interval={interval.value} resolved={resolved}"
        ),
        interval_label=interval_label,
        time_range=time_range,
        first_period=first_period,
        period_label=period_label,
    )


@app.command(  # type: ignore[misc]
    epilog=(
        "Examples:\n\n"
        "  termseries polymarket will-bitcoin-hit-150k-in-2026\n"
        "  termseries polymarket will-bitcoin-hit-150k-in-2026 --outcome no\n"
        "  termseries polymarket will-bitcoin-hit-150k-in-2026 --last 30d\n"
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
    last: Annotated[
        str | None,
        typer.Option(
            "--last",
            "--period",
            help="Rolling window ending now (e.g. 7d, 2w, 3mo, max)",
            callback=_validate_period,
        ),
    ] = None,
    from_: Annotated[
        str | None, typer.Option("--from", help="Inclusive start time")
    ] = None,
    to: Annotated[
        str | None, typer.Option("--to", help="Inclusive end time (default: now)")
    ] = None,
    first: Annotated[
        str | None,
        typer.Option(
            "--first",
            help="Data-anchored duration; can change when history is backfilled",
            callback=_validate_first,
        ),
    ] = None,
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
    period, period_label, time_range, first_period = _resolve_time_range(
        last, first, from_, to, default_last="7d", tz=ctx.obj["tz"]
    )
    resolved = (
        polymarket_auto_interval(period) if interval.value == "auto" else interval.value
    )

    _run_source(
        ctx,
        markets,
        period,
        partial(
            fetch_polymarket_series,
            outcome=outcome,
            interval=interval.value,
            fidelity=fidelity,
            tz=ctx.obj["tz"],
        ),
        fetching_message=f"Fetching {', '.join(markets)} from Polymarket…",
        debug_msg=(
            f"polymarket: period={period} interval={interval.value} resolved={resolved}"
        ),
        interval_label=resolved,
        time_range=time_range,
        first_period=first_period,
        period_label=period_label,
    )


@app.command(  # type: ignore[misc]
    name="csv",
    epilog=(
        "Examples:\n\n"
        "  termseries csv data.csv\n"
        "  termseries csv data.csv --last 30d --unit °C\n"
        "  termseries csv heart.csv --last 1mo --resample 1m --aggregate mean\n"
        "  termseries csv temp.csv humidity.csv --last 7d\n"
    ),
)
def csv_cmd(
    ctx: typer.Context,
    files: Annotated[
        list[str], typer.Argument(help="CSV file paths (timestamp, value)")
    ],
    last: Annotated[
        str | None,
        typer.Option(
            "--last",
            "--period",
            help="Rolling window ending now (e.g. 7d, 2w, max)",
            callback=_validate_period,
        ),
    ] = None,
    from_: Annotated[
        str | None, typer.Option("--from", help="Inclusive start time")
    ] = None,
    to: Annotated[
        str | None, typer.Option("--to", help="Inclusive end time (default: now)")
    ] = None,
    first: Annotated[
        str | None,
        typer.Option(
            "--first",
            help="Data-anchored duration; can change when history is backfilled",
            callback=_validate_first,
        ),
    ] = None,
    unit: Annotated[str, typer.Option(help="Value unit label")] = "value",
    resample: Annotated[
        str | None,
        typer.Option(
            help="Reduce into fixed UTC buckets (e.g. 1m, 5m, 1h)",
            callback=_validate_resample,
        ),
    ] = None,
    aggregate: Annotated[
        str,
        typer.Option(
            help="Bucket reducer: mean, median, min, max, sum, count, first, last"
        ),
    ] = "mean",
) -> None:
    """Plot time-series data from local CSV files."""
    tz = ctx.obj["tz"]
    period, period_label, time_range, first_period = _resolve_time_range(
        last, first, from_, to, default_last="max", tz=tz
    )

    _run_source(
        ctx,
        files,
        period,
        partial(fetch_csv_series, tz=tz, resample=resample, aggregate=aggregate),
        fetching_message=f"Reading {', '.join(files)}…",
        value_unit=unit,
        anchor_now=True,
        xlim_fn=lambda data: xlim_now(period, data, tz=resolve_tz(tz)),
        labels_fn=lambda _data: [Path(f).stem for f in files],
        time_range=time_range,
        first_period=first_period,
        period_label=period_label,
    )


@app.command(  # type: ignore[misc]
    epilog=(
        "Examples:\n\n"
        "  termseries hass sensor.temperature\n"
        "  termseries hass sensor.temperature sensor.humidity --last 30d\n"
        "  termseries --mode absolute hass sensor.power --unit W\n"
    )
)
def hass(
    ctx: typer.Context,
    entities: Annotated[
        list[str], typer.Argument(help="HASS entity IDs (e.g. sensor.temperature)")
    ],
    last: Annotated[
        str | None,
        typer.Option(
            "--last",
            "--period",
            help="Rolling window ending now (e.g. 7d, 2w, max)",
            callback=_validate_period,
        ),
    ] = None,
    from_: Annotated[
        str | None, typer.Option("--from", help="Inclusive start time")
    ] = None,
    to: Annotated[
        str | None, typer.Option("--to", help="Inclusive end time (default: now)")
    ] = None,
    first: Annotated[
        str | None,
        typer.Option(
            "--first",
            help="Data-anchored duration; can change when history is backfilled",
            callback=_validate_first,
        ),
    ] = None,
    unit: Annotated[
        str | None, typer.Option(help="Value unit (auto-detect if omitted)")
    ] = None,
) -> None:
    """Plot sensor data from a Home Assistant instance.

    Requires HASS_SERVER and HASS_TOKEN environment variables.
    """
    try:
        resolved_entities = expand_entities(entities)
        resolved_unit = unit if unit is not None else _detect_unit(resolved_entities[0])
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from None

    period, period_label, time_range, first_period = _resolve_time_range(
        last, first, from_, to, default_last="7d", tz=ctx.obj["tz"]
    )
    _run_source(
        ctx,
        resolved_entities,
        period,
        partial(fetch_hass_series, tz=ctx.obj["tz"]),
        fetching_message=(
            f"Fetching {', '.join(resolved_entities)} from Home Assistant…"
        ),
        value_unit=resolved_unit,
        time_range=time_range,
        first_period=first_period,
        period_label=period_label,
    )


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
