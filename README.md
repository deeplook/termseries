# termseries

![PyPI](https://img.shields.io/pypi/v/termseries)
![Python](https://img.shields.io/pypi/pyversions/termseries)
![License](https://img.shields.io/github/license/deeplook/termseries)
![CI](https://img.shields.io/github/actions/workflow/status/deeplook/termseries/ci.yml)

Show timeseries data in the terminal using matplotlib. Renders high-quality PNG
charts inline (Kitty, iTerm2, Sixel) or saves to file, with an optional
interactive Textual TUI.

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
```

## Features

- **Multiple chart modes**: absolute, indexed (rebased to 100%), log, drawdown,
  daily returns, relative (price ratio)
- **Terminal image protocols**: auto-detects Kitty, iTerm2, Sixel; falls back
  to writing PNG files
- **Interactive TUI**: built with [Textual](https://textual.textualize.io/) --
  dropdowns for period, ratio, mode, colors, plus ticker input
- **Clipboard copy**: `-c` flag or Ctrl+Y in TUI (macOS, Windows, Linux)
- **Configurable**: aspect ratio (`--ratio`), color cycle (`--colors`),
  dark/light detection

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
