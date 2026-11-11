from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.polymarket_data import fetch_football_events


def main() -> int:
    events = fetch_football_events(limit=100)
    markets = [
        market
        for event in events
        for market in (event.get("markets") or [])
    ]
    summary = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Polymarket Gamma API",
        "request": "GET /events?active=true&closed=false&tag_slug=soccer&limit=100&offset=0",
        "events_received": len(events),
        "markets_received": len(markets),
        "active_events": sum(bool(event.get("active")) for event in events),
        "open_events": sum(not bool(event.get("closed")) for event in events),
        "sample_events": [
            {
                "title": event.get("title"),
                "slug": event.get("slug"),
                "market_count": len(event.get("markets") or []),
            }
            for event in events[:10]
        ],
        "execution_mode": "read_only",
        "orders_placed": 0,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
