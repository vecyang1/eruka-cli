from pathlib import Path

from eruka_cli.models import calculate_opportunity
from eruka_cli.report import (
    fmt_int,
    fmt_value,
    format_book_row,
    format_course_row,
    render_brief_markdown,
    render_summary_markdown,
    render_trend_markdown,
    write_brief,
)


def _minimal_brief(**overrides):
    data = {
        "keyword": "digital marketing",
        "generatedAt": "2026-06-11T00:00:00+00:00",
        "summary": {"courses": 10, "totalStudents": 100, "platforms": [], "categories": []},
        "keywordSummary": {"search_volume": 1000, "cpc": 1.5, "competition": 0.2},
        "keywords": [],
        "opportunity": {"score": 50, "rationale": "test"},
        "courses": [],
        "books": [],
    }
    data.update(overrides)
    return data


def test_fmt_int_tolerates_none_floats_and_strings():
    assert fmt_int(None) == "?"
    assert fmt_int(1234567) == "1,234,567"
    assert fmt_int(673000.0) == "673,000"
    assert fmt_int("42") == "42"
    assert fmt_int("not a number") == "?"


def test_fmt_value_renders_none_as_placeholder():
    assert fmt_value(None) == "?"
    assert fmt_value(0.16) == "0.16"


def test_summary_markdown_survives_none_counts():
    summary = {
        "courses": 5,
        "totalStudents": None,
        "averagePrice": None,
        "platforms": [{"_id": "udemy", "count": None}, {"_id": "edx", "count": 3}],
        "categories": [{"_id": "Marketing", "count": None}],
    }
    score = calculate_opportunity(summary, {})
    markdown = render_summary_markdown("x", summary, score)
    assert "- udemy: ?" in markdown
    assert "- edx: 3" in markdown
    assert "Total students: ?" in markdown


def test_brief_markdown_survives_none_keyword_summary():
    markdown = render_brief_markdown(_minimal_brief(
        keywordSummary={"search_volume": None, "cpc": None, "competition": None},
        summary={"courses": None, "totalStudents": None, "platforms": [{"_id": "udemy", "count": None}], "categories": []},
    ))
    assert "Keyword search volume: ?" in markdown
    assert "Top platform: udemy (? courses)" in markdown


def test_brief_markdown_renders_auth_warning_callout():
    markdown = render_brief_markdown(_minimal_brief(authWarning="Chrome CDP unreachable"))
    assert "> Degraded: Chrome CDP unreachable" in markdown


def test_brief_markdown_renders_book_fallback_warnings_and_source_tags():
    markdown = render_brief_markdown(_minimal_brief(
        bookWarnings=["Book results served by Google Books fallback (Eurekaa GraphQL: boom)."],
        books=[{"title": "B", "authors": ["A"], "publishedDate": "2025", "source": "google_books"}],
    ))
    assert "> Note: Book results served by Google Books fallback" in markdown
    assert "[google_books]" in markdown


def test_brief_markdown_includes_trend_momentum_line():
    markdown = render_brief_markdown(_minimal_brief(
        trend={"ok": True, "momentum": 0.21, "latestValue": 88.0, "latestDate": "2026-06-07",
               "recentAvg": 80.0, "priorAvg": 66.0, "weeks": 104, "peakDate": "2026-05-01", "peakValue": 100.0},
    ))
    assert "Search interest momentum: +21.0% (rising" in markdown


def test_trend_markdown_handles_empty_series():
    markdown = render_trend_markdown("x", {"ok": False, "weeks": 0})
    assert "No trend data available" in markdown


def test_course_and_book_rows_render_missing_fields():
    assert format_course_row({}) == "- Untitled (?) - ? students, rating ?, price ?"
    row = format_book_row({"title": None, "authors": [], "publishedDate": None})
    assert row.startswith("- Untitled by Unknown (n.d.)")


def test_write_brief_creates_slugged_file(tmp_path: Path):
    path = write_brief(tmp_path, "Digital Marketing!", "# hi\n")
    assert path.exists()
    assert path.name.endswith("-digital-marketing.md")
    assert path.read_text(encoding="utf-8") == "# hi\n"
