import json

import pytest
import requests

from eruka_cli import __version__
from eruka_cli.eurekaa_client import (
    ErukaError,
    EurekaaClient,
    _normalize_eurekaa_books,
    resolve_auth,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise json.JSONDecodeError("no json", self.text or "x", 0)
        return self._payload


def test_session_has_user_agent_and_retries():
    client = EurekaaClient()
    assert client.session.headers["User-Agent"].startswith(f"eruka-cli/{__version__}")
    adapter = client.session.get_adapter("https://backend.eurekaa.io")
    assert adapter.max_retries.total == 3
    assert 503 in adapter.max_retries.status_forcelist


def test_timeout_is_connect_read_tuple():
    client = EurekaaClient()
    assert isinstance(client.timeout, tuple) and len(client.timeout) == 2


def test_graphql_raises_eruka_error_on_null_data(monkeypatch):
    client = EurekaaClient()
    monkeypatch.setattr(client.session, "post", lambda *a, **k: FakeResponse(payload={"data": None}))
    with pytest.raises(ErukaError, match="no data"):
        client.graphql("{ __typename }")


def test_graphql_raises_eruka_error_on_non_json(monkeypatch):
    client = EurekaaClient()
    monkeypatch.setattr(client.session, "post", lambda *a, **k: FakeResponse(payload=None, text="<html>err</html>"))
    with pytest.raises(ErukaError, match="non-JSON"):
        client.graphql("{ __typename }")


def test_normalize_eurekaa_books_unwraps_volume_info():
    rows = _normalize_eurekaa_books({
        "items": [{"id": "abc", "volumeInfo": {"title": "T", "authors": ["A"], "publishedDate": "2020"}}],
    }, limit=5)
    assert rows[0]["title"] == "T"
    assert rows[0]["source"] == "eurekaa"


def test_search_eurekaa_books_rejects_non_dict_payload(monkeypatch):
    client = EurekaaClient()
    monkeypatch.setattr(client, "graphql", lambda *a, **k: {"searchBooks": ["not", "a", "dict"]})
    with pytest.raises(ErukaError, match="Unexpected searchBooks payload"):
        client._search_eurekaa_books("x", 5)


def test_google_books_results_are_source_labeled(monkeypatch):
    client = EurekaaClient()
    payload = {"items": [{"id": "g1", "volumeInfo": {"title": "G"}}]}
    monkeypatch.setattr(client.session, "get", lambda *a, **k: FakeResponse(payload=payload))
    books = client._search_google_books("x", 5)
    assert books[0]["source"] == "google_books"


def test_search_books_records_fallback_warning(monkeypatch):
    client = EurekaaClient()

    def broken_eurekaa(query, limit):
        raise ErukaError("boom")

    monkeypatch.setattr(client, "_search_eurekaa_books", broken_eurekaa)
    monkeypatch.setattr(client, "_search_google_books", lambda q, l: [{"title": "G", "source": "google_books"}])
    warnings = []
    books = client.search_books("x", 5, warnings=warnings)
    assert books and books[0]["source"] == "google_books"
    assert warnings and "Google Books" in warnings[0] and "boom" in warnings[0]


def test_search_books_raises_when_all_sources_fail(monkeypatch):
    client = EurekaaClient()
    for name in ("_search_eurekaa_books", "_search_google_books", "_search_open_library"):
        monkeypatch.setattr(client, name, lambda q, l: (_ for _ in ()).throw(ErukaError("down")))
    with pytest.raises(ErukaError, match="all configured sources"):
        client.search_books("x", 5)


def test_resolve_auth_prefers_env_token(monkeypatch):
    monkeypatch.setenv("ERUKA_API_TOKEN", "secret-token-value")
    auth = resolve_auth()
    assert auth.present
    assert auth.source == "ERUKA_API_TOKEN"
    assert "secret-token-value" not in auth.masked()


def test_resolve_auth_absent_without_env(monkeypatch):
    monkeypatch.delenv("ERUKA_API_TOKEN", raising=False)
    auth = resolve_auth()
    assert not auth.present
    assert auth.masked() == "missing"


def test_doctor_omits_email_and_flags_missing_courses(monkeypatch):
    client = EurekaaClient()
    monkeypatch.delenv("ERUKA_API_TOKEN", raising=False)
    monkeypatch.setattr(client, "course_summary", lambda k: {"unexpected": True})
    monkeypatch.setattr(client, "graphql", lambda *a, **k: {"__typename": "Query"})
    monkeypatch.setattr(client, "search_books", lambda q, l, warnings=None: [{"title": "B", "source": "eurekaa"}])
    monkeypatch.setattr(client, "trend", lambda k, country_code=None: {"trend": {"2026-01-04": 50}})
    checks = client.doctor()
    assert checks["public_courses_summary"]["ok"] is False
    assert "reason" in checks["public_courses_summary"]
    assert "email" not in checks["auth"]
    assert checks["trend"]["ok"] is True
