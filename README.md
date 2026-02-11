# termseries

![PyPI](https://img.shields.io/pypi/v/termseries)
![Python](https://img.shields.io/pypi/pyversions/termseries)
![License](https://img.shields.io/github/license/deeplook/termseries)
![CI](https://img.shields.io/github/actions/workflow/status/deeplook/termseries/ci.yml)

Show timeseries data in the terminal using matplotlib. Plot stock prices from
Yahoo Finance, sensor data from Home Assistant, or any numeric timeseries from
local CSV files. Renders high-quality PNG charts inline (Kitty, iTerm2, Sixel)
or saves to file, with an optional interactive Textual TUI.

## Features

### Data Sources
- Fetch stock/crypto/index prices from Yahoo Finance via the `yahoo` subcommand
- Plot Home Assistant sensor history via the `ha` subcommand (REST API)
- Load local two-column CSV files (timestamp, value) via the `csv` subcommand
- Auto-detect and skip CSV headers, blank lines, NaN/Inf values
- Accept ISO 8601 timestamps and Unix epochs in CSV files
- Auto-detect the unit of measurement from Home Assistant entity attributes

### Chart Modes
- Absolute values (default), indexed to 100%, logarithmic scale
- Drawdown from running peak, daily returns, and relative price ratio
- Configurable time windows per data source (1h–max for Yahoo, 1h–1y/all for CSV/HA)

### Terminal Rendering
- Auto-detect Kitty, iTerm2, and Sixel-capable terminals for inline PNG display
- Fall back to writing a PNG file when no inline protocol is available
- Auto-detect dark/light terminal background for theme selection
- Force dark/light theme or inline/file output via environment variables

### Interactive TUI
- Full-screen Textual TUI with dropdowns for period, aspect ratio, mode, and color cycle
- Live ticker/entity/file input with immediate re-render on submit
- Debounced chart re-render on terminal resize using cached data
- Auto-reload at a configurable interval (`--reload N`) or toggled with Ctrl+R
- Copy current plot to clipboard with Ctrl+Y

### Customization
- Configurable aspect ratio (`--ratio W:H` or `fit` for terminal-filling)
- Seven built-in color cycles (tab10, Set1, Set2, Dark2, Accent, Pastel1, tab20)
- Layer custom `.mplstyle` overrides on top of the built-in dark/light themes
- Consistent font sizes across terminal widths in TUI mode

### Clipboard & Output
- Copy rendered plot to system clipboard (`-c` or Ctrl+Y in TUI)
- Clipboard warnings when running inside Docker or over SSH
- Built-in `demo` command showcasing multiple chart modes

### Developer Experience
- Fully typed (`py.typed`, mypy-checked)
- Pre-commit hooks for ruff, ruff-format, and mypy
- 130+ unit tests covering all modules
- Docker support with Compose for containerized usage

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

# --- Home Assistant sensors ---

# Plot HA sensor data (requires HASS_URL and HASS_TOKEN env vars)
termseries ha sensor.living_room_temperature sensor.bedroom_temperature

# Last 3 hours of data
termseries ha sensor.living_room_temperature --last 3h

# Last 30 days with explicit unit
termseries ha sensor.living_room_temperature --last 30d --unit '°C'

# Interactive TUI with HA data
termseries -i ha sensor.power_consumption

# --- CSV files ---

# Plot a local CSV (two columns: timestamp, value)
termseries csv /path/to/sensor.csv

# Multiple files, last 7 days, with a custom unit label
termseries csv temp.csv humidity.csv --last 7d --unit '°C'

# Interactive TUI with CSV data
termseries -i csv sensor.csv
```

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
`all` (default), `1h`, `3h`, `6h`, `12h`, `1d`, `2d`, `7d`, `30d`, `90d`,
`1y`. The `--unit` option sets the y-axis label (default: `value`).

The `ha` subcommand uses the same `--last` periods and auto-detects the unit
from the entity's attributes.

## Shared Options

| Option | Description |
|---|---|
| `--ratio W:H` | Figure aspect ratio (default: 4:1) |
| `--mode` | Chart mode: absolute, indexed, log, drawdown, returns, relative |
| `--colors` | Matplotlib color cycle: tab10, Set1, Set2, Dark2, Accent, Pastel1, tab20 |
| `--style PATH` | Extra `.mplstyle` file layered on top of the base theme (see [Custom Styles](#custom-styles)) |
| `-c` / `--copy` | Copy plot to system clipboard |
| `-i` / `--interactive` | Launch Textual TUI |

## Home Assistant Setup

The `ha` subcommand connects to a running Home Assistant instance via the
REST API. Set these environment variables:

```bash
export HASS_URL=http://homeassistant.local:8123
export HASS_TOKEN=your_long_lived_access_token
```

Create a long-lived access token in HA under **Profile > Security > Long-Lived
Access Tokens**. The unit label (y-axis) is auto-detected from the entity's
`unit_of_measurement` attribute; use `--unit` to override.

## Custom Styles

Chart appearance is controlled by Matplotlib `.mplstyle` files. termseries
ships with two built-in themes (`dark` and `light`) that are automatically
selected based on your terminal's background color. You can override any
setting by passing an extra style file with `--style`:

```bash
# Use thinner lines, no markers
termseries --style my-overrides.mplstyle yahoo TSLA AAPL
```

The override file only needs the keys you want to change -- everything else is
inherited from the base theme. See
[`example.mplstyle`](example.mplstyle) for a starting point, or the full
[Matplotlib customization guide](https://matplotlib.org/stable/users/explain/customizing.html)
for all available keys.

Example override file:

```ini
# my-overrides.mplstyle
lines.linewidth:  1.5
lines.marker:     None        # no markers, just lines
figure.dpi:       150         # lower DPI for smaller file size
grid.linestyle:   --          # dashed grid
```

## Environment Variables

| Variable | Effect |
|---|---|
| `HASS_URL` | Home Assistant base URL (e.g. `http://ha.local:8123`) |
| `HASS_TOKEN` | Home Assistant long-lived access token |
| `TERMSERIES_FORCE_INLINE=1` | Try inline output on unrecognized terminals |
| `TERMSERIES_NO_INLINE=1` | Always write PNG file (never inline) |
| `TERMSERIES_DARK=1` | Force dark theme |
| `TERMSERIES_LIGHT=1` | Force light theme |

## Project Structure

```
termseries/
├── src/termseries/
│   ├── __init__.py
│   ├── __main__.py
│   ├── _csv_source.py
│   ├── _ha_source.py
│   ├── _render.py
│   ├── _terminal.py
│   ├── _tui.py
│   ├── _types.py
│   ├── cli.py
│   ├── yahoo.py
│   ├── dark.mplstyle
│   ├── light.mplstyle
│   └── py.typed
├── tests/
│   ├── conftest.py
│   ├── test_csv_source.py
│   ├── test_docker.py
│   ├── test_ha_source.py
│   ├── test_render.py
│   └── test_terminal.py
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   └── publish.yml
│   ├── ISSUE_TEMPLATE/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── dependabot.yml
├── example.mplstyle
├── pyproject.toml
├── Makefile
├── Dockerfile
├── docker-compose.yml
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
