from eruka_cli.models import calculate_opportunity
from eruka_cli.cli import _keyword_items, build_parser
from eruka_cli.eurekaa_client import _normalize_eurekaa_books
from eruka_cli.report import render_brief_markdown, slugify


def test_slugify_keeps_report_names_readable():
    assert slugify("Digital Marketing for Local Business!") == "digital-marketing-for-local-business"


def test_opportunity_score_is_bounded_and_uses_real_inputs():
    summary = {"courses": 100, "totalStudents": 50_000, "averagePrice": 20}
    keyword = {
        "search_volume": 12_000,
        "monthly_searches": [["Jan-2026", 8_000], ["Apr-2026", 12_000]],
    }
    score = calculate_opportunity(summary, keyword)
    assert 0 <= score.score <= 100
    assert score.score > 0
    assert "100 courses" in score.rationale


def test_keyword_items_accepts_eurekaa_volumes_shape():
    data = {"volumes": [{"keyword": "digital marketing", "search_volume": 673000}]}
    assert _keyword_items(data, 1) == [{"keyword": "digital marketing", "search_volume": 673000}]


def test_brief_includes_public_course_market_signals_without_auth_rows():
    markdown = render_brief_markdown({
        "keyword": "digital marketing",
        "generatedAt": "2026-05-23T00:00:00+00:00",
        "summary": {
            "courses": 1069,
            "totalStudents": 9_773_146,
            "platforms": [{"_id": "udemy", "count": 970}],
            "categories": [{"_id": "Marketing", "count": 728}],
        },
        "keywordSummary": {"search_volume": 673000, "cpc": 6.38, "competition": 0.16},
        "keywords": [],
        "opportunity": {
            "score": 89,
            "rationale": "1,069 courses, 9,773,146 students, 673,000 monthly searches, trend delta +48.6%",
        },
        "courses": [],
        "books": [],
        "authWarning": "No token available; authenticated course examples skipped.",
    })

    assert "## Course Market Signals" in markdown
    assert "- Top platform: udemy (970 courses)" in markdown
    assert "- Top category: Marketing (728 courses)" in markdown


def test_eurekaa_book_search_json_normalizes_to_book_rows():
    rows = _normalize_eurekaa_books({
        "items": [
            {
                "id": "4pZlDQAAQBAJ",
                "title": "Understanding Digital Marketing",
                "authors": ["Damian Ryan"],
                "publishedDate": "2016-11-03",
                "categories": ["Business & Economics"],
                "pageCount": 432,
                "averageRating": 4.5,
                "ratingsCount": 22,
                "previewLink": "https://books.google.com/books?id=4pZlDQAAQBAJ",
            }
        ]
    }, limit=1)

    assert rows == [{
        "id": "4pZlDQAAQBAJ",
        "title": "Understanding Digital Marketing",
        "authors": ["Damian Ryan"],
        "publishedDate": "2016-11-03",
        "categories": ["Business & Economics"],
        "pageCount": 432,
        "averageRating": 4.5,
        "ratingsCount": 22,
        "description": None,
        "previewLink": "https://books.google.com/books?id=4pZlDQAAQBAJ",
        "source": "eurekaa",
    }]


def test_book_search_help_matches_multi_source_contract():
    help_text = build_parser().format_help()

    assert "Eurekaa" in help_text
    assert "Google Books-backed" not in help_text
