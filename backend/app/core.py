from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
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


def parse_fixture_csv(csv_text: str) -> list[Fixture]:
    """Parse CSV rows with ISO-8601 timezone-aware kickoff values."""
    required = {"kickoff", "country", "league", "competition_type", "home_team", "away_team"}
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("CSV must include a header row")
    missing = required - set(reader.fieldnames)
    if missing:
        raise ValueError("CSV is missing columns: " + ", ".join(sorted(missing)))

    fixtures: list[Fixture] = []
    for line_number, row in enumerate(reader, start=2):
        try:
            kickoff = datetime.fromisoformat(row["kickoff"].strip().replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                raise ValueError("kickoff must include a timezone offset")
            values = [row[key].strip() for key in required]
            if any(not value for value in values):
                raise ValueError("fixture fields cannot be blank")
            fixtures.append(Fixture(
                home_team=row["home_team"].strip(),
                away_team=row["away_team"].strip(),
                league=row["league"].strip(),
                country=row["country"].strip(),
                competition_type=row["competition_type"].strip(),
                kickoff=kickoff,
            ))
        except (AttributeError, KeyError, ValueError) as exc:
            raise ValueError(f"Invalid CSV row {line_number}: {exc}") from exc
    return fixtures


def group_fixtures(fixtures: list[Fixture], window_minutes: int = 120) -> list[list[Fixture]]:
    """Group fixtures into rolling windows anchored at each group's first kickoff."""
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
