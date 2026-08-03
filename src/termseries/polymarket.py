"""Polymarket market data source."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from termseries.period import filter_period, polymarket_covering_range
from termseries.types import TimeSeries

_CLOB_URL = "https://clob.polymarket.com"
_GAMMA_URL = "https://gamma-api.polymarket.com"
_HEADERS = {"User-Agent": "termseries/0.1.0"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SEARCH_STOPWORDS = {
    "will",
    "hit",
    "reach",
    "price",
    "what",
    "when",
    "in",
    "by",
    "the",
    "a",
    "an",
    "of",
}
_POLY_UPPER_TOKENS = {
    "afd",
    "bsw",
    "btc",
    "cdu",
    "eu",
    "eth",
    "fdp",
    "spd",
    "uk",
    "usa",
}


def _get_json(url: str, *, params: dict[str, Any] | None = None) -> object:
    """Fetch JSON from *url* and raise a readable error on HTTP failures."""
    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Polymarket request failed for {url}: {exc}") from exc
    return resp.json()


def _normalize_market_ref(value: str) -> str:
    """Accept a bare slug or a Polymarket frontend URL and return the slug."""
    ref = value.strip()
    if not ref:
        return ref
    if "://" not in ref:
        return ref.strip("/")

    parsed = urlparse(ref)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "event":
        return path_parts[1]
    return path_parts[-1] if path_parts else ref


def _slug_to_query(slug: str) -> str:
    """Turn a slug-like string into a search query."""
    parts = [part for part in re.split(r"[-_/]+", slug.casefold()) if part]
    filtered = [part for part in parts if part not in _SEARCH_STOPWORDS]
    return " ".join(filtered or parts)


def _tokenize(value: str) -> set[str]:
    """Return a lowercase token set for rough matching."""
    return set(_TOKEN_RE.findall(value.casefold()))


def _parse_string_list(value: object, field: str, slug: str) -> list[str]:
    """Return a list[str] from either a raw list or a JSON-encoded string."""
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{slug}: Polymarket field {field!r} was not valid JSON."
            ) from exc
        if not isinstance(parsed, list):
            raise RuntimeError(f"{slug}: Polymarket field {field!r} was not a list.")
        items = parsed
    else:
        raise RuntimeError(f"{slug}: Polymarket field {field!r} was missing.")

    result = [str(item).strip() for item in items if str(item).strip()]
    if not result:
        raise RuntimeError(f"{slug}: Polymarket field {field!r} was empty.")
    return result


def _humanize_tokens(value: str) -> str:
    """Convert slug tokens into a compact human label."""
    tokens = [part for part in value.split("-") if part]
    if not tokens:
        return value
    words: list[str] = []
    for token in tokens:
        if token in _POLY_UPPER_TOKENS or (len(token) <= 3 and token.isalpha()):
            words.append(token.upper())
        else:
            words.append(token.capitalize())
    return " ".join(words)


def _display_market_name(payload: Mapping[str, object]) -> str:
    """Return a compact display name for a Polymarket market payload."""
    question = str(payload.get("question") or "").strip()
    slug = str(payload.get("slug") or "").strip()
    if question:
        m = re.match(
            r"^Will (.+?) win the most seats in .+\?$",
            question,
            flags=re.IGNORECASE,
        )
        if m is not None:
            return m.group(1).strip()
        return question.rstrip("?")
    if slug.startswith("will-") and "-win-" in slug:
        inner = slug[len("will-") : slug.index("-win-")]
        return _humanize_tokens(inner)
    return slug or "Polymarket"


def _market_payloads_from_event_payload(
    slug: str, payload: object
) -> list[dict[str, object]]:
    """Extract market payloads from an event response."""
    if not isinstance(payload, dict):
        raise RuntimeError(f"{slug}: unexpected Polymarket event response: {payload!r}")

    markets = payload.get("markets")
    if not isinstance(markets, list) or not markets:
        raise RuntimeError(f"{slug}: event has no markets.")

    payloads = [market for market in markets if isinstance(market, dict)]
    if not payloads:
        raise RuntimeError(f"{slug}: event has no usable market entries.")
    return payloads


def _parse_iso_datetime(value: object) -> datetime:
    """Parse an ISO8601 timestamp used by Polymarket."""
    if not isinstance(value, str) or not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _market_match_score(
    query_slug: str, market: dict[str, object]
) -> tuple[int, int, int, float]:
    """Rank a candidate market for fuzzy resolution."""
    query_tokens = _tokenize(query_slug)
    slug_tokens = _tokenize(str(market.get("slug") or ""))
    question_tokens = _tokenize(str(market.get("question") or ""))
    overlap = len(query_tokens & (slug_tokens | question_tokens))
    active = 1 if bool(market.get("active")) else 0
    open_market = 1 if not bool(market.get("closed")) else 0
    end_dt = _parse_iso_datetime(market.get("endDate"))
    return (overlap, active, open_market, end_dt.timestamp())


def _search_market_payload(slug: str) -> dict[str, object]:
    """Search Gamma for the closest market to a non-canonical slug."""
    payload = _get_json(
        f"{_GAMMA_URL}/public-search", params={"q": _slug_to_query(slug)}
    )
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{slug}: unexpected Polymarket search response: {payload!r}"
        )

    candidates: list[dict[str, object]] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        markets = event.get("markets") or []
        if not isinstance(markets, list):
            continue
        for market in markets:
            if isinstance(market, dict):
                candidates.append(market)

    if not candidates:
        raise RuntimeError(f"{slug}: no Polymarket market matched this query.")

    best = max(candidates, key=lambda market: _market_match_score(slug, market))
    return best


def _resolve_market_payloads(slug: str) -> list[dict[str, object]]:
    """Resolve a Polymarket market or event slug to one or more market payloads."""
    try:
        payload = _get_json(f"{_GAMMA_URL}/markets/slug/{slug}")
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise
        try:
            event_payload = _get_json(f"{_GAMMA_URL}/events/slug/{slug}")
        except RuntimeError as event_exc:
            if "404" not in str(event_exc):
                raise
            return [_search_market_payload(slug)]
        return _market_payloads_from_event_payload(slug, event_payload)

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{slug}: unexpected Polymarket market response: {payload!r}"
        )
    return [payload]


def _resolve_market_token(slug: str, outcome: str) -> tuple[str, str]:
    """Resolve a market or event slug and outcome label to a tradable token ID."""
    payloads = _resolve_market_payloads(slug)
    if len(payloads) != 1:
        raise RuntimeError(
            f"{slug}: resolved to {len(payloads)} markets; "
            "use fetch_polymarket_series for event inputs."
        )
    payload = payloads[0]

    token_ids = _parse_string_list(payload.get("clobTokenIds"), "clobTokenIds", slug)
    labels_source = payload.get("shortOutcomes") or payload.get("outcomes")
    labels = _parse_string_list(labels_source, "outcomes", slug)

    if len(token_ids) != len(labels):
        raise RuntimeError(
            f"{slug}: Polymarket outcomes/token ids length mismatch "
            f"({len(labels)} labels, {len(token_ids)} token ids)."
        )

    normalized = outcome.strip().casefold()
    if not normalized:
        raise ValueError("Outcome cannot be empty.")

    for idx, label in enumerate(labels):
        if label.casefold() == normalized:
            return label, token_ids[idx]

    aliases = {"yes": 0, "y": 0, "no": 1, "n": 1}
    alias_idx: int | None = aliases.get(normalized)
    if alias_idx is not None and alias_idx < len(token_ids):
        return labels[alias_idx], token_ids[alias_idx]

    available = ", ".join(labels)
    raise ValueError(
        f"{slug}: unknown outcome {outcome!r}. Available outcomes: {available}"
    )


def _fetch_price_history(
    token_id: str,
    *,
    interval: str,
    fidelity: int,
) -> TimeSeries:
    """Fetch a Polymarket token's price history from the public CLOB API."""
    params: dict[str, str | int] = {
        "market": token_id,
        "interval": interval,
        "fidelity": fidelity,
    }

    payload = _get_json(f"{_CLOB_URL}/prices-history", params=params)
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{token_id}: unexpected Polymarket history response: {payload!r}"
        )

    history = payload.get("history")
    if not isinstance(history, list) or not history:
        raise RuntimeError(f"{token_id}: no price history returned.")

    points: TimeSeries = []
    for item in history:
        if not isinstance(item, dict):
            continue
        ts = item.get("t")
        price = item.get("p")
        if ts is None or price is None:
            continue
        points.append(
            (datetime.fromtimestamp(float(ts), tz=timezone.utc), float(price))
        )

    if not points:
        raise RuntimeError(f"{token_id}: no valid Polymarket price points returned.")
    return points


def fetch_polymarket_series(
    markets: list[str],
    period: str,
    *,
    outcome: str = "yes",
    interval: str = "auto",
    fidelity: int = 1,
) -> dict[str, TimeSeries]:
    """Fetch outcome-token price series for one or more Polymarket markets."""
    slugs = list(
        dict.fromkeys(
            normalized
            for normalized in (_normalize_market_ref(m) for m in markets)
            if normalized
        )
    )
    if not slugs:
        raise ValueError(
            "No Polymarket market slugs provided. Pass at least one market slug."
        )

    resolved_interval = (
        polymarket_covering_range(period) if interval == "auto" else interval
    )
    need_trim = resolved_interval != period and period != "max"
    now = datetime.now(timezone.utc) if need_trim else None

    result: dict[str, TimeSeries] = {}
    for slug in slugs:
        for payload in _resolve_market_payloads(slug):
            market_slug = str(payload.get("slug") or slug)
            token_ids = _parse_string_list(
                payload.get("clobTokenIds"), "clobTokenIds", market_slug
            )
            labels_source = payload.get("shortOutcomes") or payload.get("outcomes")
            labels = _parse_string_list(labels_source, "outcomes", market_slug)
            if len(token_ids) != len(labels):
                raise RuntimeError(
                    f"{market_slug}: Polymarket outcomes/token ids length mismatch "
                    f"({len(labels)} labels, {len(token_ids)} token ids)."
                )

            normalized = outcome.strip().casefold()
            if not normalized:
                raise ValueError("Outcome cannot be empty.")

            match_index: int | None = None
            for idx, label in enumerate(labels):
                if label.casefold() == normalized:
                    match_index = idx
                    break
            if match_index is None:
                aliases = {"yes": 0, "y": 0, "no": 1, "n": 1}
                alias_index = aliases.get(normalized)
                if alias_index is not None and alias_index < len(token_ids):
                    match_index = alias_index
            if match_index is None:
                available = ", ".join(labels)
                raise ValueError(
                    f"{market_slug}: unknown outcome {outcome!r}. "
                    f"Available outcomes: {available}"
                )

            label = labels[match_index]
            token_id = token_ids[match_index]
            try:
                series = _fetch_price_history(
                    token_id,
                    interval=resolved_interval,
                    fidelity=fidelity,
                )
            except RuntimeError as exc:
                if "no price history returned" not in str(exc):
                    raise
                continue
            if need_trim:
                series = filter_period(series, period, reference=now)
            if not series:
                continue
            result[f"{_display_market_name(payload)}: {label}"] = series
    if not result:
        raise RuntimeError(
            "No Polymarket price history returned for the requested input."
        )
    return result
