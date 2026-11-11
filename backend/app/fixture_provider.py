from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
UPCOMING_STATUSES = {"SCHEDULED", "TIMED"}


class FixtureProviderError(RuntimeError):
    pass


@dataclass
class FixtureScan:
    fixtures: list[Fixture]
    leagues: list[dict[str, Any]]


def fetch_fixtures_with_diagnostics(date_from: date, date_to: date) -> FixtureScan:
    """Fetch upcoming fixtures and return per-league status diagnostics."""
    token = os.getenv("FOOTBALL_DATA_API_TOKEN")
    if not token:
        raise FixtureProviderError("FOOTBALL_DATA_API_TOKEN is not configured")
    if date_to < date_from:
        raise ValueError("date_to must be on or after date_from")
    if (date_to - date_from).days > 14:
        raise ValueError("Date range cannot exceed 14 days per scan")

    headers = {"X-Auth-Token": token, "Accept": "application/json"}
    fixtures: list[Fixture] = []
    diagnostics: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=25.0, headers=headers) as client:
            for code, (league, country) in COMPETITIONS.items():
                diagnostic: dict[str, Any] = {
                    "code": code,
                    "league": league,
                    "country": country,
                    "api_matches": 0,
                    "scheduled": 0,
                    "timed": 0,
                    "accepted_upcoming": 0,
                    "ignored_other_statuses": 0,
                    "status_counts": {},
                    "error": None,
                }
                try:
                    response = client.get(
                        f"{BASE_URL}/competitions/{code}/matches",
                        params={
                            "dateFrom": date_from.isoformat(),
                            "dateTo": date_to.isoformat(),
                        },
                    )
                    if response.status_code == 429:
                        raise FixtureProviderError(
                            "Provider rate limit reached; retry later"
                        )
                    if response.status_code == 403:
                        diagnostic["error"] = (
                            "Access denied; verify account plan and competition coverage"
                        )
                        diagnostics.append(diagnostic)
                        continue
                    response.raise_for_status()
                    payload: dict[str, Any] = response.json()
                    matches = payload.get("matches", [])
                    diagnostic["api_matches"] = len(matches)
                    statuses = Counter(
                        str(match.get("status", "UNKNOWN")).upper()
                        for match in matches
                    )
                    diagnostic["status_counts"] = dict(sorted(statuses.items()))
                    diagnostic["scheduled"] = statuses.get("SCHEDULED", 0)
                    diagnostic["timed"] = statuses.get("TIMED", 0)
                    for match in matches:
                        status = str(match.get("status", "UNKNOWN")).upper()
                        if status not in UPCOMING_STATUSES:
                            diagnostic["ignored_other_statuses"] += 1
                            continue
                        home = match.get("homeTeam") or {}
                        away = match.get("awayTeam") or {}
                        utc_date = match.get("utcDate")
                        if not home.get("name") or not away.get("name") or not utc_date:
                            diagnostic["ignored_other_statuses"] += 1
                            continue
                        fixtures.append(Fixture(
                            home_team=home["name"],
                            away_team=away["name"],
                            league=league,
                            country=country,
                            competition_type="domestic_league",
                            kickoff=datetime.fromisoformat(
                                utc_date.replace("Z", "+00:00")
                            ),
                        ))
                        diagnostic["accepted_upcoming"] += 1
                except httpx.HTTPStatusError as exc:
                    diagnostic["error"] = (
                        f"Provider returned HTTP {exc.response.status_code}"
                    )
                diagnostics.append(diagnostic)
    except FixtureProviderError:
        raise
    except httpx.HTTPError as exc:
        raise FixtureProviderError(
            f"Could not reach fixture provider: {exc}"
        ) from exc
    return FixtureScan(fixtures=fixtures, leagues=diagnostics)


def fetch_fixtures(date_from: date, date_to: date) -> list[Fixture]:
    """Backward-compatible fixture-only helper."""
    return fetch_fixtures_with_diagnostics(date_from, date_to).fixtures


def upcoming_range(days: int = 7) -> tuple[date, date]:
    if not 1 <= days <= 14:
        raise ValueError("days must be between 1 and 14")
    today = datetime.now(timezone.utc).date()
    return today, today + timedelta(days=days)
