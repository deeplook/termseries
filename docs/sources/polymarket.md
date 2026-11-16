# Polymarket

Plot the price history for a prediction-market outcome:

```sh
termseries polymarket will-bitcoin-hit-150k-in-2026
termseries polymarket will-bitcoin-hit-150k-in-2026 --outcome no --last 30d
```

Market availability and history depend on the source. Use a currently available
market identifier when reproducing these examples.

## Options and sampling

| Option | Description |
|---|---|
| `--outcome` | Outcome label to chart, usually `yes` or `no` for binary markets (default: `yes`) |
| `--interval` | Aggregation interval: `auto` (default), `max`, `all`, `1m`, `1h`, `6h`, `1d`, `1w` |
| `--fidelity` | Data fidelity in minutes for the Polymarket history API (default: `1`) |

When `--interval auto` (the default), termseries picks a sensible interval based
on the period duration:

| Period duration | Auto interval |
|-----------------|--------------|
| ≤ 6 hours        | 1m           |
| ≤ 3 days         | 1h           |
| ≤ 30 days        | 6h           |
| ≤ 180 days       | 1d           |
| > 180 days       | 1w           |
