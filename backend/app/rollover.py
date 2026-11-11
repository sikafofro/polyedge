from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

DEFAULT_DB = Path(os.getenv("POLYEDGE_ROLLOVER_DB", "data/rollover.sqlite3"))
_LOCK = RLock()


def _connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialise(db_path: str | Path = DEFAULT_DB, starting_capital: float = 20.0,
               stake_fraction: float = 0.25, target_odds: float = 4.0,
               equity_target: float = 10000.0) -> None:
    if starting_capital <= 0 or not 0 < stake_fraction <= 1 or target_odds <= 1:
        raise ValueError("Invalid rollover configuration")
    with _LOCK, _connect(db_path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS account (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            equity REAL NOT NULL,
            stake_fraction REAL NOT NULL,
            target_odds REAL NOT NULL,
            equity_target REAL NOT NULL,
            status TEXT NOT NULL,
            pilot_ready INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            starting_equity REAL NOT NULL,
            reserve REAL NOT NULL,
            initial_stake REAL NOT NULL,
            current_rollover_stake REAL NOT NULL,
            cumulative_odds REAL NOT NULL DEFAULT 1.0,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            settled_at TEXT
        );
        CREATE TABLE IF NOT EXISTS legs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id INTEGER NOT NULL REFERENCES cycles(id),
            fixture TEXT NOT NULL,
            selection TEXT NOT NULL,
            decimal_odds REAL NOT NULL,
            result TEXT NOT NULL,
            settled_at TEXT NOT NULL
        );
        """)
        row = db.execute("SELECT id FROM account WHERE id=1").fetchone()
        if row is None:
            now = _now()
            db.execute(
                """INSERT INTO account
                (id,equity,stake_fraction,target_odds,equity_target,status,pilot_ready,created_at,updated_at)
                VALUES (1,?,?,?,?, 'paper',0,?,?)""",
                (starting_capital, stake_fraction, target_odds, equity_target, now, now),
            )
            _start_cycle(db, starting_capital, stake_fraction)


def _start_cycle(db: sqlite3.Connection, equity: float, fraction: float) -> int:
    stake = round(equity * fraction, 2)
    reserve = round(equity - stake, 2)
    cursor = db.execute(
        """INSERT INTO cycles
        (starting_equity,reserve,initial_stake,current_rollover_stake,cumulative_odds,status,started_at)
        VALUES (?,?,?,?,1.0,'active',?)""",
        (equity, reserve, stake, stake, _now()),
    )
    return int(cursor.lastrowid)


def get_state(db_path: str | Path = DEFAULT_DB) -> dict[str, Any]:
    initialise(db_path)
    with _LOCK, _connect(db_path) as db:
        account = dict(db.execute("SELECT * FROM account WHERE id=1").fetchone())
        cycle = db.execute(
            "SELECT * FROM cycles WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        latest = db.execute("SELECT * FROM cycles ORDER BY id DESC LIMIT 1").fetchone()
        completed = db.execute("SELECT * FROM cycles WHERE status IN ('won','lost') ORDER BY id DESC LIMIT 1").fetchone()
        current = dict(cycle or latest) if latest else None
        completed_cycle = dict(completed) if completed else None
        legs = []
        if current:
            legs = [dict(row) for row in db.execute(
                "SELECT fixture,selection,decimal_odds,result,settled_at FROM legs WHERE cycle_id=? ORDER BY id",
                (current["id"],),
            )]
        stake = round(account["equity"] * account["stake_fraction"], 2)
        return {
            "equity_usd": round(account["equity"], 2),
            "stake_fraction": account["stake_fraction"],
            "next_cycle_stake_usd": stake,
            "reserve_usd": round(account["equity"] - stake, 2),
            "target_odds": account["target_odds"],
            "equity_target_usd": account["equity_target"],
            "account_status": account["status"],
            "pilot_ready": bool(account["pilot_ready"]),
            "cycle": current,
            "last_completed_cycle": completed_cycle,
            "legs": legs,
            "execution_mode": "paper",
            "orders_placed": 0,
        }


def settle_leg(fixture: str, selection: str, decimal_odds: float, result: str,
               db_path: str | Path = DEFAULT_DB) -> dict[str, Any]:
    if not fixture.strip() or not selection.strip():
        raise ValueError("Fixture and selection are required")
    if result not in {"won", "lost", "void"}:
        raise ValueError("Result must be won, lost, or void")
    if result != "void" and (decimal_odds < 1.01 or decimal_odds > 1000):
        raise ValueError("Decimal odds must be between 1.01 and 1000")
    if result == "void":
        decimal_odds = 1.0

    initialise(db_path)
    with _LOCK, _connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        account = db.execute("SELECT * FROM account WHERE id=1").fetchone()
        if account["status"] != "paper":
            raise ValueError("Paper rollover is paused; no further entries are accepted")
        cycle = db.execute(
            "SELECT * FROM cycles WHERE status='active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if cycle is None:
            raise ValueError("No active rollover cycle")
        db.execute(
            "INSERT INTO legs(cycle_id,fixture,selection,decimal_odds,result,settled_at) VALUES(?,?,?,?,?,?)",
            (cycle["id"], fixture.strip(), selection.strip(), decimal_odds, result, _now()),
        )
        equity = float(account["equity"])
        cumulative = float(cycle["cumulative_odds"])
        current_stake = float(cycle["current_rollover_stake"])
        outcome = "leg_recorded"

        if result == "lost":
            new_equity = max(0.0, round(equity - float(cycle["initial_stake"]), 2))
            db.execute("UPDATE cycles SET status='lost',settled_at=? WHERE id=?",
                       (_now(), cycle["id"]))
            db.execute("UPDATE account SET equity=?,status=?,updated_at=? WHERE id=1",
                       (new_equity, "paused" if new_equity <= 0 else "paper", _now()))
            if new_equity > 0:
                _start_cycle(db, new_equity, float(account["stake_fraction"]))
            outcome = "cycle_lost"
        elif result == "won":
            cumulative *= decimal_odds
            current_stake *= decimal_odds
            if cumulative + 1e-9 >= float(account["target_odds"]):
                # The full final returned stake is cash again; reserve + returned stake = new equity.
                new_equity = round(float(cycle["reserve"]) + current_stake, 2)
                db.execute("UPDATE cycles SET cumulative_odds=?,current_rollover_stake=?,status='won',settled_at=? WHERE id=?",
                           (cumulative, current_stake, _now(), cycle["id"]))
                pilot_ready = 1
                new_status = "paused" if new_equity >= float(account["equity_target"]) else "paper"
                db.execute("UPDATE account SET equity=?,pilot_ready=?,status=?,updated_at=? WHERE id=1",
                           (new_equity, pilot_ready, new_status, _now()))
                if new_status == "paper":
                    _start_cycle(db, new_equity, float(account["stake_fraction"]))
                outcome = "target_hit"
            else:
                db.execute("UPDATE cycles SET cumulative_odds=?,current_rollover_stake=? WHERE id=?",
                           (cumulative, current_stake, cycle["id"]))
        # A void leg returns the current stake unchanged and does not advance cumulative odds.
        db.commit()

    state = get_state(db_path)
    state["last_event"] = outcome
    return state
