"""Chart rendering and output dispatch."""

from __future__ import annotations

import os
import sys
from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt

from termseries._terminal import (
    _copy_to_clipboard,
    _detect_dark_terminal,
    _is_iterm2,
    _is_kitty,
    _is_sixel_terminal,
    _is_ssh_session,
    _png_dimensions,
    _print_iterm2_png,
    _print_kitty_png,
    _print_sixel_png,
)
from termseries._types import TimeSeries


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
            xs = [dt for dt, _ in points]
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
