"""Render time-series data as wide matplotlib plots.

Supports both a one-shot CLI mode and an interactive Textual TUI.  See
``termseries --help`` for full usage details.
"""

from __future__ import annotations

__version__ = "0.3.0"

from termseries.cli import app, csv_cmd, demo, hass, main
from termseries.cli import polymarket as polymarket_cmd
from termseries.cli import yahoo as yahoo_cmd
from termseries.csv_source import (
    _parse_timestamp,
    _read_csv,
    fetch_csv_series,
    resample_series,
)
from termseries.gaps import insert_gaps
from termseries.hass_source import (
    _detect_unit,
    _fetch_hass_entity,
    _hass_request,
    fetch_hass_series,
)
from termseries.period import (
    TUI_PERIOD_CHOICES,
    _to_date_cutoff,
    filter_period,
    parse_period,
)
from termseries.polymarket import fetch_polymarket_series
from termseries.render import (
    _output_png,
    _render_png,
    _transform_cumulative,
    _transform_delta,
    _transform_drawdown,
    _transform_indexed,
    _transform_returns,
)
from termseries.terminal import (
    _VALID_OUTPUTS,
    _VALID_PROTOCOLS,
    _VALID_THEMES,
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
    _terminal_pixel_width,
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
    "_to_date_cutoff",
    "app",
    "main",
    "yahoo_cmd",
    "polymarket_cmd",
    "csv_cmd",
    "demo",
    "fetch_yahoo_series",
    "fetch_polymarket_series",
    "_fetch_closes",
    "fetch_csv_series",
    "resample_series",
    "fetch_hass_series",
    "_hass_request",
    "_fetch_hass_entity",
    "_detect_unit",
    "hass",
    "_read_csv",
    "_parse_timestamp",
    "_render_png",
    "_output_png",
    "_transform_indexed",
    "_transform_drawdown",
    "_transform_returns",
    "_transform_cumulative",
    "_transform_delta",
    "_run_interactive",
    "_VALID_THEMES",
    "_VALID_OUTPUTS",
    "_VALID_PROTOCOLS",
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
    "_terminal_pixel_width",
    "insert_gaps",
]
