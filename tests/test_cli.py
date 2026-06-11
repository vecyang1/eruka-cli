import json

import pytest
import requests

import eruka_cli.cli as cli
from eruka_cli.cli import dedupe_keyword_items, main
from eruka_cli.eurekaa_client import AuthContext, ErukaError


class FakeClient:
    """Offline stand-in for EurekaaClient with realistic response shapes."""

    def __init__(self, timeout=None, **kwargs):
        pass

    def course_summary(self, keyword):
        return {
            "courses": 100,
            "totalStudents": 50_000,
            "averagePrice": 20,
            "platforms": [{"_id": "udemy", "count": 90}],
            "categories": [{"_id": "Marketing", "count": 70}],
        }

    def keyword_volume(self, keyword):
        return {
            "summary": {"search_volume": 1000, "cpc": 1.5, "competition": 0.2,
                        "monthly_searches": [["Jan", 800], ["Jun", 1000]]},
            "volumes": [
                {"keyword": "a", "search_volume": 1000, "cpc": 1.5, "competition": 0.2},
                {"keyword": "a alias", "search_volume": 1000, "cpc": 1.5, "competition": 0.2},
                {"keyword": "b", "search_volume": 50, "cpc": 0.3, "competition": 0.1},
            ],
        }

    def similar_keywords(self, keyword):
        return ["adjacent topic"]

    def trend(self, keyword, country_code=None):
        return {"trend": {f"2026-0{m}-01": 40 + m for m in range(1, 7)}}

    def search_courses(self, keyword, limit, page, token):
        return [{"title": "Course", "platform": "udemy", "students": 10, "rating": 4.5, "price": 19}]

    def search_books(self, query, limit, warnings=None):
        return [{"title": "Book", "authors": ["A"], "publishedDate": "2025", "source": "eurekaa"}]

    def doctor(self, from_chrome=False):
        return {
            "public_courses_summary": {"ok": True, "courses": 1},
            "graphql_introspection": {"ok": True},
            "book_search": {"ok": True, "count": 1},
            "trend": {"ok": True, "points": 10},
            "auth": {"ok": False, "source": "none", "token": "missing"},
        }


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(cli, "EurekaaClient", FakeClient)
    monkeypatch.delenv("ERUKA_API_TOKEN", raising=False)
    return monkeypatch


def test_dedupe_drops_alias_rows_keeps_first():
    items = [
        {"keyword": "a", "search_volume": 10, "cpc": 1.0, "competition": 0.5},
        {"keyword": "a2", "search_volume": 10, "cpc": 1.0, "competition": 0.5},
        {"keyword": "b", "search_volume": 10, "cpc": 1.0, "competition": None},
        {"keyword": "c", "search_volume": 99, "cpc": 1.0, "competition": 0.5},
    ]
    deduped = dedupe_keyword_items(items)
    assert [item["keyword"] for item in deduped] == ["a", "b", "c"]


def test_summary_command_renders_markdown(offline, capsys):
    assert main(["summary", "x"]) == 0
    out = capsys.readouterr().out
    assert "Course Demand Summary: x" in out
    assert "opportunity score" in out.lower()


def test_keyword_command_dedupes_by_default(offline, capsys):
    assert main(["keyword", "x", "--limit", "5", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["keyword"] for item in payload["keywords"]] == ["a", "b"]


def test_keyword_command_all_flag_keeps_aliases(offline, capsys):
    assert main(["keyword", "x", "--limit", "5", "--all", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["keywords"]) == 3


def test_trend_command_outputs_momentum(offline, capsys):
    assert main(["trend", "x", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["momentum"]["ok"] is True
    assert payload["momentum"]["weeks"] == 6


def test_trend_command_exits_0_on_empty_series_with_warning(offline, capsys, monkeypatch):
    monkeypatch.setattr(FakeClient, "trend", lambda self, k, country_code=None: {"trend": {}})
    assert main(["trend", "x"]) == 0
    captured = capsys.readouterr()
    assert "No trend data" in captured.out
    assert "no trend history" in captured.err


def test_courses_requires_token(offline, capsys):
    assert main(["courses", "x"]) == 2
    assert "requires ERUKA_API_TOKEN" in capsys.readouterr().err


def test_courses_with_env_token(offline, capsys, monkeypatch):
    monkeypatch.setenv("ERUKA_API_TOKEN", "t")
    assert main(["courses", "x"]) == 0
    out = capsys.readouterr().out
    assert "Course (udemy)" in out
    assert "t" not in out.splitlines()[0]  # token never echoed


def test_book_search_surfaces_fallback_warning(offline, capsys, monkeypatch):
    def fallback_books(self, query, limit, warnings=None):
        if warnings is not None:
            warnings.append("Book results served by Google Books fallback (Eurekaa GraphQL: down).")
        return [{"title": "G", "authors": [], "publishedDate": None, "source": "google_books"}]

    monkeypatch.setattr(FakeClient, "search_books", fallback_books)
    assert main(["book-search", "x"]) == 0
    captured = capsys.readouterr()
    assert "fallback" in captured.err
    assert "[google_books]" in captured.out


def test_brief_includes_trend_and_handles_no_auth(offline, capsys):
    assert main(["brief", "x", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["trend"]["ok"] is True
    assert payload["authWarning"] is not None
    assert payload["courses"] == []


def test_brief_markdown_renders_complete_document(offline, capsys):
    assert main(["brief", "x"]) == 0
    out = capsys.readouterr().out
    for heading in ("## Market Read", "## Keyword Ideas", "## Course Market Signals",
                    "## Course Examples", "## Book Examples", "## Next Research Moves"):
        assert heading in out


def test_brief_survives_trend_failure(offline, capsys, monkeypatch):
    def broken_trend(self, k, country_code=None):
        raise ErukaError("trend down")

    monkeypatch.setattr(FakeClient, "trend", broken_trend)
    assert main(["brief", "x", "--json"]) == 0
    captured = capsys.readouterr()
    assert "trend data unavailable" in captured.err
    assert json.loads(captured.out)["trend"] is None


def test_doctor_exits_2_when_public_checks_fail(offline, capsys, monkeypatch):
    def failing_doctor(self, from_chrome=False):
        return {
            "public_courses_summary": {"ok": False, "error": "down"},
            "graphql_introspection": {"ok": True},
            "book_search": {"ok": True, "count": 1},
            "trend": {"ok": True, "points": 10},
            "auth": {"ok": False, "source": "none", "token": "missing"},
        }

    monkeypatch.setattr(FakeClient, "doctor", failing_doctor)
    assert main(["doctor"]) == 2


def test_doctor_exits_0_when_only_auth_missing(offline):
    assert main(["doctor"]) == 0


def test_main_maps_network_errors_to_exit_2(offline, capsys, monkeypatch):
    def boom(self, keyword):
        raise requests.ConnectionError("dns failure")

    monkeypatch.setattr(FakeClient, "course_summary", boom)
    assert main(["summary", "x"]) == 2
    assert "network error" in capsys.readouterr().err


def test_unrecognized_volume_shape_warns(offline, capsys, monkeypatch):
    monkeypatch.setattr(FakeClient, "keyword_volume", lambda self, k: {"totally": "new-shape"})
    assert main(["keyword", "x"]) == 0
    assert "unrecognized shape" in capsys.readouterr().err
