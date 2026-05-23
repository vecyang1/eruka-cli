from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import OpportunityScore


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "research"


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
    }


def emit_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _top_count(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return max(items, key=lambda item: item.get("count") or 0)


def render_summary_markdown(keyword: str, summary: dict[str, Any], score: OpportunityScore) -> str:
    platforms = summary.get("platforms") or []
    top_platforms = sorted(platforms, key=lambda item: item.get("count", 0), reverse=True)[:8]
    categories = summary.get("categories") or []
    top_categories = sorted(categories, key=lambda item: item.get("count", 0), reverse=True)[:8]

    lines = [
        f"# Course Demand Summary: {keyword}",
        "",
        f"- Eruka opportunity score: **{score.score}/100**",
        f"- Rationale: {score.rationale}",
        f"- Total courses: {summary.get('courses', 0):,}",
        f"- Total students: {summary.get('totalStudents', 0):,}",
        f"- Average price: {summary.get('averagePrice', 0)}",
        "",
        "## Top Platforms",
        "",
    ]
    lines.extend(f"- {item.get('_id')}: {item.get('count'):,}" for item in top_platforms)
    lines.extend(["", "## Top Categories", ""])
    lines.extend(f"- {item.get('_id')}: {item.get('count'):,}" for item in top_categories)
    return "\n".join(lines).strip() + "\n"


def render_brief_markdown(data: dict[str, Any]) -> str:
    keyword = data["keyword"]
    score = data["opportunity"]
    summary = data["summary"]
    top_platform = _top_count(summary.get("platforms") or [])
    top_category = _top_count(summary.get("categories") or [])
    lines = [
        f"# Eruka Research Brief: {keyword}",
        "",
        f"Generated: {data['generatedAt']}",
        "",
        "## Market Read",
        "",
        f"- Opportunity score: **{score['score']}/100**",
        f"- Rationale: {score['rationale']}",
        f"- Courses: {data['summary'].get('courses', 0):,}",
        f"- Students: {data['summary'].get('totalStudents', 0):,}",
        f"- Keyword search volume: {data.get('keywordSummary', {}).get('search_volume', 0):,}",
        f"- Average CPC: {data.get('keywordSummary', {}).get('cpc')}",
        f"- Competition: {data.get('keywordSummary', {}).get('competition')}",
        "",
        "## Keyword Ideas",
        "",
    ]
    for item in data.get("keywords", [])[:12]:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('keyword')}: volume {item.get('search_volume')}, "
                f"CPC {item.get('cpc')}, competition {item.get('competition')}"
            )
        else:
            lines.append(f"- {item}")

    lines.extend(["", "## Course Market Signals", ""])
    if top_platform:
        lines.append(f"- Top platform: {top_platform.get('_id')} ({top_platform.get('count'):,} courses)")
    if top_category:
        lines.append(f"- Top category: {top_category.get('_id')} ({top_category.get('count'):,} courses)")
    lines.append(f"- Public summary confirms {summary.get('courses', 0):,} total courses and {summary.get('totalStudents', 0):,} total students.")

    lines.extend(["", "## Course Examples", ""])
    courses = data.get("courses") or []
    if courses:
        for course in courses:
            lines.append(
                f"- {course.get('title')} ({course.get('platform')}) - "
                f"{course.get('students')} students, rating {course.get('rating')}, price {course.get('price')}"
            )
    else:
        lines.append("- Authenticated Eurekaa course rows unavailable; use `--from-chrome` or `ERUKA_API_TOKEN`.")

    lines.extend(["", "## Book Examples", ""])
    for book in data.get("books", []):
        authors = ", ".join(book.get("authors") or [])
        lines.append(f"- {book.get('title')} by {authors or 'Unknown'} ({book.get('publishedDate') or 'n.d.'})")

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
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = path / f"{stamp}-{slugify(keyword)}.md"
    file_path.write_text(markdown, encoding="utf-8")
    return file_path
