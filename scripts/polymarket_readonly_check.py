from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import qualify_fixture
from app.fixture_provider import fetch_fixtures_with_diagnostics, upcoming_range
from app.polymarket_data import fetch_football_events, match_fixtures_to_events


def main() -> int:
    events = fetch_football_events(limit=100)
    markets = [
        market
        for event in events
        for market in (event.get("markets") or [])
    ]
    summary = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "polymarket_provider": "Polymarket Gamma API",
        "polymarket_events_received": len(events),
        "polymarket_markets_received": len(markets),
        "execution_mode": "read_only",
        "orders_placed": 0,
    }

    if not os.getenv("FOOTBALL_DATA_API_TOKEN"):
        summary["fixture_matching_status"] = "skipped_missing_FOOTBALL_DATA_API_TOKEN"
        summary["next_action"] = (
            "Add FOOTBALL_DATA_API_TOKEN as a GitHub Actions repository secret "
            "to enable live fixture-to-market matching."
        )
    else:
        start, end = upcoming_range(days=14)
        fixture_scan = fetch_fixtures_with_diagnostics(start, end)
        rules = json.loads(
            (ROOT / "config" / "team_rules.json").read_text(encoding="utf-8")
        )
        qualifying = []
        for fixture in fixture_scan.fixtures:
            eligible, _ = qualify_fixture(fixture, rules)
            if eligible:
                qualifying.append({
                    "kickoff": fixture.kickoff.isoformat(),
                    "country": fixture.country,
                    "league": fixture.league,
                    "home_team": fixture.home_team,
                    "away_team": fixture.away_team,
                })

        matches = match_fixtures_to_events(qualifying, events)
        matched = [item for item in matches if item["market_match_status"] == "matched"]
        summary.update({
            "fixture_matching_status": "completed",
            "fixture_provider": "football-data.org",
            "fixtures_received": len(fixture_scan.fixtures),
            "qualifying_fixtures": len(qualifying),
            "matched_fixtures": len(matched),
            "unmatched_fixtures": len(matches) - len(matched),
            "sample_matches": [
                {
                    "fixture": f'{item["home_team"]} vs {item["away_team"]}',
                    "kickoff": item["kickoff"],
                    "event_titles": [
                        event["event_title"] for event in item["polymarket_events"]
                    ],
                }
                for item in matched[:10]
            ],
            "league_diagnostics": fixture_scan.leagues,
        })

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
