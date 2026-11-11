import pytest

from app.market_intelligence import (
    analyse_fixture_markets,
    analyse_match_winner_market,
    build_paper_accumulator,
)

FIXTURE = {
    "kickoff": "2026-11-21T20:00:00+00:00",
    "home_team": "Real Madrid CF",
    "away_team": "RC Celta de Vigo",
    "league": "La Liga",
}

WINNER_MARKET = {
    "id": "market-1",
    "question": "Real Madrid CF vs. RC Celta de Vigo",
    "active": True,
    "closed": False,
    "outcomes": '["Real Madrid", "Draw", "Celta Vigo"]',
    "outcomePrices": '["0.70", "0.18", "0.12"]',
    "clobTokenIds": '["home-token", "draw-token", "away-token"]',
    "liquidityNum": 12500,
    "volumeNum": 45000,
}


def test_extracts_home_draw_away_prices_and_home_odds():
    selected = analyse_match_winner_market(FIXTURE, {"markets": [WINNER_MARKET]})
    assert selected is not None
    assert selected["market_type"] == "match_winner_1x2"
    assert selected["home_win_price"] == 0.70
    assert selected["home_win_decimal_odds"] == pytest.approx(1.4286)
    assert selected["outcomes"]["draw"]["price"] == 0.18
    assert selected["home_token_id"] == "home-token"


def test_rejects_halftime_and_first_goal_markets():
    halftime = {**WINNER_MARKET, "question": "Real Madrid vs Celta Vigo - Halftime Result"}
    first_goal = {**WINNER_MARKET, "question": "Real Madrid vs Celta Vigo - First Team to Score"}
    assert analyse_match_winner_market(FIXTURE, {"markets": [halftime, first_goal]}) is None


def test_rejects_yes_no_market_even_if_question_mentions_home_team():
    yes_no = {
        **WINNER_MARKET,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.70", "0.30"]',
    }
    assert analyse_match_winner_market(FIXTURE, {"markets": [yes_no]}) is None


def test_rejects_incomplete_or_invalid_prices():
    invalid = {**WINNER_MARKET, "outcomePrices": '["1.0", "0", "0.2"]'}
    assert analyse_match_winner_market(FIXTURE, {"markets": [invalid]}) is None


def test_rejects_closed_market():
    closed = {**WINNER_MARKET, "closed": True}
    assert analyse_match_winner_market(FIXTURE, {"markets": [closed]}) is None


def test_selects_highest_liquidity_valid_winner_market():
    lower = {**WINNER_MARKET, "id": "low", "liquidityNum": 10}
    higher = {**WINNER_MARKET, "id": "high", "liquidityNum": 500}
    selected = analyse_match_winner_market(FIXTURE, {"markets": [lower, higher]})
    assert selected["market_id"] == "high"


def test_builds_paper_accumulator_and_uses_strategy_stake():
    analyses = [{
        **FIXTURE,
        "selected_market": analyse_match_winner_market(FIXTURE, {"markets": [WINNER_MARKET]}),
    }]
    result = build_paper_accumulator(analyses, bankroll_usd=20, stake_fraction=0.25)
    assert result["status"] == "proposed_paper_accumulator"
    assert result["leg_count"] == 1
    assert result["stake_usd"] == 5.0
    assert result["combined_decimal_odds"] == pytest.approx(1.4286)
    assert result["orders_placed"] == 0


def test_minimum_odds_prevents_under_target_accumulator():
    analyses = [{
        **FIXTURE,
        "selected_market": analyse_match_winner_market(FIXTURE, {"markets": [WINNER_MARKET]}),
    }]
    result = build_paper_accumulator(
        analyses, bankroll_usd=20, stake_fraction=0.25, minimum_odds=2.0
    )
    assert result["status"] == "not_proposed"
    assert result["legs"] == []
    assert result["stake_usd"] == 0


def test_analyse_fixture_markets_reports_unmatched_fixture_safely():
    result = analyse_fixture_markets(
        [{**FIXTURE, "polymarket_events": [{"markets": []}]}],
        {"starting_bankroll_usd": 20, "stake_fraction": 0.25, "minimum_odds": None},
    )
    assert result["validated_match_winner_markets"] == 0
    assert result["paper_accumulator"]["status"] == "not_proposed"
    assert result["orders_placed"] == 0
