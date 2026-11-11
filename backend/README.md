# Backend

## Run locally

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

Health check: `GET http://127.0.0.1:8000/health`

Configuration: `GET http://127.0.0.1:8000/api/v1/config`

Strategy settings: `GET http://127.0.0.1:8000/api/v1/strategy`

Run tests:

```bash
cd backend
pytest
```

The execution mode is deliberately paper-only. No wallet, private key, or live order placement is implemented.
