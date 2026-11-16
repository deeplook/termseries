# Chart modes and gaps

Modes apply to every source and both rendering backends. Pass `--mode` before the
source command. Data must have a meaningful baseline and unit for the chosen mode.

| Mode | What it shows |
| --- | --- |
| `absolute` | Original values (default) |
| `indexed` | Values rebased to 100 at each series' first observation |
| `log` | Original values on a logarithmic y-axis |
| `drawdown` | Percentage change from the running peak |
| `returns` | Percentage change from the preceding observation |
| `relative` | Ratio of exactly two series, joined by display-timezone calendar date |
| `cumulative` | Running sum of values |
| `delta` | Difference from the preceding observation |
| `seasonal` | Cycles overlaid on a shared reference window |

```sh
termseries --mode indexed yahoo --last 1y TSLA NVDA
termseries --mode drawdown yahoo --last 1y TSLA
termseries --mode cumulative csv readings.csv --last auto
termseries --mode relative yahoo --last 1y AAPL MSFT
```

Indexed series use their own first returned observations; these may not share the
same timestamp. A zero or missing indexed baseline cannot produce meaningful
indexed values. Relative mode uses a daily join even for intraday input. Log
charts require positive values. See [Seasonal overlays](seasonal.md) for cycle
selection and [Browser charts](browser.md) for renderer details.

## Missing observations

`--gaps connect` (default) does not insert temporal line breaks. `--gaps show`
detects missing intervals and breaks the line while preserving elapsed time:

```sh
termseries --gaps show hass sensor.temperature --last 7d
termseries --gaps 1h csv readings.csv --last auto
```

Detection requires at least three points. Intervals must exceed 1.5 times the
median positive interval. A duration such as `1h` adds another requirement: the
interval must exceed that duration too. The duration does not replace the cadence
rule. Both comparisons are strict; duplicate timestamps are ignored when estimating
cadence.

A NaN sentinel breaks the line; no zero fill, interpolation or compression of
weekends/market closures is implied. Invalid mathematical results remain missing
even with `connect`. Existing returns and delta calculations can propagate a gap
to an adjacent value because gap insertion precedes those transforms.

## Line styles

`--line-style` accepts `linear`, `step-pre`, `step-post`, and `step-mid`. Steps are
useful for discrete states such as sleep stages or thermostat settings. Compare
actual output in the [renderer gallery](gallery.md).
