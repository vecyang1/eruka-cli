from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import OpportunityScore


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "research"


def fmt_int(value: Any) -> str:
    """Format a count for humans; tolerates None, floats, and numeric strings."""
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "?"


def fmt_value(value: Any, missing: str = "?") -> str:
    return missing if value is None else str(value)


def compact_course(course: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": course.get("title"),
        "platform": course.get("platform"),
        "students": course.get("students"),
        "rating": course.get("rating"),
        "price": course.get("price"),
        "duration": course.get("duration"),
        "badge": course.get("badge"),
        "url": course.get("url"),
    }


def compact_book(book: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": book.get("title"),
        "authors": book.get("authors") or [],
        "publishedDate": book.get("publishedDate"),
        "categories": book.get("categories") or [],
        "pageCount": book.get("pageCount"),
        "rating": book.get("averageRating"),
        "ratingsCount": book.get("ratingsCount"),
        "previewLink": book.get("previewLink"),
        "source": book.get("source"),
    }


def emit_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def format_course_row(course: dict[str, Any]) -> str:
    return (
        f"- {fmt_value(course.get('title'), 'Untitled')} ({fmt_value(course.get('platform'))}) - "
        f"{fmt_int(course.get('students'))} students, rating {fmt_value(course.get('rating'))}, "
        f"price {fmt_value(course.get('price'))}"
    )


def format_book_row(book: dict[str, Any]) -> str:
    authors = ", ".join(book.get("authors") or [])
    source = book.get("source")
    suffix = f" [{source}]" if source and source != "eurekaa" else ""
    return (
        f"- {fmt_value(book.get('title'), 'Untitled')} by {authors or 'Unknown'} "
        f"({book.get('publishedDate') or 'n.d.'}){suffix}"
    )


def _top_count(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return max(items, key=lambda item: item.get("count") or 0)


def render_summary_markdown(keyword: str, summary: dict[str, Any], score: OpportunityScore) -> str:
    platforms = summary.get("platforms") or []
    top_platforms = sorted(platforms, key=lambda item: item.get("count") or 0, reverse=True)[:8]
    categories = summary.get("categories") or []
    top_categories = sorted(categories, key=lambda item: item.get("count") or 0, reverse=True)[:8]

    lines = [
        f"# Course Demand Summary: {keyword}",
        "",
        f"- Eruka opportunity score: **{score.score}/100**",
        f"- Rationale: {score.rationale}",
        f"- Total courses: {fmt_int(summary.get('courses', 0))}",
        f"- Total students: {fmt_int(summary.get('totalStudents', 0))}",
        f"- Average price: {fmt_value(summary.get('averagePrice', 0))}",
        "",
        "## Top Platforms",
        "",
    ]
    lines.extend(f"- {item.get('_id')}: {fmt_int(item.get('count'))}" for item in top_platforms)
    lines.extend(["", "## Top Categories", ""])
    lines.extend(f"- {item.get('_id')}: {fmt_int(item.get('count'))}" for item in top_categories)
    return "\n".join(lines).strip() + "\n"


def render_trend_markdown(keyword: str, momentum: dict[str, Any], country: str | None = None) -> str:
    scope = f" ({country})" if country else " (worldwide)"
    lines = [f"# Demand Trend: {keyword}{scope}", ""]
    if not momentum.get("ok"):
        lines.append("- No trend data available for this keyword.")
        return "\n".join(lines).strip() + "\n"
    direction = "rising" if momentum["momentum"] > 0.05 else ("falling" if momentum["momentum"] < -0.05 else "flat")
    lines.extend([
        f"- Momentum: **{momentum['momentum']:+.1%}** ({direction}; last 12 weeks vs prior 12)",
        f"- Latest interest: {momentum['latestValue']:.0f} on {momentum['latestDate']}",
        f"- Recent 12-week average: {momentum['recentAvg']}",
        f"- Peak: {momentum['peakValue']:.0f} on {momentum['peakDate']}",
        f"- History: {momentum['weeks']} weekly points",
    ])
    return "\n".join(lines).strip() + "\n"


def render_brief_markdown(data: dict[str, Any]) -> str:
    keyword = data.get("keyword", "")
    score = data.get("opportunity") or {}
    summary = data.get("summary") or {}
    keyword_summary = data.get("keywordSummary") or {}
    top_platform = _top_count(summary.get("platforms") or [])
    top_category = _top_count(summary.get("categories") or [])
    lines = [
        f"# Eruka Research Brief: {keyword}",
        "",
        f"Generated: {data.get('generatedAt', '')}",
        "",
        "## Market Read",
        "",
        f"- Opportunity score: **{score.get('score', '?')}/100**",
        f"- Rationale: {score.get('rationale', 'unavailable')}",
        f"- Courses: {fmt_int(summary.get('courses', 0))}",
        f"- Students: {fmt_int(summary.get('totalStudents', 0))}",
        f"- Keyword search volume: {fmt_int(keyword_summary.get('search_volume', 0))}",
        f"- Average CPC: {fmt_value(keyword_summary.get('cpc'))}",
        f"- Competition: {fmt_value(keyword_summary.get('competition'))}",
    ]

    trend = data.get("trend")
    if trend and trend.get("ok"):
        direction = "rising" if trend["momentum"] > 0.05 else ("falling" if trend["momentum"] < -0.05 else "flat")
        lines.append(
            f"- Search interest momentum: {trend['momentum']:+.1%} ({direction}, "
            f"latest {trend['latestValue']:.0f} on {trend['latestDate']})"
        )

    lines.extend(["", "## Keyword Ideas", ""])
    for item in data.get("keywords", [])[:12]:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('keyword')}: volume {fmt_value(item.get('search_volume'))}, "
                f"CPC {fmt_value(item.get('cpc'))}, competition {fmt_value(item.get('competition'))}"
            )
        else:
            lines.append(f"- {item}")

    lines.extend(["", "## Course Market Signals", ""])
    if top_platform:
        lines.append(f"- Top platform: {top_platform.get('_id')} ({fmt_int(top_platform.get('count'))} courses)")
    if top_category:
        lines.append(f"- Top category: {top_category.get('_id')} ({fmt_int(top_category.get('count'))} courses)")
    lines.append(
        f"- Public summary confirms {fmt_int(summary.get('courses', 0))} total courses "
        f"and {fmt_int(summary.get('totalStudents', 0))} total students."
    )

    lines.extend(["", "## Course Examples", ""])
    auth_warning = data.get("authWarning")
    if auth_warning:
        lines.extend([f"> Degraded: {auth_warning}", ""])
    courses = data.get("courses") or []
    if courses:
        lines.extend(format_course_row(course) for course in courses)
    elif not auth_warning:
        lines.append("- Authenticated Eurekaa course rows unavailable; use `--from-chrome` or `ERUKA_API_TOKEN`.")

    lines.extend(["", "## Book Examples", ""])
    book_warnings = data.get("bookWarnings") or []
    if book_warnings:
        lines.extend(f"> Note: {warning}" for warning in book_warnings)
        lines.append("")
    lines.extend(format_book_row(book) for book in data.get("books", []))

    lines.extend(["", "## Next Research Moves", ""])
    lines.extend([
        "- Inspect the top 3 course outlines and extract repeated module promises.",
        "- Compare high-volume keywords against low-course-count niches.",
        "- Use Reddit/Crowd Insights separately for pain-language validation.",
        "- Turn the best gap into a narrow course promise before drafting modules.",
    ])
    return "\n".join(lines).strip() + "\n"


def write_brief(out_dir: str | Path, keyword: str, markdown: str) -> Path:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    # UTC so the filename stamp matches the generatedAt field inside the brief.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    file_path = path / f"{stamp}-{slugify(keyword)}.md"
    file_path.write_text(markdown, encoding="utf-8")
    return file_path
