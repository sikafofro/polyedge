from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.core import Fixture

BASE_URL = "https://api.football-data.org/v4"
COMPETITIONS = {
    "PL": ("Premier League", "England"),
    "PD": ("La Liga", "Spain"),
    "BL1": ("Bundesliga", "Germany"),
    "DED": ("Eredivisie", "Netherlands"),
    "FL1": ("Ligue 1", "France"),
    "PPL": ("Primeira Liga", "Portugal"),
    "SA": ("Serie A", "Italy"),
}

class FixtureProviderError(RuntimeError):
    pass

def fetch_fixtures(date_from: date, date_to: date) -> list[Fixture]:
    """Fetch upcoming domestic-league fixtures from football-data.org v4."""
    token = os.getenv("FOOTBALL_DATA_API_TOKEN")
    if not token:
        raise FixtureProviderError("FOOTBALL_DATA_API_TOKEN is not configured")
    if date_to < date_from:
        raise ValueError("date_to must be on or after date_from")
    if (date_to - date_from).days > 14:
        raise ValueError("Date range cannot exceed 14 days per scan")

    headers = {"X-Auth-Token": token, "Accept": "application/json"}
    fixtures: list[Fixture] = []
    try:
        with httpx.Client(timeout=25.0, headers=headers) as client:
            for code, (league, country) in COMPETITIONS.items():
                response = client.get(
                    f"{BASE_URL}/competitions/{code}/matches",
                    params={"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat(), "status": "SCHEDULED"},
                )
                if response.status_code == 403:
                    raise FixtureProviderError(
                        f"Provider denied access to {league} ({code}); check your plan and competition coverage"
                    )
                if response.status_code == 429:
                    raise FixtureProviderError("Provider rate limit reached; retry later")
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                for match in payload.get("matches", []):
                    home = match.get("homeTeam") or {}
                    away = match.get("awayTeam") or {}
                    if not home.get("name") or not away.get("name") or not match.get("utcDate"):
                        continue
                    fixtures.append(Fixture(
                        home_team=home["name"],
                        away_team=away["name"],
                        league=league,
                        country=country,
                        competition_type="domestic_league",
                        kickoff=datetime.fromisoformat(
                            match["utcDate"].replace("Z", "+00:00")
                        ),
                    ))
    except httpx.HTTPStatusError as exc:
        raise FixtureProviderError(f"Fixture provider returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise FixtureProviderError(f"Could not reach fixture provider: {exc}") from exc
    return fixtures

def upcoming_range(days: int = 7) -> tuple[date, date]:
    if not 1 <= days <= 14:
        raise ValueError("days must be between 1 and 14")
    today = date.today()
    return today, today + timedelta(days=days)
