# POLYEDGE Cloudflare Pages API setup

The frontend is deployed as a Cloudflare Pages site. Its API is implemented with Pages Functions in `functions/api/[[path]].js`; this avoids sending browser API requests to the static-site origin and receiving an HTML 404 page instead of JSON.

## Required Cloudflare settings

Open **Workers & Pages → polyedge → Settings**.

### 1. Create and bind the D1 database

1. In Cloudflare, open **Storage & databases → D1 SQL Database**.
2. Create a database named `polyedge-db`.
3. Open the Pages project **polyedge → Settings → Functions → D1 database bindings**.
4. Add a binding:
   - Variable name: `POLYEDGE_DB`
   - D1 database: `polyedge-db`
5. Save the setting.

The API creates its account, cycles, and settlement-ledger tables automatically on first use. The D1 binding is required for persistent rollover state.

### 2. Add the football-data.org API token

1. Open the Pages project **Settings → Variables and Secrets**.
2. Add an encrypted secret:
   - Name: `FOOTBALL_DATA_API_TOKEN`
   - Value: your football-data.org API token
3. Save it for the Production environment (and Preview too, if you test preview deployments).

Do not put the token in frontend code, GitHub files, screenshots, or chat.

### 3. Confirm the Pages build settings

The project should use:
- Framework preset: **None**
- Root directory: `frontend`
- Build command: leave blank
- Build output directory: `.`

Pages Functions are deployed automatically from `frontend/functions`.

### 4. Redeploy and verify

After saving the D1 binding and secret, open **Deployments** and retry the latest deployment (or push a new commit). Then test these URLs using the deployed Pages domain:

- `/api/health` — should return JSON with `"status":"ok"`
- `/api/v1/config` — should return the selected club rules
- `/api/v1/strategy` — should return the $20 / 25% paper strategy
- `/api/v1/rollover` — should return $20 equity, $5 next stake, and $15 reserve
- `/api/v1/polymarket/football-markets?days=14&limit=5` — should return live fixture and public market research

The first rollover request initializes the D1 tables. The first market request requires a valid football-data.org token and may take longer because it checks each configured domestic league and then searches Polymarket for qualifying fixtures.

## Operating safeguards

- The API is read-only for fixture and market research.
- Rollover settlement is a paper ledger only.
- No wallet, private key, signing, order placement, or live trading is implemented.
- Keep D1 attached to the production Pages environment so the settlement ledger persists across deployments.
