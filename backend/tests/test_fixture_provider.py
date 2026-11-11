from datetime import date

from app.fixture_provider import COMPETITIONS, fetch_fixtures_with_diagnostics


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "matches": [
                {
                    "status": "SCHEDULED",
                    "utcDate": "2026-11-12T18:00:00Z",
                    "homeTeam": {"name": "Arsenal"},
                    "awayTeam": {"name": "Everton"},
                },
                {
                    "status": "TIMED",
                    "utcDate": "2026-11-13T18:00:00Z",
                    "homeTeam": {"name": "Arsenal"},
                    "awayTeam": {"name": "Chelsea"},
                },
                {
                    "status": "FINISHED",
                    "utcDate": "2026-11-10T18:00:00Z",
                    "homeTeam": {"name": "Arsenal"},
                    "awayTeam": {"name": "Liverpool"},
                },
            ]
        }


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params):
        self.calls.append((url, params))
        return FakeResponse()


def test_fetch_includes_scheduled_and_timed_and_reports_each_league(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_TOKEN", "test-token")
    monkeypatch.setattr("app.fixture_provider.httpx.Client", FakeClient)

    result = fetch_fixtures_with_diagnostics(date(2026, 11, 11), date(2026, 11, 18))

    assert len(result.fixtures) == len(COMPETITIONS) * 2
    assert len(result.leagues) == len(COMPETITIONS)
    assert all(item["scheduled"] == 1 for item in result.leagues)
    assert all(item["timed"] == 1 for item in result.leagues)
    assert all(item["accepted_upcoming"] == 2 for item in result.leagues)
    assert all(item["ignored_other_statuses"] == 1 for item in result.leagues)
