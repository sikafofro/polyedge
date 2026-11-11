# POLYEDGE

POLYEDGE is a rules-driven football home-win accumulator research and bankroll-tracking application.

## V1.1 operating rules

- Starting paper bankroll: **$20 USD**.
- Stake allocation: **25% of current settled bankroll per accumulator**. The initial stake is **$5.00**.
- Only one active accumulator may be active at a time; wait for full settlement before the next entry.
- Only configured clubs playing **at home in their domestic league** qualify.
- Apply opponent exclusions in `config/team_rules.json`.
- Group eligible kickoffs into rolling two-hour windows anchored at the first kickoff in each group.
- No minimum odds or confidence filter is applied.
- Execution remains **paper-only**. A logical accumulator is not represented as a native Polymarket combo unless platform support is verified.

## Bankroll configuration

The starting balance and stake fraction are stored in `config/strategy.json`. The API's `GET /api/v1/strategy` endpoint and dashboard read these settings from the same file. The initial stake is calculated as:

`$20.00 × 25% = $5.00`

This is the initial allocation only. The next stake must be recalculated from settled available bankroll after the previous accumulator is fully settled. A persistent settlement ledger is a separate development milestone; this configuration change does not itself implement balance persistence.

## Configured clubs

| League | Home club | Opponents to skip |
|---|---|---|
| English Premier League | Arsenal | Liverpool, Manchester United, Manchester City, Brighton, Tottenham Hotspur, Aston Villa, Chelsea |
| Spanish La Liga | Barcelona | Real Madrid, Real Betis, Atlético Madrid |
| Spanish La Liga | Real Madrid | Barcelona, Real Betis, Atlético Madrid |
| German Bundesliga | Bayern Munich | Borussia Dortmund |
| Dutch Eredivisie | PSV | Feyenoord |
| French Ligue 1 | Paris Saint-Germain | Monaco, Marseille, Strasbourg |
| Portuguese Primeira Liga | Porto | Sporting CP, Benfica |
| Portuguese Primeira Liga | Sporting CP | Porto, Benfica |
| Italian Serie A | Inter Milan | AC Milan, Fiorentina, Como, Lazio, Roma, Napoli |

One additional Portuguese exclusion was mentioned but not identified; it has deliberately not been guessed.

## Polymarket read-only market connector\n\nThe read-only endpoint `GET /api/v1/polymarket/football-markets?days=14&limit=100` reads active soccer events from the public Polymarket Gamma API and conservatively matches event titles to qualifying upcoming fixtures. Public market data requires no wallet credentials. The endpoint returns event/market identifiers, outcome prices, liquidity and volume where supplied. It does not access private account data or submit, cancel, or sign orders. Name matching is deliberately conservative: unmatched fixtures remain unmatched for manual review.\n\nGamma API: `https://gamma-api.polymarket.com/events` (active, open soccer events).\n\n## CSV fixture scanner

Required CSV columns: `kickoff,country,league,competition_type,home_team,away_team`. Kickoff must be ISO-8601 with timezone. The sample in `data/sample_fixtures.csv` is synthetic test data only.

### Run the API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

### Live fixture provider and daily scan

POLYEDGE uses football-data.org API v4. Store its token as the GitHub Actions secret `FOOTBALL_DATA_API_TOKEN`; never put the token in source code or chat. The daily workflow runs at 06:00 UTC and saves a fixture report artifact for 14 days. It retains `SCHEDULED` and `TIMED` fixtures and records per-league diagnostics.

The API endpoints include `GET /health`, `GET /api/v1/config`, `GET /api/v1/strategy`, `GET /api/v1/fixtures/live?days=7`, `POST /api/v1/fixtures/scan`, and `POST /api/v1/fixtures/upload`.

## Tests

```bash
cd backend
pytest
```

## Safety and operational controls

- No wallet, private key, seed phrase, or live order placement is implemented.
- Validate competition, home/away orientation, timezone, market identity, and settlement before considering execution.
- Log skipped fixtures and the exact rule that caused each skip.
- Polymarket multi-event accumulator support must be verified before any execution design is treated as tradable.


## Four-odds sequential rollover engine (paper only)

The rollover engine is implemented in `backend/app/rollover.py` and exposed through:

- `GET /api/v1/rollover` — account equity, current cycle, reserve, next 25% stake, cumulative odds, pilot-readiness flag and settlement history.
- `POST /api/v1/rollover/settle` — records one already-settled paper selection. JSON fields: `fixture`, `selection`, `decimal_odds`, and `result` (`won`, `lost`, or `void`).

### Rollover accounting

Each cycle allocates 25% of settled equity as the initial rollover stake and leaves 75% as reserve. Winning legs are sequential: the full returned stake is rolled into the next selection until cumulative decimal odds reach at least 4.00. A void leg returns the current exposure without advancing cumulative odds. A loss consumes the cycle's initial stake and starts a new cycle from remaining equity (unless the account is exhausted).

On a successful cycle, new equity is the untouched reserve plus the full final returned stake. For example, $20 starts with a $5 rollover stake and $15 reserve. At exactly 4.00 cumulative odds, the $5 becomes $20; new equity is therefore $35 and the next 25% stake is $8.75. This includes the returned principal as well as profit and avoids understating account equity.

The first completed 4.00+ paper rollover sets `pilot_ready=true`. This is an operational smoke-test milestone only, **not evidence of a profitable strategy and not an automatic live-trading switch**. Live execution remains disabled; no wallet or order-submission integration is present.

The ledger uses SQLite at `data/rollover.sqlite3` by default. Set `POLYEDGE_ROLLOVER_DB` to a path on a persistent mounted volume in deployment; an ephemeral filesystem can lose the ledger on restart or redeploy. Back up this database before any future live pilot.

Configuration keys: `rollover_target_odds`, `rollover_equity_target_usd`, `rollover_settlement_mode`, `paper_cycle_required_for_pilot_readiness`, and `live_execution_enabled`.
