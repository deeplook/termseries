# termseries

![PyPI](https://img.shields.io/pypi/v/termseries)
![Python](https://img.shields.io/pypi/pyversions/termseries)
![License](https://img.shields.io/github/license/deeplook/termseries)
![CI](https://img.shields.io/github/actions/workflow/status/deeplook/termseries/ci.yml)

Show timeseries data in the terminal using matplotlib. Plot stock prices from
Yahoo Finance or any numeric timeseries from local CSV files. Renders
high-quality PNG charts inline (Kitty, iTerm2, Sixel) or saves to file, with an
optional interactive Textual TUI.

## Installation

```bash
pip install termseries
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install termseries
```

## Quick Start

```bash
# Plot stock prices (7-day default)
termseries yahoo TSLA AAPL MSFT

# Indexed comparison over 1 month
termseries --mode indexed yahoo --period 1mo TSLA AAPL MSFT

# Log scale over 5 years
termseries --mode log yahoo --period 5y AAPL MSFT GOOGL

# Drawdown chart
termseries --mode drawdown yahoo --period 1y TSLA AAPL

# Relative price ratio (exactly 2 tickers)
termseries --mode relative yahoo --period 1y AAPL MSFT

# Copy plot to clipboard
termseries yahoo -c TSLA AAPL

# Interactive TUI
termseries -i yahoo TSLA

# --- CSV files ---

# Plot a local CSV (two columns: timestamp, value)
termseries csv /path/to/sensor.csv

# Multiple files, last 7 days, with a custom unit label
termseries csv temp.csv humidity.csv --last 7d --unit '°C'

# Interactive TUI with CSV data
termseries -i csv sensor.csv
```

## Features

- **Multiple data sources**: Yahoo Finance (`yahoo`) for stocks, local CSV files
  (`csv`) for any numeric timeseries (sensors, metrics, etc.)
- **Multiple chart modes**: absolute, indexed (rebased to 100%), log, drawdown,
  daily returns, relative (price ratio)
- **Terminal image protocols**: auto-detects Kitty, iTerm2, Sixel; falls back
  to writing PNG files
- **Interactive TUI**: built with [Textual](https://textual.textualize.io/) --
  dropdowns for period, ratio, mode, colors, plus ticker/file input
- **Clipboard copy**: `-c` flag or Ctrl+Y in TUI (macOS, Windows, Linux)
- **Configurable**: aspect ratio (`--ratio`), color cycle (`--colors`),
  dark/light detection

## CSV File Format

The `csv` subcommand expects two-column CSV files (timestamp, value). Header
rows are auto-detected and skipped. Timestamps can be ISO 8601 strings or Unix
epochs. Blank lines and NaN/Inf values are silently skipped.

```csv
2024-01-01T00:00:00Z,20.5
2024-01-02T00:00:00Z,21.0
2024-01-03T00:00:00Z,22.1
```

Each file becomes one series labelled by its filename (without extension). The
`--last` option filters to a time window from the most recent data point:
`all` (default), `1d`, `7d`, `30d`, `90d`, `1y`. The `--unit` option sets the
y-axis label (default: `value`).

## Shared Options

| Option | Description |
|---|---|
| `--ratio W:H` | Figure aspect ratio (default: 4:1) |
| `--mode` | Chart mode: absolute, indexed, log, drawdown, returns, relative |
| `--colors` | Matplotlib color cycle: tab10, Set1, Set2, Dark2, Accent, Pastel1, tab20 |
| `-c` / `--copy` | Copy plot to system clipboard |
| `-i` / `--interactive` | Launch Textual TUI |

## Environment Variables

| Variable | Effect |
|---|---|
| `TERMSERIES_FORCE_INLINE=1` | Try inline output on unrecognized terminals |
| `TERMSERIES_NO_INLINE=1` | Always write PNG file (never inline) |
| `TERMSERIES_DARK=1` | Force dark theme |
| `TERMSERIES_LIGHT=1` | Force light theme |

## Project Structure

```
termseries/
├── src/
│   └── termseries/
│       ├── __init__.py
│       ├── __main__.py
│       └── py.typed
├── tests/
├── pyproject.toml
├── Makefile
├── Dockerfile
└── README.md
```

## Development

```bash
git clone https://github.com/deeplook/termseries.git
cd termseries
uv sync --all-extras
uv run pre-commit install
make test
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
