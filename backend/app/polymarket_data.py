from __future__ import annotations

import re
from datetime import date, timedelta, timezone, datetime
from typing import Any

import httpx

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"


class PolymarketDataError(RuntimeError):
    """Raised when the public Polymarket market-data API cannot be read."""


def _normalise(value: str) -> str:
    value = value.casefold().replace("&", "and")
    for source, target in (("ü", "u"), ("ö", "o"), ("é", "e"), ("ñ", "n"), ("á", "a")):
        value = value.replace(source, target)
    words = re.sub(r"[^a-z0-9]+", " ", value).strip()
    for suffix in (" fc", " cf", " sc", " afc"):
        if words.endswith(suffix):
            words = words[:-len(suffix)]
    for prefix in ("fc ", "afc ", "sc "):
        if words.startswith(prefix):
            words = words[len(prefix):]
    return words


def _contains_team(title: str, team: str) -> bool:
    title_norm = f" {_normalise(title)} "
    aliases = {
        "manchester united": ("man united",),
        "manchester city": ("man city",),
        "paris saint germain": ("psg",),
        "tottenham hotspur": ("tottenham",),
        "inter milan": ("internazionale", "inter"),
        "bayern munchen": ("bayern munich",),
        "bayern munich": ("bayern munchen",),
        "rc celta de vigo": ("celta de vigo", "celta vigo"),
        "1 fc koln": ("koln", "cologne", "fc koln"),
    }
    team_norm = _normalise(team)
    candidates = (team_norm, *aliases.get(team_norm, ()))
    return any(f" {candidate} " in title_norm for candidate in candidates)


def fetch_football_events(
    limit: int = 100,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Read active soccer events in a date window from Gamma; no wallet auth."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    start = date_from or datetime.now(timezone.utc).date()
    end = date_to or (start + timedelta(days=14))
    if end < start:
        raise ValueError("date_to must be on or after date_from")
    try:
        response = httpx.get(
            f"{GAMMA_BASE_URL}/events",
            params={
                "active": "true",
                "closed": "false",
                "tag_slug": "soccer",
                "start_date_min": start.isoformat(),
                "start_date_max": end.isoformat(),
                "order": "startDate",
                "ascending": "true",
                "limit": limit,
                "offset": 0,
            },
            headers={"Accept": "application/json"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PolymarketDataError(f"Could not retrieve Polymarket events: {exc}") from exc
    if not isinstance(payload, list):
        raise PolymarketDataError("Unexpected Gamma API response: expected an event list")
    return payload


def search_football_events(query: str, limit_per_type: int = 5) -> list[dict[str, Any]]:
    """Search public active Polymarket events by fixture team names."""
    if not query.strip():
        raise ValueError("query cannot be blank")
    if not 1 <= limit_per_type <= 20:
        raise ValueError("limit_per_type must be between 1 and 20")
    try:
        response = httpx.get(
            f"{GAMMA_BASE_URL}/public-search",
            params={
                "q": query,
                "events_status": "active",
                "limit_per_type": limit_per_type,
                "search_tags": "true",
            },
            headers={"Accept": "application/json"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PolymarketDataError(f"Could not search Polymarket events: {exc}") from exc
    if not isinstance(payload, dict):
        raise PolymarketDataError("Unexpected public-search response: expected an object")
    events = payload.get("events") or []
    if not isinstance(events, list):
        raise PolymarketDataError("Unexpected public-search response: events must be a list")
    return events


def match_fixtures_to_events(
    fixtures: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Match only when both fixture team names occur in the event title."""
    results: list[dict[str, Any]] = []
    for fixture in fixtures:
        home = str(fixture.get("home_team", ""))
        away = str(fixture.get("away_team", ""))
        matches = []
        for event in events:
            title = str(event.get("title") or event.get("slug") or "")
            if title and _contains_team(title, home) and _contains_team(title, away):
                matches.append({
                    "event_id": event.get("id"),
                    "event_title": title,
                    "event_slug": event.get("slug"),
                    "event_url": (
                        f"https://polymarket.com/event/{event['slug']}"
                        if event.get("slug") else None
                    ),
                    "markets": [
                        {
                            "question": market.get("question"),
                            "condition_id": market.get("conditionId"),
                            "active": market.get("active"),
                            "closed": market.get("closed"),
                            "liquidity": market.get("liquidityNum"),
                            "volume": market.get("volumeNum"),
                            "outcomes": market.get("outcomes"),
                            "outcome_prices": market.get("outcomePrices"),
                            "clob_token_ids": market.get("clobTokenIds"),
                        }
                        for market in (event.get("markets") or [])
                    ],
                })
        results.append({
            **fixture,
            "market_match_status": "matched" if matches else "unmatched",
            "polymarket_events": matches,
        })
    return results
