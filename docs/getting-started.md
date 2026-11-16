# Quick start

Install termseries, then choose a source and an output:

```sh
termseries yahoo TSLA AAPL
termseries --mode indexed yahoo --last 1y TSLA NVDA
termseries --output chart.png yahoo --last 1mo TSLA
```

The default backend displays a PNG inline in a compatible terminal, otherwise it
saves a file. `--mode indexed` rebases each series to 100 at its own first value.
Options such as `--mode`, `--theme`, `--backend`, and `--output` go before the source
command; source options such as `--last`, `--interval`, and `--unit` go after it.

## Start without a network connection

Create `temperature.csv`:

```csv
timestamp,value
2026-01-01T00:00:00Z,20.1
2026-01-01T01:00:00Z,20.5
2026-01-01T02:00:00Z,21.2
2026-01-01T03:00:00Z,20.8
```

```sh
termseries --output temperature.png csv temperature.csv --last auto --unit °C
```

`auto` fits the horizontal axis to the available observations. `max` also loads all
observations but extends the axis to now. Use explicit bounds for reproducible
comparisons; see [Time ranges](time-ranges.md).

## Create a browser chart

After installing the [browser extra](installation.md#browser-charts):

```sh
termseries --backend plotly --ratio 16:9 --theme light --output temperature.html \
  --open csv temperature.csv --last auto --unit °C
```

Hover for values, drag to zoom, and click legend entries to hide or show a series.
The file is self-contained and works offline. It contains a snapshot, so zooming
does not fetch new data.

## Explore in the terminal

```sh
termseries -i yahoo TSLA NVDA
```

The [interactive TUI](tui.md) can change sources, chart mode, period, and colors,
and can reload data. Browser and TUI interaction are separate output modes.

Continue with [Examples](examples.md), [Chart modes](modes.md), or the
[CLI reference](cli.md).
