"""Chart rendering and output dispatch."""

from __future__ import annotations

import hashlib
import math
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib
import matplotlib.pyplot as plt
from cycler import cycler

from termseries.terminal import (
    _copy_to_clipboard,
    _detect_dark_terminal,
    _is_docker,
    _is_ghostty,
    _is_iterm2,
    _is_kitty,
    _is_sixel_terminal,
    _is_ssh_session,
    _png_dimensions,
    _print_iterm2_png,
    _print_kitty_png,
    _print_sixel_png,
    _terminal_pixel_width,
)
from termseries.types import TimeSeries

_Transform = Callable[[Sequence[Any], Sequence[float]], tuple[list[Any], list[float]]]


def _display_series_name(name: str) -> str:
    """Shorten long display names for titles and legends."""
    raw = name.strip()
    if not raw:
        return raw

    label = raw.replace("-", " ")
    if len(label) > 42:
        return f"{label[:39].rstrip()}..."
    return label


def _legend_layout(display_names: Sequence[str]) -> tuple[str, int, int]:
    """Return ``(placement, cols, rows)`` for legend placement."""
    if not display_names:
        return ("best", 1, 1)
    max_len = max(len(name) for name in display_names)
    count = len(display_names)

    if count == 1:
        return ("inside-top-left", 1, 1)

    if count <= 4 and max_len <= 24:
        cols = min(4, max(1, count))
        return ("best", cols, 1)

    if count <= 8 and max_len <= 16:
        cols = 1
        rows = math.ceil(count / cols)
        return ("inside-left", cols, rows)

    cols = 2
    rows = math.ceil(count / cols)
    return ("outside", cols, rows)


def _auto_output_filename(
    series_names: Sequence[str], period: str, ratio: tuple[int, int]
) -> str:
    """Build a readable auto-output filename that stays within path limits."""
    names = [n.strip().upper() for n in series_names if n.strip()]
    names_part = "-".join(names[:6])
    if len(names) > 6:
        names_part += f"-plus{len(names) - 6}"
    if len(names_part) > 120:
        digest = hashlib.sha1(names_part.encode("utf-8")).hexdigest()[:10]
        names_part = f"{names_part[:96].rstrip('-')}-h{digest}"
    w, h = ratio
    return f"termseries_{names_part}_{period}_{w}x{h}.png"


def _transform_indexed(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if not ys:
        return list(xs), list(ys)
    base = ys[0]
    return list(xs), [100.0 * y / base for y in ys]


def _transform_drawdown(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if not ys:
        return list(xs), list(ys)
    peak: float | None = None
    dd: list[float] = []
    for y in ys:
        if math.isnan(y):
            dd.append(float("nan"))
        else:
            peak = y if peak is None else max(peak, y)
            dd.append((y / peak - 1.0) * 100.0)
    return list(xs), dd


def _transform_returns(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if len(ys) < 2:
        return list(xs), list(ys)
    return list(xs[1:]), [(ys[i] / ys[i - 1] - 1.0) * 100.0 for i in range(1, len(ys))]


def _transform_cumulative(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if not ys:
        return list(xs), list(ys)
    cumulative: list[float] = []
    total = 0.0
    for y in ys:
        if math.isnan(y):
            cumulative.append(float("nan"))
        else:
            total += y
            cumulative.append(total)
    return list(xs), cumulative


def _transform_delta(
    xs: Sequence[Any], ys: Sequence[float]
) -> tuple[list[Any], list[float]]:
    if len(ys) < 2:
        return list(xs), list(ys)
    return list(xs[1:]), [ys[i] - ys[i - 1] for i in range(1, len(ys))]


_TRANSFORMS: dict[str, _Transform] = {
    "indexed": _transform_indexed,
    "drawdown": _transform_drawdown,
    "returns": _transform_returns,
    "cumulative": _transform_cumulative,
    "delta": _transform_delta,
}


def _render_png(
    series: dict[str, TimeSeries],
    ratio: tuple[int, int],
    period_label: str,
    figsize: tuple[float, float] | None = None,
    color_cycle: str | None = None,
    mode: str = "absolute",
    value_unit: str = "USD",
    style_override: Path | None = None,
    tz: str = "UTC",
    interval_label: str = "Daily",
    line_style: str = "linear",
    xlim: tuple[datetime, datetime] | None = None,
    theme: str = "auto",
    save_dpi: float | None = None,
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
        Chart mode (absolute, indexed, log, drawdown, returns, relative,
        cumulative, delta).
    value_unit : str
        Unit label for the y-axis (e.g. "USD", "C"). Defaults to "USD".
    style_override : Path | None
        Extra .mplstyle file layered on top of the base theme.
    """
    # Resolve target timezone for x-axis display
    target_tz: timezone | ZoneInfo | None
    if tz == "UTC":
        target_tz = timezone.utc
    elif tz == "local":
        target_tz = None  # astimezone(None) gives local tz
    else:
        target_tz = ZoneInfo(tz)

    names = list(series.keys())
    if not names:
        raise ValueError("No data series provided. Pass at least one series.")
    display_names = {_name: _display_series_name(_name) for _name in names}
    legend_placement, legend_cols, legend_rows = _legend_layout(
        [display_names[name] for name in names]
    )

    dark = _detect_dark_terminal(theme)
    base_style = "termseries.dark" if dark else "termseries.light"
    if style_override:
        plt.style.use([base_style, style_override])
    else:
        plt.style.use(base_style)

    if figsize:
        width_in, height_in = figsize
    else:
        ratio_w, ratio_h = ratio
        width_in = 12.0
        height_in = width_in * (ratio_h / ratio_w)
    crowded_legend = legend_placement == "outside"
    if legend_placement == "outside":
        legend_cols = 2
        height_in += 0.45 * legend_rows + 0.5
    if color_cycle:
        cmap = matplotlib.colormaps[color_cycle]
        plt.rcParams["axes.prop_cycle"] = cycler(
            color=[cmap(i) for i in range(cmap.N)]
            if cmap.N <= 20
            else [cmap(x) for x in [i / 10 for i in range(10)]]
        )
    fig, ax = plt.subplots(
        figsize=(width_in, height_in), constrained_layout=not crowded_legend
    )

    _ds_map = {
        "step-pre": "steps-pre",
        "step-post": "steps-post",
        "step-mid": "steps-mid",
    }
    ds = _ds_map.get(line_style, "default")

    if mode == "relative":
        if len(names) != 2:
            raise ValueError(
                "Relative mode requires exactly 2 series (e.g. AAPL MSFT)."
            )
        pts_a = series[names[0]]
        pts_b = series[names[1]]
        closes_a = {dt.astimezone(target_tz).date(): c for dt, c in pts_a}
        closes_b = {dt.astimezone(target_tz).date(): c for dt, c in pts_b}
        common = sorted(closes_a.keys() & closes_b.keys())
        if not common:
            raise RuntimeError(f"No overlapping dates for {names[0]} and {names[1]}.")
        xs = common
        ys = [closes_a[d] / closes_b[d] for d in common]
        n = len(xs)
        marker = "o" if n <= 100 else None
        ms = max(2, 8 - n // 15)
        ax.plot(
            # matplotlib accepts date/datetime x-values at runtime, but its stubs
            # only type the numeric/array overloads.
            xs,  # type: ignore[arg-type]
            ys,
            label=f"{display_names[names[0]]}/{display_names[names[1]]}",
            marker=marker,
            markersize=ms,
            drawstyle=ds,
        )
    else:
        for name, points in series.items():
            xs = [dt.astimezone(target_tz) for dt, _ in points]
            ys = [close for _, close in points]
            transform = _TRANSFORMS.get(mode)
            if transform is not None:
                xs, ys = transform(xs, ys)
            n = len(xs)
            marker = "o" if n <= 100 else None
            ms = max(2, 8 - n // 15)
            ax.plot(
                # See the note above: date/datetime x-values are runtime-valid but
                # untyped in matplotlib's stubs.
                xs,  # type: ignore[arg-type]
                ys,
                label=display_names[name],
                marker=marker,
                markersize=ms,
                drawstyle=ds,
            )
    if mode == "log":
        ax.set_yscale("log")

    if xlim is not None:
        left, right = xlim
        # datetime bounds are runtime-valid but untyped in matplotlib's set_xlim stub.
        ax.set_xlim(left.astimezone(target_tz), right.astimezone(target_tz))  # type: ignore[arg-type]

    is_stock = value_unit == "USD"
    title_labels = {
        "absolute": "Close" if is_stock else "",
        "indexed": "Indexed",
        "log": "Close (log)" if is_stock else "Log",
        "drawdown": "Drawdown",
        "returns": f"{interval_label} Returns",
        "relative": f"{names[0]}/{names[1]}" if mode == "relative" else "",
        "cumulative": "Cumulative",
        "delta": f"{interval_label} Delta",
    }
    prefix = title_labels.get(mode, "")
    if len(names) <= 3 and all(len(display_names[name]) <= 24 for name in names):
        names_str = ", ".join(display_names[name] for name in names)
    else:
        names_str = f"{len(names)} series"
    if prefix:
        ax.set_title(f"{prefix} ({period_label}): {names_str}")
    else:
        ax.set_title(f"{names_str} ({period_label})")
    tz_label = "UTC" if tz == "UTC" else "local" if tz == "local" else tz
    ax.set_xlabel(f"Date ({tz_label})")
    ylabel = {
        "absolute": f"Close ({value_unit})" if is_stock else value_unit,
        "indexed": "% of start",
        "log": f"Close ({value_unit}, log)" if is_stock else f"{value_unit} (log)",
        "drawdown": "% from peak",
        "returns": f"{interval_label} change (%)",
        "relative": f"{names[0]}/{names[1]} ratio" if mode == "relative" else "",
        "cumulative": f"Cumulative ({value_unit})",
        "delta": f"{interval_label} change ({value_unit})",
    }
    ax.set_ylabel(ylabel.get(mode, value_unit))
    legend: Any = None
    if legend_placement == "outside":
        legend = ax.legend(
            ncols=legend_cols,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.32),
            fontsize=max(7, 10 - legend_rows // 2),
            frameon=True,
        )
        fig.subplots_adjust(bottom=min(0.52, 0.16 + 0.08 * legend_rows))
    elif legend_placement == "inside-top-left":
        ax.legend(
            ncols=legend_cols,
            loc="upper left",
            bbox_to_anchor=(0.02, 0.98),
            fontsize=9,
            frameon=True,
            borderaxespad=0.0,
        )
    elif legend_placement == "inside-left":
        ax.legend(
            ncols=legend_cols,
            loc="center left",
            bbox_to_anchor=(0.02, 0.5),
            fontsize=max(8, 10 - max(0, legend_rows - 4)),
            frameon=True,
            borderaxespad=0.0,
        )
    else:
        ax.legend(
            ncols=legend_cols,
            loc="best",
            fontsize=max(8, 10 - max(0, legend_rows - 1)),
            frameon=True,
        )
    fig.autofmt_xdate()

    buf = BytesIO()
    _save_dpi: float | str
    if save_dpi is not None:
        _save_dpi = save_dpi
    elif sys.stdout.isatty():
        px_width = _terminal_pixel_width()
        _save_dpi = px_width / width_in if px_width else "figure"
    else:
        _save_dpi = "figure"
    if crowded_legend and legend is not None:
        # The fixed height/margin heuristics above are an estimate; grow the
        # canvas to whatever the legend actually needs instead of clipping it.
        fig.savefig(
            buf,
            format="png",
            dpi=_save_dpi,
            bbox_inches="tight",
            bbox_extra_artists=[legend],
        )
    else:
        fig.savefig(buf, format="png", dpi=_save_dpi)
    plt.close(fig)
    return buf.getvalue()


def _output_png(
    png: bytes,
    series_names: list[str],
    ratio: tuple[int, int],
    period: str,
    *,
    copy: bool = False,
    output: str = "auto",
    protocol: str = "auto",
) -> None:
    """Handle output of rendered PNG: optional clipboard copy, inline display
    (Kitty TGP / iTerm2 / Sixel), named file write, or raw stdout.

    Parameters
    ----------
    output:
        "auto"   — inline if terminal supports it, else auto-named file (default)
        "inline" — force inline; warn and fall back to file if no protocol detected
        "-"      — write raw PNG bytes to stdout (no terminal escapes)
        other    — write PNG to this path
    protocol:
        "auto"   — detect from terminal environment (default)
        "kitty"  — Kitty Terminal Graphics Protocol
        "iterm2" — iTerm2 OSC 1337 Inline Images Protocol
        "sixel"  — Sixel graphics
    """
    import warnings

    if copy:
        _copy_to_clipboard(png)
        w, h = _png_dimensions(png)
        msg = f"Plot ({w}x{h}) copied to clipboard."
        if _is_docker():
            msg += " (Docker container -- may not reach your local clipboard)"
        elif _is_ssh_session():
            msg += " (remote machine -- may not reach your local clipboard)"
        print(msg)

    # Raw stdout: binary PNG bytes, no terminal escapes
    if output == "-":
        sys.stdout.buffer.write(png)
        sys.stdout.buffer.flush()
        return

    # Named file
    if output not in ("auto", "inline"):
        with open(output, "wb") as f:
            f.write(png)
        print(f"Wrote plot to {output}")
        return

    # --- Inline / auto logic ---

    def _emit_inline() -> bool:
        """Emit PNG inline using the resolved protocol. Returns False when protocol
        is 'auto' and no supported terminal is detected."""
        if not sys.stdout.isatty():
            return False
        if protocol == "kitty":
            _print_kitty_png(png)
        elif protocol == "iterm2":
            _print_iterm2_png(png)
        elif protocol == "sixel":
            _print_sixel_png(png)
        else:  # auto: run detection chain
            if _is_kitty() or _is_ghostty():
                _print_kitty_png(png)
            elif _is_iterm2():
                _print_iterm2_png(png)
            elif _is_sixel_terminal():
                _print_sixel_png(png)
            else:
                return False
        sys.stdout.flush()
        return True

    if output == "inline":
        if not _emit_inline():
            warnings.warn(
                "No inline protocol detected; falling back to file output.",
                stacklevel=2,
            )
            # fall through to auto-named file below
        else:
            return
    else:  # auto
        if protocol != "auto":
            # Explicit protocol: go inline only if auto-detection would have
            if _is_kitty() or _is_ghostty() or _is_iterm2() or _is_sixel_terminal():
                _emit_inline()
                return
            # else fall through to auto-named file
        else:
            if _emit_inline():
                return
            # else fall through to auto-named file
        print("No inline image protocol detected; saving plot to file.")

    # Auto-named file fallback
    out = _auto_output_filename(series_names, period, ratio)
    with open(out, "wb") as f:
        f.write(png)
    print(f"Wrote plot to {out}")
