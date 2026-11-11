from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import group_fixtures, qualify_fixture
from app.fixture_provider import (
    FixtureProviderError,
    fetch_fixtures_with_diagnostics,
    upcoming_range,
)


def main() -> int:
    try:
        start, end = upcoming_range(days=7)
        scan = fetch_fixtures_with_diagnostics(start, end)
        fixtures = scan.fixtures
    except (FixtureProviderError, ValueError) as exc:
        print(f"Fixture scan failed: {exc}", file=sys.stderr)
        return 1

    rules = json.loads((ROOT / "config" / "team_rules.json").read_text(encoding="utf-8"))
    eligible = []
    skipped = []
    eligible_fixtures = []
    for fixture in fixtures:
        qualifies, reason = qualify_fixture(fixture, rules)
        row = {
            "kickoff": fixture.kickoff.isoformat(),
            "country": fixture.country,
            "league": fixture.league,
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "reason": reason,
        }
        (eligible if qualifies else skipped).append(row)
        if qualifies:
            eligible_fixtures.append(fixture)

    groups = group_fixtures(eligible_fixtures, 120)
    report = {
        "provider": "football-data.org",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "total_fixtures": len(fixtures),
        "qualifying_fixtures": len(eligible),
        "skipped_fixtures": len(skipped),
        "league_diagnostics": scan.leagues,
        "eligible": eligible,
        "skipped": skipped,
        "accumulator_groups": [
            {
                "group_number": i,
                "fixtures": [
                    {
                        "kickoff": f.kickoff.isoformat(),
                        "home_team": f.home_team,
                        "away_team": f.away_team,
                        "league": f.league,
                    }
                    for f in group
                ],
            }
            for i, group in enumerate(groups, start=1)
        ],
        "execution_mode": "paper",
        "note": "This report contains fixtures only. No bets were placed.",
    }
    output = ROOT / "fixture-scan-report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    summary = {
        key: report[key]
        for key in (
            "provider",
            "date_from",
            "date_to",
            "total_fixtures",
            "qualifying_fixtures",
            "skipped_fixtures",
        )
    }
    summary["leagues"] = [
        {
            "league": item["league"],
            "api_matches": item["api_matches"],
            "scheduled": item["scheduled"],
            "timed": item["timed"],
            "accepted_upcoming": item["accepted_upcoming"],
            "error": item["error"],
        }
        for item in scan.leagues
    ]
    print(json.dumps(summary, indent=2))
    print(f"Full report written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
