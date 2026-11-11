from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core import group_fixtures, parse_fixture_csv, qualify_fixture
from app.fixture_provider import FixtureProviderError, fetch_fixtures, upcoming_range
from app.polymarket_data import PolymarketDataError, search_football_events, match_fixtures_to_events
from app.market_intelligence import analyse_fixture_markets
from app.rollover import get_state, settle_leg

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "config" / "team_rules.json"
STRATEGY_PATH = ROOT / "config" / "strategy.json"

app = FastAPI(title="POLYEDGE API", version="0.3.0")


class FixtureCsvRequest(BaseModel):
    csv_text: str = Field(min_length=1)


class RolloverSettlementRequest(BaseModel):
    fixture: str = Field(min_length=1, max_length=200)
    selection: str = Field(min_length=1, max_length=200)
    decimal_odds: float = Field(gt=0, le=1000)
    result: str


def load_rules() -> dict[str, Any]:
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Team rules configuration is missing") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Team rules configuration is invalid JSON") from exc


def load_strategy() -> dict[str, Any]:
    try:
        return json.loads(STRATEGY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Strategy configuration is missing") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Strategy configuration is invalid JSON") from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "polyedge-api"}


@app.get("/api/v1/config")
def get_config() -> dict[str, Any]:
    return load_rules()


@app.get("/api/v1/strategy")
def get_strategy() -> dict[str, Any]:
    return load_strategy()


@app.get("/api/v1/fixtures/sample-csv")
def get_sample_fixture_csv() -> dict[str, str]:
    sample_path = ROOT / "data" / "sample_fixtures.csv"
    try:
        return {"csv_text": sample_path.read_text(encoding="utf-8")}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Sample fixture CSV is missing") from exc


@app.post("/api/v1/fixtures/scan")
def scan_fixture_csv(payload: FixtureCsvRequest) -> dict[str, Any]:
    """Scan a supplied CSV against configured club, competition and exclusion rules."""
    try:
        fixtures = parse_fixture_csv(payload.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rules = load_rules()
    eligible = []
    skipped = []
    for fixture in fixtures:
        qualifies, reason = qualify_fixture(fixture, rules)
        record = {
            "kickoff": fixture.kickoff.isoformat(),
            "country": fixture.country,
            "league": fixture.league,
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "competition_type": fixture.competition_type,
            "reason": reason,
        }
        (eligible if qualifies else skipped).append(record)

    eligible_fixtures = [fixture for fixture in fixtures if qualify_fixture(fixture, rules)[0]]
    grouped = group_fixtures(eligible_fixtures, window_minutes=120)
    groups = [
        {
            "group_number": index,
            "fixtures": [
                {
                    "kickoff": fixture.kickoff.isoformat(),
                    "home_team": fixture.home_team,
                    "away_team": fixture.away_team,
                    "league": fixture.league,
                    "country": fixture.country,
                }
                for fixture in group
            ],
        }
        for index, group in enumerate(grouped, start=1)
    ]
    return {
        "mode": "csv_test_scan",
        "execution_mode": "paper",
        "total_fixtures": len(fixtures),
        "qualifying_fixtures": len(eligible),
        "skipped_fixtures": len(skipped),
        "eligible": eligible,
        "skipped": skipped,
        "accumulator_groups": groups,
        "note": "CSV input is test data only. No market orders are placed.",
    }


@app.post("/api/v1/fixtures/upload")
async def upload_fixture_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    """Accept a real CSV file upload and run it through the same scanner."""
    if file.filename and not file.filename.casefold().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Please upload a .csv file")
    try:
        csv_text = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded") from exc
    if not csv_text.strip():
        raise HTTPException(status_code=422, detail="Uploaded CSV is empty")
    return scan_fixture_csv(FixtureCsvRequest(csv_text=csv_text))


@app.get("/api/v1/fixtures/live")
def scan_live_fixtures(days: int = 7) -> dict[str, Any]:
    """Fetch live upcoming league fixtures and apply the configured selection rules."""
    if not 1 <= days <= 14:
        raise HTTPException(status_code=422, detail="days must be between 1 and 14")
    from datetime import date, timedelta
    date_from = date.today()
    date_to = date_from + timedelta(days=days)
    try:
        fixtures = fetch_fixtures(date_from, date_to)
    except FixtureProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    rules = load_rules()
    eligible = []
    skipped = []
    qualifying_fixtures = []
    for fixture in fixtures:
        qualifies, reason = qualify_fixture(fixture, rules)
        record = {
            "kickoff": fixture.kickoff.isoformat(),
            "country": fixture.country,
            "league": fixture.league,
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "reason": reason,
        }
        (eligible if qualifies else skipped).append(record)
        if qualifies:
            qualifying_fixtures.append(fixture)
    groups = group_fixtures(qualifying_fixtures, window_minutes=120)
    return {
        "mode": "live_fixture_scan",
        "provider": "football-data.org",
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "total_fixtures": len(fixtures),
        "qualifying_fixtures": len(eligible),
        "skipped_fixtures": len(skipped),
        "eligible": eligible,
        "skipped": skipped,
        "accumulator_groups": [
            {"group_number": i, "fixtures": [
                {"kickoff": f.kickoff.isoformat(), "home_team": f.home_team,
                 "away_team": f.away_team, "league": f.league, "country": f.country}
                for f in group
            ]} for i, group in enumerate(groups, start=1)
        ],
        "execution_mode": "paper",
        "note": "Live fixture data only; no bets or market orders are placed.",
    }


@app.get("/api/v1/polymarket/football-markets")
def get_polymarket_football_markets(days: int = 14, limit: int = 5) -> dict[str, Any]:
    """Search public Polymarket events separately for each qualifying fixture."""
    if not 1 <= days <= 14:
        raise HTTPException(status_code=422, detail="days must be between 1 and 14")
    if not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
    from datetime import date, timedelta
    date_from = date.today()
    date_to = date_from + timedelta(days=days)
    try:
        fixtures = fetch_fixtures(date_from, date_to)
    except FixtureProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    rules = load_rules()
    qualifying = []
    for fixture in fixtures:
        qualifies, _ = qualify_fixture(fixture, rules)
        if qualifies:
            qualifying.append({
                "kickoff": fixture.kickoff.isoformat(),
                "country": fixture.country,
                "league": fixture.league,
                "home_team": fixture.home_team,
                "away_team": fixture.away_team,
            })

    events_by_id: dict[str, dict[str, Any]] = {}
    try:
        for fixture in qualifying:
            query = f'{fixture["home_team"]} {fixture["away_team"]}'
            for event in search_football_events(query, limit_per_type=limit):
                key = str(event.get("id") or event.get("slug") or event.get("title"))
                events_by_id[key] = event
    except PolymarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    events = list(events_by_id.values())
    matched = match_fixtures_to_events(qualifying, events)
    market_intelligence = analyse_fixture_markets(matched, load_strategy())
    return {
        "provider": "Polymarket Gamma public-search",
        "authentication": "none_public_market_data",
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "fixtures_checked": len(qualifying),
        "events_scanned": len(events),
        "matched_fixtures": sum(item["market_match_status"] == "matched" for item in matched),
        "unmatched_fixtures": sum(item["market_match_status"] == "unmatched" for item in matched),
        "matches": matched,
        "market_intelligence": market_intelligence,
        "execution_mode": "paper",
        "orders_placed": 0,
    }



@app.get("/api/v1/rollover")
def get_rollover_state() -> dict[str, Any]:
    """Return the persistent paper rollover account and active cycle."""
    try:
        return get_state()
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/rollover/settle")
def settle_rollover_leg(payload: RolloverSettlementRequest) -> dict[str, Any]:
    """Record one settled sequential rollover leg; this endpoint never places orders."""
    try:
        return settle_leg(
            fixture=payload.fixture,
            selection=payload.selection,
            decimal_odds=payload.decimal_odds,
            result=payload.result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
