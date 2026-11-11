# POLYEDGE

POLYEDGE is a rules-driven football home-win accumulator research and bankroll-tracking application.

## V1.0 operating rules

- Starting paper bankroll: **$100 USD**.
- Stake allocation: **25% of current settled bankroll per accumulator**.
- Only one active accumulator may be active at a time; wait for full settlement before the next entry.
- Only configured clubs playing **at home in their domestic league** qualify.
- Apply opponent exclusions in `config/team_rules.json`.
- Group eligible kickoffs into rolling two-hour windows anchored at the first kickoff in each group.
- No minimum odds or confidence filter is applied in V1.
- Execution remains **paper-only**. A logical accumulator is not represented as a native Polymarket combo unless platform support is verified.

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

## CSV fixture scanner

The first scanner milestone uses CSV input so the rules can be tested before connecting a live fixture provider.

Required CSV columns:

`kickoff,country,league,competition_type,home_team,away_team`

- `kickoff` must be ISO-8601 and include a timezone, for example `2026-11-14T09:00:00+00:00`.
- `competition_type` must be `domestic_league` to qualify.
- The sample in `data/sample_fixtures.csv` is **synthetic test data, not real fixtures**.

### Run the API

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

### Scan fixtures

Send the CSV text as JSON to the scanner:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/fixtures/scan \
  -H "Content-Type: application/json" \
  --data-binary @- <<'JSON'
{"csv_text":"kickoff,country,league,competition_type,home_team,away_team\n2026-11-14T09:00:00+00:00,England,Premier League,domestic_league,Arsenal,Everton\n"}
JSON
```

The response separates qualifying and skipped fixtures, explains skip reasons, and groups eligible matches into accumulator windows.

You can also upload a CSV file directly:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/fixtures/upload \\
  -F "file=@data/sample_fixtures.csv;type=text/csv"
```

The upload endpoint accepts UTF-8 CSV files with a `.csv` filename. The sample file is synthetic test data only.

Other endpoints:
- `GET /health`
- `GET /api/v1/config`
- `GET /api/v1/strategy`
- `GET /api/v1/fixtures/sample-csv`

## Live fixture provider and daily scan

POLYEDGE uses the football-data.org API v4 for scheduled fixtures. Its published free coverage currently includes all seven leagues configured above: Premier League, La Liga, Bundesliga, Eredivisie, Ligue 1, Primeira Liga and Serie A. The free tier has request limits and delayed schedule/score data; this integration retrieves scheduled fixtures, not live scores.

1. Register for a free API account at https://www.football-data.org/client/register.
2. Retrieve your API token from your account or registration email.
3. In GitHub, open this repository's **Settings → Secrets and variables → Actions → New repository secret**.
4. Create a secret named `FOOTBALL_DATA_API_TOKEN` and paste the token as its value. Never put the token in a source file or chat.
5. Open **Actions → Daily POLYEDGE fixture scan → Run workflow** to trigger the first manual scan. The workflow is also scheduled daily at 06:00 UTC (06:00 Accra time).

The daily workflow saves a JSON report as a downloadable Actions artifact for 14 days. If the secret is missing, the scan will fail safely and place no bets. The live API endpoint is `GET /api/v1/fixtures/live?days=7`; it requires the token in the backend environment.

Football data provided by the Football-Data.org API.

## Tests

```bash
cd backend
pytest
```

## Safety and operational controls

- No wallet, private key, seed phrase, or live order placement is implemented.
- Validate competition, home/away orientation, timezone, market identity, and settlement before considering execution.
- Log skipped fixtures and the exact rule that caused each skip.
