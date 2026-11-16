# Time ranges

Use `--last` for a rolling window ending now, `--from` and `--to` for a fixed
inclusive interval, or `--first` for a duration beginning at the earliest
returned data point. `--to` defaults to `now`; these forms cannot be combined.
`--period` remains a compatibility alias for `--last`.

```bash
termseries yahoo TSLA --last 7d
termseries yahoo TSLA --from 2026-07-01 --to 2026-07-31
termseries csv readings.csv --from ytd
termseries csv readings.csv --first 7d
```

`--from` and `--to` accept ISO-8601 dates/times (such as `2026-07-01` or
`2026-07-01T12:00:00Z`), `now`, and the same relative/calendar expressions as
`--last` (such as `7d` and `ytd`).

Partial dates/times are zero-padded to a full timestamp, and the direction of
padding depends on which bound you're filling in, so the range stays fully
inclusive: `--from` rounds *down* to the start of the given granularity, while
`--to` rounds *up* to its end (calendar-aware, so February gets 28 or 29 days
correctly). For example, `--from 2025 --to 2026` expands to
`2025-01-01T00:00:00` through `2026-12-31T23:59:59` — covering all of both
years — not just the first instant of 2026. Likewise `--from 2026-05` starts
at `2026-05-01T00:00:00` and `--to 2026-05` ends at `2026-05-31T23:59:59`.
A fully-specified timestamp on either side is used as-is.

Warning: `--first` is data-anchored, not calendar-anchored. Its effective start
can change when a source adds or backfills older history, so use `--from` and
`--to` for reproducible charts. It accepts durations only (for example `7d`,
`2w`, or `3mo`).

`--last` accepts free-form `<number><unit>` values:

| Unit | Example | Meaning |
|------|---------|---------|
| `m`  | `30m`   | minutes |
| `h`  | `6h`    | hours   |
| `d`  | `14d`   | days    |
| `w`  | `2w`    | weeks   |
| `mo` | `3mo`   | months (≈30 days) |
| `y`  | `1y`    | years (≈365 days) |
| `ytd`| `ytd`   | year-to-date (from Jan 1st) |
| `mtd`| `mtd`   | month-to-date (from 1st of month) |
| `wtd`| `wtd`   | week-to-date (from Monday) |
| `dtd`| `dtd`   | day-to-date (from midnight) |
| `htd`| `htd`   | hour-to-date (from start of hour) |
| `max`|         | all data, x-axis extends to now |
| `auto`|        | all data, x-axis fits to data |

Calendar boundaries for `ytd`/`mtd`/`wtd`/`dtd`/`htd` are computed in the
timezone set by `--tz` (default UTC) — e.g. `--tz local --last dtd` means
"since local midnight", not UTC midnight.

For Yahoo, non-native periods (e.g. `14d`, `2w`) are handled automatically by
overfetching the next-larger native range and trimming client-side.
