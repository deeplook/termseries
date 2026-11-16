# termseries

Render time series in your terminal or in an interactive browser chart. Fetch stock
prices from Yahoo Finance, prediction-market histories from Polymarket, sensor
readings from Home Assistant, numeric Obsidian daily-note fields, or local CSV data.

![A stock chart rendered by termseries](assets/termseries-yahoo.png)

## Start here

```sh
pip install termseries
termseries yahoo TSLA AAPL
```

- [Installation](installation.md) — pip, uv, and optional browser dependencies.
- [Quick start](getting-started.md) — create terminal, PNG, and HTML output.
- [Examples](examples.md) — recipes for every source and chart mode.

## Choose an output

| Output | Use it for | Guide |
| --- | --- | --- |
| Terminal / PNG | Quick plots, scripts, files, clipboard and terminal graphics | [Output](output.md) |
| Interactive TUI | Change chart settings and reload source data in the terminal | [Terminal UI](tui.md) |
| Browser HTML | Hover, zoom, pan, embedding and offline sharing | [Browser and Python](browser.md) |

Matplotlib is the default. The optional Plotly backend exports full pages or HTML
fragments and does not require a Plotly account or server. Compare the renderers
in the [interactive gallery](gallery.md).

## Explore the reference

[CLI options](cli.md), [time ranges](time-ranges.md), [chart modes and gaps](modes.md),
[seasonal overlays](seasonal.md), [configuration](configuration.md), and
[Matplotlib styles](styles.md) describe the controls in detail.

For changes in version 0.5.0, see the [changelog](changelog.md). The project is
[MIT licensed](license.md).
