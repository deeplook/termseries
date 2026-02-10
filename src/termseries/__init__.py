"""Render time-series data as wide matplotlib plots.

Supports both a one-shot CLI mode and an interactive Textual TUI.  See
``termseries --help`` for full usage details.
"""

from __future__ import annotations

__version__ = "0.1.0"

from termseries._render import _output_png, _render_png
from termseries._terminal import (
    _copy_to_clipboard,
    _detect_dark_terminal,
    _is_iterm2,
    _is_kitty,
    _is_sixel_terminal,
    _is_ssh_session,
    _parse_ratio,
    _png_dimensions,
    _print_iterm2_png,
    _print_kitty_png,
    _print_sixel_png,
)
from termseries._tui import _run_interactive
from termseries._types import ColorCycle, Mode, TimeSeries, YahooPeriod
from termseries.cli import app, demo, main, yahoo
from termseries.yahoo import _fetch_closes, fetch_yahoo_series

__all__ = [
    "__version__",
    "TimeSeries",
    "Mode",
    "ColorCycle",
    "YahooPeriod",
    "app",
    "main",
    "yahoo",
    "demo",
    "fetch_yahoo_series",
    "_fetch_closes",
    "_render_png",
    "_output_png",
    "_run_interactive",
    "_is_kitty",
    "_is_iterm2",
    "_is_sixel_terminal",
    "_is_ssh_session",
    "_detect_dark_terminal",
    "_print_kitty_png",
    "_print_sixel_png",
    "_print_iterm2_png",
    "_png_dimensions",
    "_copy_to_clipboard",
    "_parse_ratio",
]
