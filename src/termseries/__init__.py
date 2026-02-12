"""Render time-series data as wide matplotlib plots.

Supports both a one-shot CLI mode and an interactive Textual TUI.  See
``termseries --help`` for full usage details.
"""

from __future__ import annotations

__version__ = "0.1.0"

from termseries.cli import app, csv_cmd, demo, ha, main, yahoo
from termseries.csv_source import (
    _parse_timestamp,
    _read_csv,
    fetch_csv_series,
)
from termseries.ha_source import (
    _detect_unit,
    _fetch_ha_entity,
    _ha_request,
    fetch_ha_series,
)
from termseries.period import (
    TUI_PERIOD_CHOICES,
    filter_period,
    parse_period,
)
from termseries.render import _output_png, _render_png
from termseries.terminal import (
    _copy_to_clipboard,
    _detect_dark_terminal,
    _is_docker,
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
from termseries.tui import _run_interactive
from termseries.types import ColorCycle, Mode, TimeSeries
from termseries.yahoo import _fetch_closes, fetch_yahoo_series

__all__ = [
    "__version__",
    "TimeSeries",
    "Mode",
    "ColorCycle",
    "TUI_PERIOD_CHOICES",
    "parse_period",
    "filter_period",
    "app",
    "main",
    "yahoo",
    "csv_cmd",
    "demo",
    "fetch_yahoo_series",
    "_fetch_closes",
    "fetch_csv_series",
    "fetch_ha_series",
    "_ha_request",
    "_fetch_ha_entity",
    "_detect_unit",
    "ha",
    "_read_csv",
    "_parse_timestamp",
    "_render_png",
    "_output_png",
    "_run_interactive",
    "_is_kitty",
    "_is_iterm2",
    "_is_sixel_terminal",
    "_is_docker",
    "_is_ssh_session",
    "_detect_dark_terminal",
    "_print_kitty_png",
    "_print_sixel_png",
    "_print_iterm2_png",
    "_png_dimensions",
    "_copy_to_clipboard",
    "_parse_ratio",
]
