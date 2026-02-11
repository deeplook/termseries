"""Yahoo Finance data source."""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from termseries._types import TimeSeries

_AUTO_INTERVAL: dict[str, str] = {
    "1d": "5m",
    "5d": "15m",
    "7d": "15m",
}


def _resolve_interval(period: str, interval: str) -> str:
    """Return a concrete Yahoo interval string.

    If *interval* is ``"auto"``, pick a sensible default based on *period*;
    otherwise return *interval* unchanged.
    """
    if interval != "auto":
        return interval
    return _AUTO_INTERVAL.get(period, "1d")


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
    """
    resolved = _resolve_interval(period, interval)
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not tickers:
        raise ValueError(
            "No ticker symbols provided. Pass at least one ticker (e.g. TSLA)."
        )
    return {ticker: _fetch_closes(ticker, period, resolved) for ticker in tickers}
