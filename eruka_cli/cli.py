from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

import requests

from . import __version__
from .eurekaa_client import ErukaError, EurekaaClient, resolve_auth
from .models import calculate_opportunity, summarize_trend
from .report import (
    compact_book,
    compact_course,
    emit_json,
    fmt_value,
    format_book_row,
    format_course_row,
    render_brief_markdown,
    render_summary_markdown,
    render_trend_markdown,
    write_brief,
)

EXIT_OK = 0
EXIT_ERROR = 2
EXIT_INTERRUPTED = 130


def _print(data: str) -> None:
    sys.stdout.write(data)
    if not data.endswith("\n"):
        sys.stdout.write("\n")


def _warn(message: str) -> None:
    sys.stderr.write(f"eruka: warning: {message}\n")


def dedupe_keyword_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop alias rows that share identical (volume, cpc, competition) metrics.

    The keyword API returns alias groups ("digital marketing", "dijital marketing", ...)
    with byte-identical metrics; only the first (canonical) row is informative. Rows
    with any missing metric are never deduped.
    """
    seen: set[tuple[Any, Any, Any]] = set()
    result = []
    for item in items:
        key = (item.get("search_volume"), item.get("cpc"), item.get("competition"))
        if all(value is not None for value in key):
            if key in seen:
                continue
            seen.add(key)
        result.append(item)
    return result


def _keyword_items(volume: dict[str, Any], limit: int, dedupe: bool = True) -> list[dict[str, Any]]:
    keywords = volume.get("volumes") or volume.get("keywords") or volume.get("data", {}).get("keywords") or []
    if not isinstance(keywords, list):
        return []
    items = [item for item in keywords if isinstance(item, dict)]
    if items and dedupe:
        items = dedupe_keyword_items(items)
    return items[:limit]


def _keyword_summary(volume: dict[str, Any]) -> dict[str, Any]:
    summary = volume.get("summary") or volume.get("data", {}).get("summary") or {}
    return summary if isinstance(summary, dict) else {}


def _warn_on_unrecognized_volume_shape(volume: dict[str, Any]) -> None:
    if volume and not _keyword_summary(volume) and not _keyword_items(volume, 1, dedupe=False):
        _warn(f"keyword volume response had an unrecognized shape (keys: {sorted(volume.keys())[:6]}); treating as no data")


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
    return EXIT_OK if ok else EXIT_ERROR


def command_auth_status(args: argparse.Namespace) -> int:
    auth = resolve_auth(from_chrome=args.from_chrome)
    payload = {"ok": auth.present, "source": auth.source, "email": auth.email, "token": auth.masked()}
    _print(emit_json(payload) if args.json else f"auth {payload['token']} email={auth.email or '-'}")
    return EXIT_OK if auth.present else EXIT_ERROR


def command_summary(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    summary = client.course_summary(args.keyword)
    volume = client.keyword_volume(args.keyword)
    _warn_on_unrecognized_volume_shape(volume)
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
    return EXIT_OK


def command_keyword(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    volume = client.keyword_volume(args.keyword)
    _warn_on_unrecognized_volume_shape(volume)
    similar = client.similar_keywords(args.keyword)
    payload = {
        "keyword": args.keyword,
        "summary": _keyword_summary(volume),
        "keywords": _keyword_items(volume, args.limit, dedupe=not args.all),
        "similar": similar[: args.limit],
    }
    if args.json:
        _print(emit_json(payload))
    else:
        summary = payload["summary"]
        _print(f"# Keyword Research: {args.keyword}\n")
        _print(f"- Search volume: {fmt_value(summary.get('search_volume'))}")
        _print(f"- CPC: {fmt_value(summary.get('cpc'))}")
        _print(f"- Competition: {fmt_value(summary.get('competition'))}\n")
        _print("## Related Keywords")
        for item in payload["keywords"]:
            _print(
                f"- {item.get('keyword')}: volume {fmt_value(item.get('search_volume'))}, "
                f"CPC {fmt_value(item.get('cpc'))}"
            )
        if payload["similar"]:
            _print("\n## Similar")
            for item in payload["similar"]:
                _print(f"- {item}")
    return EXIT_OK


def command_trend(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    data = client.trend(args.keyword, country_code=args.country)
    points = data.get("trend") or {}
    momentum = summarize_trend(points, window=args.window)
    payload = {
        "keyword": args.keyword,
        "country": args.country,
        "momentum": momentum,
        "trend": points,
    }
    if args.json:
        _print(emit_json(payload))
    else:
        _print(render_trend_markdown(args.keyword, momentum, country=args.country))
    # An empty series is a valid answer ("no recorded interest"), not an error;
    # JSON consumers should branch on momentum.ok instead of the exit code.
    if not momentum.get("ok"):
        _warn(f"no trend history recorded for '{args.keyword}'")
    return EXIT_OK


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
            _print(format_course_row(course))
    return EXIT_OK


def command_course(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    auth = resolve_auth(from_chrome=args.from_chrome)
    if not auth.token:
        raise ErukaError("Course inspection requires ERUKA_API_TOKEN or --from-chrome.")
    course = client.get_course(args.course_id, auth.token)
    _print(emit_json(course))
    return EXIT_OK


def command_book_search(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    warnings: list[str] = []
    books = [compact_book(book) for book in client.search_books(args.query, args.limit, warnings=warnings)]
    for warning in warnings:
        _warn(warning)
    payload = {"query": args.query, "books": books, "warnings": warnings}
    if args.json:
        _print(emit_json(payload))
    else:
        _print(f"# Book Research: {args.query}\n")
        for book in books:
            _print(format_book_row(book))
    return EXIT_OK


def command_brief(args: argparse.Namespace) -> int:
    client = EurekaaClient()
    summary = client.course_summary(args.keyword)
    volume = client.keyword_volume(args.keyword)
    _warn_on_unrecognized_volume_shape(volume)
    keyword_summary = _keyword_summary(volume)
    score = calculate_opportunity(summary, keyword_summary)

    trend_momentum: dict[str, Any] | None = None
    try:
        trend_points = client.trend(args.keyword).get("trend") or {}
        trend_momentum = summarize_trend(trend_points)
    except (ErukaError, requests.RequestException, OSError) as exc:
        _warn(f"trend data unavailable: {exc}")

    courses: list[dict[str, Any]] = []
    auth_warning = None
    try:
        auth = resolve_auth(from_chrome=args.from_chrome)
        if auth.token:
            courses = [compact_course(row) for row in client.search_courses(args.keyword, args.limit, 1, auth.token)]
        else:
            auth_warning = "No token available; authenticated course examples skipped."
    except (ErukaError, requests.RequestException, OSError) as exc:
        auth_warning = str(exc)

    book_warnings: list[str] = []
    books = [compact_book(book) for book in client.search_books(args.keyword, args.limit, warnings=book_warnings)]
    for warning in book_warnings:
        _warn(warning)
    payload = {
        "keyword": args.keyword,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "keywordSummary": keyword_summary,
        "keywords": _keyword_items(volume, args.limit * 3),
        "opportunity": score.__dict__,
        "trend": trend_momentum,
        "courses": courses,
        "books": books,
        "authWarning": auth_warning,
        "bookWarnings": book_warnings,
    }

    if args.json:
        output = emit_json(payload)
        _print(output)
        return EXIT_OK

    markdown = render_brief_markdown(payload)
    if args.out:
        path = write_brief(args.out, args.keyword, markdown)
        _print(str(path))
    else:
        _print(markdown)
    return EXIT_OK


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
    keyword.add_argument("--all", action="store_true", help="Keep alias keyword rows with identical metrics.")
    keyword.add_argument("--json", action="store_true")
    keyword.set_defaults(func=command_keyword)

    trend = sub.add_parser("trend", help="Weekly search-interest trend and momentum for a keyword.")
    trend.add_argument("keyword")
    trend.add_argument("--country", help="Two-letter country code (e.g. US, JP); default worldwide.")
    trend.add_argument("--window", type=int, default=12, help="Momentum window in weeks (default 12).")
    trend.add_argument("--json", action="store_true")
    trend.set_defaults(func=command_trend)

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
        return EXIT_ERROR
    except requests.RequestException as exc:
        sys.stderr.write(f"eruka: network error: {exc}\n")
        return EXIT_ERROR
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"eruka: invalid JSON from a data source: {exc}\n")
        return EXIT_ERROR
    except OSError as exc:
        sys.stderr.write(f"eruka: system error: {exc}\n")
        return EXIT_ERROR
    except KeyboardInterrupt:
        sys.stderr.write("eruka: interrupted\n")
        return EXIT_INTERRUPTED
