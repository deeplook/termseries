# Installation

```bash
pip install termseries
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install termseries
```

Or run it without installing, via [`uvx`](https://docs.astral.sh/uv/guides/tools/):

```bash
uvx termseries yahoo TSLA AAPL MSFT
```

## Browser charts

```sh
pip install 'termseries[browser]'
# Or install the same extra with uv:
uv tool install 'termseries[browser]'
```

The base installation renders Matplotlib PNGs. The browser extra adds Plotly and
local-timezone detection. Python 3.10 or newer is required. No Plotly account,
notebook, server, or static-image export engine is needed.

Use `termseries --version` to check the installed version and `termseries --help`
for available commands. For repository development, see [Development](development.md).
