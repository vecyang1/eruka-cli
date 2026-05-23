from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .eurekaa_client import ErukaError, EurekaaClient, resolve_auth
from .models import calculate_opportunity
from .report import (
    compact_book,
    compact_course,
    emit_json,
    render_brief_markdown,
    render_summary_markdown,
    write_brief,
)


def _print(data: str) -> None:
    sys.stdout.write(data)
    if not data.endswith("\n"):
        sys.stdout.write("\n")


def _keyword_items(volume: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    keywords = volume.get("volumes") or volume.get("keywords") or volume.get("data", {}).get("keywords") or []
    if not isinstance(keywords, list):
        return []
    return [item for item in keywords if isinstance(item, dict)][:limit]


def _keyword_summary(volume: dict[str, Any]) -> dict[str, Any]:
    summary = volume.get("summary") or volume.get("data", {}).get("summary") or {}
    return summary if isinstance(summary, dict) else {}


def command_doctor(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    checks = client.doctor(from_chrome=args.from_chrome)
    ok = all(check.get("ok") for name, check in checks.items() if name != "auth")
    if args.from_chrome:
        ok = ok and checks.get("auth", {}).get("ok", False)
    if args.json:
        _print(emit_json({"ok": ok, "checks": checks}))
    else:
        for name, check in checks.items():
            status = "ok" if check.get("ok") else "warn"
            detail = ", ".join(f"{k}={v}" for k, v in check.items() if k != "ok")
            _print(f"{status:4} {name}: {detail}")
    return 0 if ok else (2 if args.from_chrome else 0)


def command_auth_status(args: argparse.Namespace) -> int:
    auth = resolve_auth(from_chrome=args.from_chrome)
    payload = {"ok": auth.present, "source": auth.source, "email": auth.email, "token": auth.masked()}
    _print(emit_json(payload) if args.json else f"auth {payload['token']} email={auth.email or '-'}")
    return 0 if auth.present else 2


def command_summary(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    summary = client.course_summary(args.keyword)
    volume = client.keyword_volume(args.keyword)
    score = calculate_opportunity(summary, _keyword_summary(volume))
    payload = {
        "keyword": args.keyword,
        "summary": summary,
        "keywordSummary": _keyword_summary(volume),
        "opportunity": score.__dict__,
    }
    if args.json:
        _print(emit_json(payload))
    else:
        _print(render_summary_markdown(args.keyword, summary, score))
    return 0


def command_keyword(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    volume = client.keyword_volume(args.keyword)
    similar = client.similar_keywords(args.keyword)
    payload = {
        "keyword": args.keyword,
        "summary": _keyword_summary(volume),
        "keywords": _keyword_items(volume, args.limit),
        "similar": similar[: args.limit],
    }
    if args.json:
        _print(emit_json(payload))
    else:
        summary = payload["summary"]
        _print(f"# Keyword Research: {args.keyword}\n")
        _print(f"- Search volume: {summary.get('search_volume')}")
        _print(f"- CPC: {summary.get('cpc')}")
        _print(f"- Competition: {summary.get('competition')}\n")
        _print("## Related Keywords")
        for item in payload["keywords"]:
            _print(f"- {item.get('keyword')}: volume {item.get('search_volume')}, CPC {item.get('cpc')}")
        if payload["similar"]:
            _print("\n## Similar")
            for item in payload["similar"]:
                _print(f"- {item}")
    return 0


def command_courses(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    auth = resolve_auth(from_chrome=args.from_chrome)
    if not auth.token:
        raise ErukaError("Detailed course search requires ERUKA_API_TOKEN or --from-chrome.")
    rows = client.search_courses(args.keyword, args.limit, args.page, auth.token)
    payload = {"keyword": args.keyword, "auth": auth.masked(), "courses": [compact_course(row) for row in rows]}
    if args.json:
        _print(emit_json(payload))
    else:
        _print(f"# Courses: {args.keyword}\n")
        for course in payload["courses"]:
            _print(
                f"- {course['title']} ({course['platform']}) - "
                f"{course['students']} students, rating {course['rating']}, price {course['price']}"
            )
    return 0


def command_course(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    auth = resolve_auth(from_chrome=args.from_chrome)
    if not auth.token:
        raise ErukaError("Course inspection requires ERUKA_API_TOKEN or --from-chrome.")
    course = client.get_course(args.course_id, auth.token)
    _print(emit_json(course))
    return 0


def command_book_search(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    books = [compact_book(book) for book in client.search_books(args.query, args.limit)]
    payload = {"query": args.query, "books": books}
    if args.json:
        _print(emit_json(payload))
    else:
        _print(f"# Book Research: {args.query}\n")
        for book in books:
            authors = ", ".join(book.get("authors") or [])
            _print(f"- {book.get('title')} by {authors or 'Unknown'} ({book.get('publishedDate') or 'n.d.'})")
    return 0


def command_brief(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    summary = client.course_summary(args.keyword)
    volume = client.keyword_volume(args.keyword)
    keyword_summary = _keyword_summary(volume)
    score = calculate_opportunity(summary, keyword_summary)

    courses: list[dict[str, Any]] = []
    auth_warning = None
    try:
        auth = resolve_auth(from_chrome=args.from_chrome)
        if auth.token:
            courses = [compact_course(row) for row in client.search_courses(args.keyword, args.limit, 1, auth.token)]
        else:
            auth_warning = "No token available; authenticated course examples skipped."
    except Exception as exc:
        auth_warning = str(exc)

    books = [compact_book(book) for book in client.search_books(args.keyword, args.limit)]
    payload = {
        "keyword": args.keyword,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "keywordSummary": keyword_summary,
        "keywords": _keyword_items(volume, args.limit * 3),
        "opportunity": score.__dict__,
        "courses": courses,
        "books": books,
        "authWarning": auth_warning,
    }

    if args.json:
        output = emit_json(payload)
        _print(output)
        return 0

    markdown = render_brief_markdown(payload)
    if args.out:
        path = write_brief(args.out, args.keyword, markdown)
        _print(str(path))
    else:
        _print(markdown)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eruka", description="Agent-friendly course and market research CLI.")
    parser.add_argument("--version", action="version", version=f"eruka {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check public endpoints, GraphQL, book search, and optional Chrome auth.")
    doctor.add_argument("--from-chrome", action="store_true", help="Require token access from active Chrome Eurekaa tab.")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=command_doctor)

    auth = sub.add_parser("auth-status", help="Check token availability without printing token values.")
    auth.add_argument("--from-chrome", action="store_true")
    auth.add_argument("--json", action="store_true")
    auth.set_defaults(func=command_auth_status)

    summary = sub.add_parser("summary", help="Public course demand summary and opportunity score.")
    summary.add_argument("keyword")
    summary.add_argument("--json", action="store_true")
    summary.set_defaults(func=command_summary)

    keyword = sub.add_parser("keyword", help="Keyword volume, CPC, competition, and related ideas.")
    keyword.add_argument("keyword")
    keyword.add_argument("--limit", type=int, default=10)
    keyword.add_argument("--json", action="store_true")
    keyword.set_defaults(func=command_keyword)

    courses = sub.add_parser("courses", help="Authenticated detailed course rows.")
    courses.add_argument("keyword")
    courses.add_argument("--limit", type=int, default=5)
    courses.add_argument("--page", type=int, default=1)
    courses.add_argument("--from-chrome", action="store_true")
    courses.add_argument("--json", action="store_true")
    courses.set_defaults(func=command_courses)

    course = sub.add_parser("course", help="Authenticated course inspection by id.")
    course.add_argument("course_id")
    course.add_argument("--from-chrome", action="store_true")
    course.set_defaults(func=command_course)

    books = sub.add_parser("book-search", help="Public book research across Eurekaa, Google Books, and Open Library.")
    books.add_argument("query")
    books.add_argument("--limit", type=int, default=5)
    books.add_argument("--json", action="store_true")
    books.set_defaults(func=command_book_search)

    brief = sub.add_parser("brief", help="Compound market/course/book/keyword research brief.")
    brief.add_argument("keyword")
    brief.add_argument("--limit", type=int, default=5)
    brief.add_argument("--from-chrome", action="store_true")
    brief.add_argument("--out", help="Directory to write a Markdown brief.")
    brief.add_argument("--json", action="store_true")
    brief.set_defaults(func=command_brief)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ErukaError as exc:
        sys.stderr.write(f"eruka: {exc}\n")
        return 2
