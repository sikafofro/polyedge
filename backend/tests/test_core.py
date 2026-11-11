from datetime import datetime, timedelta, timezone

from app.core import Fixture, accumulator_stake, group_fixtures, qualify_fixture

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
    assert accumulator_stake(100) == 25
    assert accumulator_stake(80) == 20


def test_invalid_stake_fraction_rejected():
    try:
        accumulator_stake(100, 1.2)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid fraction to raise ValueError")
