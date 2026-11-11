from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class Fixture:
    home_team: str
    away_team: str
    league: str
    country: str
    competition_type: str
    kickoff: datetime


def _norm(value: str) -> str:
    return " ".join(value.casefold().replace("&", "and").split())


def qualify_fixture(fixture: Fixture, rules: dict[str, Any]) -> tuple[bool, str]:
    """Return eligibility and an explainable reason for a selected team's home fixture."""
    if fixture.competition_type.casefold() != "domestic_league":
        return False, "not a domestic league fixture"

    for selection in rules.get("selected_teams", []):
        same_league = _norm(selection["league"]) == _norm(fixture.league)
        same_country = _norm(selection["country"]) == _norm(fixture.country)
        selected_is_home = _norm(selection["team"]) == _norm(fixture.home_team)
        if not (same_league and same_country and selected_is_home):
            continue

        excluded = {_norm(team) for team in selection.get("excluded_opponents", [])}
        if _norm(fixture.away_team) in excluded:
            return False, f"excluded opponent: {fixture.away_team}"
        return True, "qualifies"

    return False, "no configured selected team is playing at home in its domestic league"


def group_fixtures(fixtures: list[Fixture], window_minutes: int = 120) -> list[list[Fixture]]:
    """Group sorted eligible fixtures into rolling windows anchored at each group's first kickoff."""
    if window_minutes <= 0:
        raise ValueError("window_minutes must be positive")

    ordered = sorted(fixtures, key=lambda item: item.kickoff)
    groups: list[list[Fixture]] = []
    current: list[Fixture] = []
    anchor: datetime | None = None
    window = timedelta(minutes=window_minutes)

    for fixture in ordered:
        kickoff = fixture.kickoff
        if kickoff.tzinfo is None:
            raise ValueError("fixture kickoff must be timezone-aware")
        if not current or anchor is None or kickoff - anchor <= window:
            if not current:
                anchor = kickoff
            current.append(fixture)
        else:
            groups.append(current)
            current = [fixture]
            anchor = kickoff

    if current:
        groups.append(current)
    return groups


def accumulator_stake(bankroll: float, fraction: float = 0.25) -> float:
    """Calculate one accumulator's allocation from settled, available bankroll."""
    if bankroll < 0:
        raise ValueError("bankroll cannot be negative")
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be greater than 0 and at most 1")
    return round(bankroll * fraction, 2)
