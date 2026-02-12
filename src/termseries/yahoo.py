"""Yahoo Finance data source."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from termseries.period import filter_period, yahoo_auto_interval, yahoo_covering_range
from termseries.types import TimeSeries


def _fetch_closes(
    ticker: str, period: str, interval: str = "1d"
) -> list[tuple[datetime, float]]:
    """Return list of (UTC datetime, close) points for the requested period."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?range={period}&interval={interval}"
    )
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    payload = resp.json()

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError(f"{ticker}: unexpected Yahoo response: {payload!r}")

    series = result[0]
    timestamps = series.get("timestamp") or []
    quotes = ((series.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quotes.get("close") or []

    points: list[tuple[datetime, float]] = []
    for ts, close in zip(timestamps, closes, strict=False):
        if close is None:
            continue
        points.append((datetime.fromtimestamp(ts, tz=timezone.utc), float(close)))

    if not points:
        raise RuntimeError(f"{ticker}: no close data returned for period={period}.")

    return points


def fetch_yahoo_series(
    tickers: list[str],
    period: str,
    interval: str = "auto",
) -> dict[str, TimeSeries]:
    """Fetch close-price time series from Yahoo Finance for each ticker.

    Returns a dict mapping ticker symbol to its list of (datetime, close) points.
    Tickers are deduplicated and uppercased; order is preserved.

    Non-native Yahoo periods are handled by overfetching the next-larger
    native range and trimming client-side.
    """
    resolved = yahoo_auto_interval(period) if interval == "auto" else interval
    covering = yahoo_covering_range(period)
    need_trim = covering != period

    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not tickers:
        raise ValueError(
            "No ticker symbols provided. Pass at least one ticker (e.g. TSLA)."
        )

    result: dict[str, TimeSeries] = {}
    for ticker in tickers:
        points = _fetch_closes(ticker, covering, resolved)
        if need_trim:
            points = filter_period(points, period)
        result[ticker] = points
    return result
