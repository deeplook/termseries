"""Yahoo Finance data source."""

from __future__ import annotations

import logging
import math
import random
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from termseries.period import (
    filter_period,
    resolve_tz,
    yahoo_auto_interval,
    yahoo_covering_range,
)
from termseries.types import TimeSeries

_LOGGER = logging.getLogger(__name__)
_RATE_LIMIT_RETRIES = 2
_TICKER_PAUSE = 2


def _retry_delay(response: requests.Response, attempt: int) -> float:
    """Honor Retry-After without shortening the exponential backoff."""
    delay = float(30 * 2**attempt)
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            server_delay = float(retry_after)
        except ValueError:
            try:
                server_delay = (
                    parsedate_to_datetime(retry_after).timestamp() - time.time()
                )
            except (TypeError, ValueError, OverflowError):
                server_delay = 0
        if math.isfinite(server_delay):
            delay = max(delay, server_delay)
    return delay + random.uniform(0, 1)


def _fetch_closes(
    ticker: str,
    period: str,
    interval: str = "1d",
    *,
    session: requests.Session | None = None,
) -> list[tuple[datetime, float]]:
    """Return list of (UTC datetime, close) points for the requested period."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?range={period}&interval={interval}"
    )
    with requests.Session() if session is None else nullcontext(session) as client:
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            try:
                resp = client.get(
                    url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15
                )
                if resp.status_code != 429:
                    resp.raise_for_status()
                    break
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"Yahoo Finance request failed for {ticker}: {exc}"
                ) from exc
            resp.close()
            if attempt == _RATE_LIMIT_RETRIES:
                raise RuntimeError(
                    f"Yahoo Finance request failed for {ticker}: HTTP 429 "
                    "Too Many Requests after backoff; stop and retry later. "
                    "Smaller ranges cannot fix an IP/client block."
                )
            delay = _retry_delay(resp, attempt)
            _LOGGER.warning(
                "%s: Yahoo returned HTTP 429; retrying in %.1fs (%d/%d).",
                ticker,
                delay,
                attempt + 1,
                _RATE_LIMIT_RETRIES,
            )
            time.sleep(delay)
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
    *,
    tz: str = "UTC",
) -> dict[str, TimeSeries]:
    """Fetch close-price time series from Yahoo Finance for each ticker.

    Returns a dict mapping ticker symbol to its list of (datetime, close) points.
    Tickers are deduplicated and uppercased; order is preserved.

    Non-native Yahoo periods are handled by overfetching the next-larger
    native range and trimming client-side. *tz* controls which timezone
    to-date periods (ytd/mtd/wtd/dtd/htd) anchor their calendar boundary in.
    """
    resolved = yahoo_auto_interval(period) if interval == "auto" else interval
    covering = yahoo_covering_range(period)
    need_trim = covering != period
    now = datetime.now(timezone.utc) if need_trim else None
    resolved_tz = resolve_tz(tz)

    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))
    if not tickers:
        raise ValueError(
            "No ticker symbols provided. Pass at least one ticker (e.g. TSLA)."
        )

    result: dict[str, TimeSeries] = {}
    with requests.Session() as session:
        for index, ticker in enumerate(tickers):
            if index:
                time.sleep(_TICKER_PAUSE)
            points = _fetch_closes(ticker, covering, resolved, session=session)
            if need_trim:
                points = filter_period(points, period, reference=now, tz=resolved_tz)
                if not points:
                    raise RuntimeError(
                        f"{ticker}: no data left after trimming to period={period}."
                    )
            result[ticker] = points
    return result
