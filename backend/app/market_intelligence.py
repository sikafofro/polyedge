from __future__ import annotations

import json
import math
import re
from typing import Any

from app.core import accumulator_stake


EXCLUDED_MARKET_TERMS = (
    "halftime", "half-time", "first half", "first team to score",
    "exact score", "correct score", "total goals", "over/under",
    "both teams to score", "corner", "cards", "player", "penalty",
)


def _normalise(value: str) -> str:
    value = value.casefold().replace("&", "and")
    for source, target in (("ü", "u"), ("ö", "o"), ("é", "e"), ("ñ", "n"), ("á", "a")):
        value = value.replace(source, target)
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    for prefix in ("fc ", "afc ", "sc "):
        if value.startswith(prefix):
            value = value[len(prefix):]
    for suffix in (" fc", " cf", " sc", " afc"):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
    return " ".join(value.split())


def _team_matches(outcome: str, team: str) -> bool:
    left, right = _normalise(outcome), _normalise(team)
    aliases = {
        "bayern munchen": {"bayern munich"},
        "bayern munich": {"bayern munchen"},
        "rc celta de vigo": {"celta de vigo", "celta vigo"},
        "celta de vigo": {"rc celta de vigo", "celta vigo"},
        "1 fc koln": {"koln", "cologne", "fc koln"},
        "koln": {"1 fc koln", "cologne"},
        "paris saint germain": {"psg"},
        "psg": {"paris saint germain"},
        "inter milan": {"internazionale"},
        "internazionale": {"inter milan"},
    }
    return left == right or left in aliases.get(right, set()) or right in aliases.get(left, set())


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def analyse_match_winner_market(
    fixture: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a validated 1X2 match-winner market; reject props and side markets."""
    home = str(fixture.get("home_team") or "")
    away = str(fixture.get("away_team") or "")
    candidates: list[dict[str, Any]] = []

    for market in event.get("markets") or []:
        question = str(market.get("question") or "")
        lowered = question.casefold()
        if any(term in lowered for term in EXCLUDED_MARKET_TERMS):
            continue
        if market.get("active") is False or market.get("closed") is True:
            continue

        outcomes = [str(item) for item in _as_list(market.get("outcomes"))]
        prices = _as_list(market.get("outcomePrices"))
        token_ids = _as_list(market.get("clobTokenIds"))
        if len(outcomes) != 3 or len(prices) != 3:
            continue

        home_indexes = [i for i, item in enumerate(outcomes) if _team_matches(item, home)]
        away_indexes = [i for i, item in enumerate(outcomes) if _team_matches(item, away)]
        draw_indexes = [i for i, item in enumerate(outcomes) if _normalise(item) in {"draw", "tie"}]
        if len(home_indexes) != 1 or len(away_indexes) != 1 or len(draw_indexes) != 1:
            continue
        indexes = [home_indexes[0], draw_indexes[0], away_indexes[0]]
        probabilities = [_number(prices[i]) for i in indexes]
        if any(price is None or not 0 < price < 1 for price in probabilities):
            continue

        home_price, draw_price, away_price = probabilities
        liquidity = _number(market.get("liquidityNum", market.get("liquidity")))
        volume = _number(market.get("volumeNum", market.get("volume")))
        candidate = {
            "market_id": market.get("id"),
            "condition_id": market.get("conditionId"),
            "question": question,
            "market_type": "match_winner_1x2",
            "outcomes": {
                "home": {"name": outcomes[home_indexes[0]], "price": home_price,
                         "decimal_odds": round(1 / home_price, 4)},
                "draw": {"name": outcomes[draw_indexes[0]], "price": draw_price,
                         "decimal_odds": round(1 / draw_price, 4)},
                "away": {"name": outcomes[away_indexes[0]], "price": away_price,
                         "decimal_odds": round(1 / away_price, 4)},
            },
            "home_win_price": home_price,
            "home_win_decimal_odds": round(1 / home_price, 4),
            "liquidity_usd": liquidity,
            "volume_usd": volume,
            "home_token_id": token_ids[home_indexes[0]] if len(token_ids) == 3 else None,
            "data_quality": "validated_three_outcome_market",
        }
        candidates.append(candidate)

    if not candidates:
        return None
    # Prefer the most liquid valid 1X2 market; missing liquidity ranks last.
    candidates.sort(key=lambda item: item["liquidity_usd"] if item["liquidity_usd"] is not None else -1,
                    reverse=True)
    return candidates[0]


def build_paper_accumulator(
    fixture_analyses: list[dict[str, Any]],
    bankroll_usd: float,
    stake_fraction: float,
    minimum_odds: float | None = None,
) -> dict[str, Any]:
    """Build a paper-only home-win accumulator from validated markets."""
    legs = []
    for item in fixture_analyses:
        market = item.get("selected_market")
        if not market:
            continue
        legs.append({
            "fixture": f'{item["home_team"]} vs {item["away_team"]}',
            "kickoff": item["kickoff"],
            "selection": f'{item["home_team"]} to win',
            "market_question": market["question"],
            "yes_price": market["home_win_price"],
            "decimal_odds": market["home_win_decimal_odds"],
            "condition_id": market.get("condition_id"),
        })

    combined_odds = math.prod(leg["decimal_odds"] for leg in legs) if legs else None
    qualifies = bool(legs) and (minimum_odds is None or combined_odds >= minimum_odds)
    stake = accumulator_stake(bankroll_usd, stake_fraction) if qualifies else 0.0
    return {
        "status": "proposed_paper_accumulator" if qualifies else "not_proposed",
        "execution_mode": "paper",
        "legs": legs if qualifies else [],
        "leg_count": len(legs) if qualifies else 0,
        "combined_decimal_odds": round(combined_odds, 4) if qualifies else None,
        "stake_usd": stake,
        "potential_return_usd": round(stake * combined_odds, 2) if qualifies else None,
        "potential_profit_usd": round(stake * (combined_odds - 1), 2) if qualifies else None,
        "minimum_odds": minimum_odds,
        "reason": (
            "All included legs have a validated three-outcome match-winner market."
            if qualifies else
            "No qualifying match-winner legs met the configured accumulator requirements."
        ),
        "orders_placed": 0,
    }


def analyse_fixture_markets(
    matched_fixtures: list[dict[str, Any]],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    analyses = []
    for fixture in matched_fixtures:
        selected = None
        matched_events = fixture.get("polymarket_events") or []
        for event in matched_events:
            selected = analyse_match_winner_market(fixture, event)
            if selected:
                break
        analyses.append({
            "kickoff": fixture.get("kickoff"),
            "league": fixture.get("league"),
            "home_team": fixture.get("home_team"),
            "away_team": fixture.get("away_team"),
            "market_status": "validated" if selected else "no_valid_match_winner_market",
            "selected_market": selected,
        })

    accumulator = build_paper_accumulator(
        analyses,
        bankroll_usd=float(strategy["starting_bankroll_usd"]),
        stake_fraction=float(strategy["stake_fraction"]),
        minimum_odds=strategy.get("minimum_odds"),
    )
    return {
        "provider": "Polymarket Gamma public market data",
        "fixtures_analysed": len(analyses),
        "validated_match_winner_markets": sum(bool(item["selected_market"]) for item in analyses),
        "rejected_or_missing_markets": sum(not bool(item["selected_market"]) for item in analyses),
        "fixtures": analyses,
        "paper_accumulator": accumulator,
        "execution_mode": "paper",
        "orders_placed": 0,
    }
