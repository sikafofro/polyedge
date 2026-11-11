from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "config" / "team_rules.json"

app = FastAPI(title="POLYEDGE API", version="0.1.0")


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
