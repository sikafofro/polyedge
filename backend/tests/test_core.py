from datetime import datetime, timezone

import pytest

from app.core import (
    Fixture,
    accumulator_stake,
    group_fixtures,
    parse_fixture_csv,
    qualify_fixture,
)
from app.main import get_strategy

RULES = {
    "selected_teams": [
        {
            "league": "Premier League",
            "country": "England",
            "team": "Arsenal",
            "excluded_opponents": ["Liverpool", "Manchester City"],
        }
    ]
}


def fixture(home="Arsenal", away="Everton", league="Premier League",
            country="England", competition="domestic_league", hour=12):
    return Fixture(
        home_team=home,
        away_team=away,
        league=league,
        country=country,
        competition_type=competition,
        kickoff=datetime(2026, 11, 11, hour, 0, tzinfo=timezone.utc),
    )


def test_qualifies_selected_home_team_in_domestic_league():
    assert qualify_fixture(fixture(), RULES) == (True, "qualifies")


def test_skips_excluded_opponent():
    eligible, reason = qualify_fixture(fixture(away="Liverpool"), RULES)
    assert not eligible
    assert "excluded opponent" in reason


def test_skips_away_fixture():
    eligible, _ = qualify_fixture(fixture(home="Everton", away="Arsenal"), RULES)
    assert not eligible


def test_skips_cup_fixture():
    eligible, _ = qualify_fixture(fixture(competition="domestic_cup"), RULES)
    assert not eligible


def test_groups_fixtures_within_two_hours():
    first = fixture(hour=10)
    second = fixture(home="Barcelona", league="La Liga", country="Spain", hour=12)
    third = fixture(home="Bayern Munich", league="Bundesliga", country="Germany", hour=13)
    groups = group_fixtures([third, first, second], 120)
    assert [len(group) for group in groups] == [2, 1]


def test_stake_is_25_percent_of_current_bankroll():
    assert accumulator_stake(50) == 5.0
    assert accumulator_stake(100) == 25
    assert accumulator_stake(80) == 20


def test_strategy_endpoint_uses_twenty_dollar_bankroll():
    strategy = get_strategy()
    assert strategy["starting_bankroll_usd"] == 20.0
    assert strategy["stake_fraction"] == 0.25
    assert accumulator_stake(
        strategy["starting_bankroll_usd"], strategy["stake_fraction"]
    ) == 12.5


def test_invalid_stake_fraction_rejected():
    with pytest.raises(ValueError):
        accumulator_stake(100, 1.2)


def test_parse_fixture_csv_reads_timezone_aware_rows():
    source = (
        "kickoff,country,league,competition_type,home_team,away_team\n"
        "2026-11-14T09:00:00+00:00,England,Premier League,"
        "domestic_league,Arsenal,Everton\n"
    )
    parsed = parse_fixture_csv(source)
    assert len(parsed) == 1
    assert parsed[0].home_team == "Arsenal"
    assert parsed[0].kickoff.tzinfo is not None


def test_parse_fixture_csv_rejects_missing_timezone():
    source = (
        "kickoff,country,league,competition_type,home_team,away_team\n"
        "2026-11-14T09:00:00,England,Premier League,"
        "domestic_league,Arsenal,Everton\n"
    )
    with pytest.raises(ValueError, match="timezone"):
        parse_fixture_csv(source)


def test_parse_fixture_csv_rejects_missing_columns():
    with pytest.raises(ValueError, match="missing columns"):
        parse_fixture_csv("kickoff,home_team\n2026-11-14T09:00:00+00:00,Arsenal\n")
