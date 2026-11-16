# CSV files

The `csv` subcommand expects two-column CSV files (timestamp, value). Header
rows are auto-detected and skipped. Timestamps can be ISO 8601 strings or Unix
epochs. Blank lines, blank values, and NaN/Inf values are silently skipped.
Naive timestamps (without an explicit offset) are assumed to be UTC.

```csv
2024-01-01T00:00:00Z,20.5
2024-01-02T00:00:00Z,21.0
2024-01-03T00:00:00Z,22.1
```

A plain two-column file becomes one series labelled by its filename (without
extension). A CSV with a header row and more than one value column plots
*every* column by default, each labelled `<stem>.<column>`:

```csv
timestamp,temp,humidity
2024-01-01T00:00:00Z,20.5,50.0
2024-01-02T00:00:00Z,21.0,55.0
```

```bash
termseries csv sensors.csv --last 7d
```

Append `:col1,col2` to a path to plot only specific columns instead of every
one:

```bash
termseries csv sensors.csv:temp,humidity --last 7d
```

The `--last` filters to a now-anchored time window using free-form
`<number><unit>` syntax (e.g. `7d`, `2w`, `3mo`). Special values: `max`
(default) shows all data with the x-axis extending to now; `auto` auto-fits
the x-axis to the data with no empty space. The `--unit` option sets the
y-axis label (default: `value`).

For high-frequency data, `--resample` reduces points into fixed, UTC-aligned
buckets before rendering. Use `--aggregate` to select the bucket reducer
(`mean` by default; also `median`, `min`, `max`, `sum`, `count`, `first`, and
`last`). The plotted timestamp is the start of each bucket. For example:

```bash
termseries csv data/heart.csv --last 1mo --resample 1m --aggregate mean --unit bpm
```

`--last 1m` means the last minute; use `--last 1mo` for the last month.


See [Time ranges](../time-ranges.md) and [Chart modes and gaps](../modes.md).
