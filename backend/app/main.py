from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.core import group_fixtures, parse_fixture_csv, qualify_fixture

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "config" / "team_rules.json"

app = FastAPI(title="POLYEDGE API", version="0.2.0")


class FixtureCsvRequest(BaseModel):
    csv_text: str = Field(min_length=1)


def load_rules() -> dict[str, Any]:
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Team rules configuration is missing") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Team rules configuration is invalid JSON") from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "polyedge-api"}


@app.get("/api/v1/config")
def get_config() -> dict[str, Any]:
    return load_rules()


@app.get("/api/v1/strategy")
def get_strategy() -> dict[str, Any]:
    return {
        "starting_bankroll_usd": 100.0,
        "stake_fraction": 0.25,
        "fixture_grouping_window_minutes": 120,
        "max_active_accumulators": 1,
        "settlement_required_before_next_entry": True,
        "execution_mode": "paper",
        "minimum_odds": None,
        "minimum_confidence": None,
    }


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

    eligible_fixtures = [
        fixture for fixture in fixtures if qualify_fixture(fixture, rules)[0]
    ]
    grouped = group_fixtures(
        eligible_fixtures,
        window_minutes=120,
    )
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
