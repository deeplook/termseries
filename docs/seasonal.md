# Seasonal overlays

`--mode seasonal` wraps a multi-cycle series into overlaid per-cycle lines —
e.g. one line per year, so you can compare the same time of year across
multiple years at a glance. Use `--cycle` to pick the cycle length:

```bash
# One line per calendar year (default cycle)
termseries --mode seasonal yahoo TSLA --from 2022

# One line per calendar quarter (Q1/Q2/Q3/Q4 all overlay onto the same
# Jan-Mar-shaped window, so the x-axis shows a single quarter's width)
termseries --mode seasonal --cycle quarter yahoo TSLA --last 2y

# One line per calendar week, Monday-aligned
termseries --mode seasonal --cycle 1w yahoo TSLA --last 6mo

# Arbitrary duration cycles (e.g. 90-day chunks)
termseries --mode seasonal --cycle 90d yahoo TSLA --last 1y
```

Each output series is labeled with its cycle, e.g. `TSLA (2024)`,
`TSLA (2024 Q1)`, `TSLA (2024-W03)`. The x-axis label and tick formatting
adapt to the cycle:

| `--cycle` | X-axis label | Tick format |
|---|---|---|
| `year` (default) | `Month of year` | Month names (`Jan`, `Feb`, …), centered mid-month |
| `quarter` | `Day of quarter` | Day offset within the quarter (`Day 1`…`Day 92`) |
| a 7-day duration (`1w`/`7d`) | `Day of week` | Weekday names, Monday-aligned, centered on each day |
| any other duration | `Day of chunk` | Day offset within the chunk |

For the Matplotlib renderer, the timezone is only shown in the x-axis label when it can actually affect
what's displayed (`quarter` and week cycles, which are day-or-finer
calendar-aligned); it's omitted for `year` (month-level display) and other
duration cycles (elapsed-time based, timezone-invariant).

If `--cycle` is as long as or longer than the available data, only one
chunk is produced and a warning is printed (CLI) or shown as a notification
(TUI) instead of failing. `--mode seasonal` works with `--interactive` (`-i`)
too, wrapping freshly fetched data on every redraw — the cycle length comes
from `--cycle` at launch (no in-TUI cycle selector yet).

For [browser output](browser.md), use `--backend plotly` with the same mode and
cycle options. The browser renderer uses adaptive ticks and displays cycle
positions in hover labels, rather than claiming the synthetic reference year is
an observation year.
