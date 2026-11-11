# POLYEDGE

POLYEDGE is a rules-driven football home-win accumulator research and bankroll-tracking application.

## V1.0 operating rules

- Starting paper bankroll: **$100 USD**.
- Stake allocation: **25% of current bankroll per accumulator**, calculated only when a new accumulator is eligible to start.
- Only one accumulator may be active at a time. No new stake is opened until every leg in the active accumulator is settled.
- Eligible fixtures must feature one of the configured clubs **at home in its domestic league**.
- Apply the configured opponent exclusions exactly. Rules are editable in `config/team_rules.json`.
- Group otherwise eligible fixtures whose scheduled kickoffs fall within a rolling two-hour window into one logical accumulator.
- No minimum odds or model-confidence filter is applied in V1.0. The system still records market availability and execution constraints.
- A logical accumulator is not assumed to be a native Polymarket product. Until combination support is verified, V1 operates in simulation/paper mode and must not imply that separately purchased positions have an all-or-nothing accumulator payout.

## Selected clubs and exclusions

| League | Home club | Opponents to skip |
|---|---|---|
| English Premier League | Arsenal | Liverpool, Manchester United, Manchester City, Brighton, Tottenham Hotspur, Aston Villa, Chelsea |
| La Liga | Barcelona | Real Madrid, Real Betis, Atlético Madrid |
| La Liga | Real Madrid | Barcelona, Real Betis, Atlético Madrid |
| Bundesliga | Bayern Munich | Borussia Dortmund |
| Eredivisie | PSV | Feyenoord |
| Ligue 1 | Paris Saint-Germain | Monaco, Marseille, Strasbourg |
| Primeira Liga | Porto | Sporting CP, Benfica |
| Primeira Liga | Sporting CP | Porto, Benfica |
| Serie A | Inter Milan | AC Milan, Fiorentina, Como, Lazio, Roma, Napoli |

The user may add or remove exclusions later. No missing Portuguese exclusion has been guessed.

## Development status

This repository is being initialized. The first milestone is a testable rules and bankroll core, followed by fixture-data integration, accumulator scheduling, a dashboard, backtesting, and only then any live-market integration.

## Safety and operational controls

- Default to paper trading; live trading must remain disabled until explicitly implemented, reviewed, and enabled.
- Never store private keys, seed phrases, or API secrets in source control.
- Validate fixture competition, home/away orientation, kickoff time, market identity, and settlement status before considering an entry.
- Log skipped fixtures and the exact rule that caused each skip.

## Local development

The initial backend is Python 3.11+ with FastAPI. See `backend/requirements.txt`.
