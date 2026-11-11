from app.polymarket_data import match_fixtures_to_events


def test_matches_only_when_both_fixture_teams_are_in_event_title():
    fixtures = [
        {"home_team": "Arsenal", "away_team": "Everton", "league": "Premier League"},
        {"home_team": "Barcelona", "away_team": "Real Madrid", "league": "La Liga"},
    ]
    events = [
        {
            "id": "event-1",
            "title": "Arsenal vs Everton",
            "slug": "arsenal-everton",
            "markets": [{"question": "Will Arsenal win?", "liquidityNum": 1200}],
        }
    ]

    result = match_fixtures_to_events(fixtures, events)

    assert result[0]["market_match_status"] == "matched"
    assert result[0]["polymarket_events"][0]["event_id"] == "event-1"
    assert result[0]["polymarket_events"][0]["markets"][0]["liquidity"] == 1200
    assert result[1]["market_match_status"] == "unmatched"
    assert result[1]["polymarket_events"] == []


def test_match_is_not_created_from_only_one_team_name():
    fixtures = [{"home_team": "Arsenal", "away_team": "Everton"}]
    events = [{"id": "event-2", "title": "Arsenal to win the league", "markets": []}]

    result = match_fixtures_to_events(fixtures, events)

    assert result[0]["market_match_status"] == "unmatched"
