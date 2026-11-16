# Yahoo Finance

Fetch stock, cryptocurrency, or index prices:

```sh
termseries yahoo TSLA AAPL
termseries --mode indexed yahoo --last 1y TSLA NVDA
termseries yahoo TSLA --interval 1m --last 1d
```

## Options and sampling

| Option | Description |
|---|---|
| `--last` | Rolling chart range ending now (default: `7d`). Any `<number><unit>`, `max`, or `auto`; `--period` is an alias |
| `--from`, `--to` | Inclusive fixed bounds; `--to` defaults to now |
| `--first` | Data-anchored duration; may change when older history is backfilled |
| `--interval` | Data interval: auto (default), 1m, 5m, 15m, 30m, 60m, 90m, 1d |

When `--interval auto` (the default), termseries picks a sensible interval based
on the period duration:

| Period duration | Auto interval |
|-----------------|--------------|
| ≤ 1 day         | 5m           |
| ≤ 7 days        | 15m          |
| > 7 days        | 1d           |

Yahoo requests share one session per fetch and pause two seconds between
unique tickers. On HTTP 429, termseries retries twice, waiting approximately
30 seconds and then 60 seconds (plus jitter), or longer if Yahoo supplies a
`Retry-After` header. Retry waits are logged. Persistent rate limits stop the
fetch with an actionable error; other HTTP and network errors fail immediately.

Termseries already uses the simple `Mozilla/5.0` User-Agent that worked in
our downloader checks. Splitting a range into more requests does not resolve
an IP/client block, so ranges are fetched in one request per ticker.

See [Browser charts and Python](../browser.md) for fetching Yahoo observations
programmatically and embedding a TSLA/NVDA comparison. Yahoo access requires a
network connection; persistent source throttling cannot be fixed by chart settings.
