from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__
from .chrome_token import ChromeTokenError, load_token_from_chrome


BACKEND_URL = "https://backend.eurekaa.io"
GRAPHQL_URL = "https://wlsnotdhue.execute-api.us-east-1.amazonaws.com/prod/graphql"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_URL = "https://openlibrary.org/search.json"

CONNECT_TIMEOUT = 8.0
READ_TIMEOUT = 25.0
RETRY_TOTAL = 3
RETRY_BACKOFF = 0.5
RETRY_STATUSES = (429, 502, 503, 504)


class ErukaError(RuntimeError):
    pass


def _normalize_eurekaa_books(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    items = data.get("items") or data.get("books") or []
    books = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        volume = item.get("volumeInfo") if isinstance(item.get("volumeInfo"), dict) else item
        books.append({
            "id": item.get("id") or volume.get("id"),
            "title": volume.get("title"),
            "authors": volume.get("authors") or [],
            "publishedDate": volume.get("publishedDate"),
            "categories": volume.get("categories") or [],
            "pageCount": volume.get("pageCount"),
            "averageRating": volume.get("averageRating"),
            "ratingsCount": volume.get("ratingsCount"),
            "description": volume.get("description"),
            "previewLink": volume.get("previewLink"),
            "source": "eurekaa",
        })
    return books


@dataclass
class AuthContext:
    token: str | None
    source: str
    email: str | None = None

    @property
    def present(self) -> bool:
        return bool(self.token)

    def masked(self) -> str:
        if not self.token:
            return "missing"
        return f"present:{len(self.token)} chars via {self.source}"


def resolve_auth(from_chrome: bool = False) -> AuthContext:
    token = os.environ.get("ERUKA_API_TOKEN")
    if token:
        return AuthContext(token=token, source="ERUKA_API_TOKEN")
    if from_chrome:
        try:
            chrome_token = load_token_from_chrome()
        except ChromeTokenError as exc:
            raise ErukaError(str(exc)) from exc
        return AuthContext(token=chrome_token.token, source="Chrome Nuxt store", email=chrome_token.email)
    return AuthContext(token=None, source="none")


class EurekaaClient:
    def __init__(self, timeout: tuple[float, float] | float = (CONNECT_TIMEOUT, READ_TIMEOUT)):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"eruka-cli/{__version__} (research CLI)"
        retry = Retry(
            total=RETRY_TOTAL,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=RETRY_STATUSES,
            allowed_methods=frozenset({"GET", "POST"}),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def post_backend(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{BACKEND_URL}/{path.lstrip('/')}"
        response = self.session.post(url, json=payload, timeout=self.timeout)
        if response.status_code >= 400:
            raise ErukaError(f"Backend request failed: {response.status_code} {response.text[:200]}")
        try:
            return response.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError) as exc:
            raise ErukaError(f"Backend returned non-JSON response from {path}.") from exc

    def graphql(self, query: str, variables: dict[str, Any] | None = None, token: str | None = None) -> dict[str, Any]:
        headers = {"content-type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = self.session.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ErukaError(f"GraphQL transport failed: {response.status_code} {response.text[:200]}")
        try:
            data = response.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError) as exc:
            raise ErukaError("GraphQL endpoint returned a non-JSON response.") from exc
        if data.get("errors"):
            message = "; ".join(str(err.get("message", err)) for err in data["errors"])
            raise ErukaError(f"GraphQL error: {message}")
        if data.get("data") is None:
            raise ErukaError("GraphQL returned no data and no errors; the service may be degraded.")
        return data["data"]

    def course_summary(self, keyword: str) -> dict[str, Any]:
        return self.post_backend("courses-summary", {"args": {"keyword": keyword}})

    def trend(self, keyword: str, country_code: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"keyword": keyword}
        if country_code:
            payload["countryCode"] = country_code
        return self.post_backend("trend", payload)

    def similar_keywords(self, keyword: str) -> list[str]:
        data = self.post_backend("similar-keywords", {"keyword": keyword})
        # Known shapes: {"data": {"keywords": [...]}} and {"keywords": [...]}.
        raw = data.get("data", {}).get("keywords", data.get("keywords", []))
        return [str(item) for item in raw if item]

    def keyword_volume(self, keyword: str) -> dict[str, Any]:
        return self.post_backend("keywords-volume", {"keyword": keyword})

    def search_courses(self, keyword: str, limit: int, page: int, token: str) -> list[dict[str, Any]]:
        query = """
        query SearchCourses($keyword: String, $limit: Int, $page: Int) {
          searchCourses(keyword: $keyword, limit: $limit, page: $page) {
            _id
            title
            url
            category
            subcategory
            topics
            students
            instructors
            rating
            ratingCount
            platform
            price
            badge
            estEarning
            duration
            modulesCount
          }
        }
        """
        data = self.graphql(query, {"keyword": keyword, "limit": limit, "page": page}, token=token)
        return data.get("searchCourses") or []

    def get_course(self, course_id: str, token: str) -> dict[str, Any]:
        query = """
        query GetCourse($id: ID!) {
          getCourse(id: $id) {
            _id
            title
            url
            shortDescription
            description
            category
            subcategory
            topics
            students
            instructors
            rating
            ratingCount
            platform
            price
            badge
            estEarning
            duration
            modulesCount
            modules { title duration }
          }
        }
        """
        data = self.graphql(query, {"id": course_id}, token=token)
        return data.get("getCourse") or {}

    def search_books(self, query: str, limit: int, warnings: list[str] | None = None) -> list[dict[str, Any]]:
        """Search books across Eurekaa, Google Books, and Open Library in order.

        When a source fails or returns nothing and a later source is used, a note is
        appended to `warnings` (if provided) so callers can surface the degradation.
        """
        errors: list[str] = []
        sources = (
            ("Eurekaa GraphQL", self._search_eurekaa_books),
            ("Google Books", self._search_google_books),
            ("Open Library", self._search_open_library),
        )
        empty_sources: list[str] = []
        for index, (name, searcher) in enumerate(sources):
            try:
                books = searcher(query, limit)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                continue
            if books:
                if index > 0 and warnings is not None:
                    skipped = "; ".join(
                        errors + [f"{source} returned no results" for source in empty_sources]
                    )
                    warnings.append(f"Book results served by {name} fallback ({skipped}).")
                return books
            empty_sources.append(name)

        if errors:
            raise ErukaError("Book search failed across all configured sources. " + " | ".join(errors))
        return []

    def _search_eurekaa_books(self, query: str, limit: int) -> list[dict[str, Any]]:
        graph_query = """
        query SearchBooks($text: String!, $startIndex: Int) {
          searchBooks(text: $text, startIndex: $startIndex)
        }
        """
        data = self.graphql(graph_query, {"text": query, "startIndex": 0})
        raw = data.get("searchBooks") or {}
        if not isinstance(raw, dict):
            raise ErukaError(f"Unexpected searchBooks payload type: {type(raw).__name__}")
        return _normalize_eurekaa_books(raw, limit)

    def _search_google_books(self, query: str, limit: int) -> list[dict[str, Any]]:
        try:
            response = self.session.get(
                GOOGLE_BOOKS_URL,
                params={"q": query, "maxResults": max(1, min(limit, 40))},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ErukaError(f"Google Books request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ErukaError(f"Google Books request failed: {response.status_code} {response.text[:200]}")
        try:
            payload = response.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError) as exc:
            raise ErukaError("Google Books returned a non-JSON response.") from exc
        books = []
        for item in payload.get("items", []):
            volume = item.get("volumeInfo", {})
            books.append({
                "id": item.get("id"),
                "title": volume.get("title"),
                "authors": volume.get("authors", []),
                "publishedDate": volume.get("publishedDate"),
                "categories": volume.get("categories", []),
                "pageCount": volume.get("pageCount"),
                "averageRating": volume.get("averageRating"),
                "ratingsCount": volume.get("ratingsCount"),
                "description": volume.get("description"),
                "previewLink": volume.get("previewLink"),
                "source": "google_books",
            })
        return books

    def _search_open_library(self, query: str, limit: int) -> list[dict[str, Any]]:
        try:
            response = self.session.get(
                OPEN_LIBRARY_URL,
                params={"q": query, "limit": max(1, min(limit, 100))},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ErukaError(f"Open Library request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ErukaError(f"Open Library request failed: {response.status_code} {response.text[:200]}")
        try:
            payload = response.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError) as exc:
            raise ErukaError("Open Library returned a non-JSON response.") from exc
        books = []
        for item in payload.get("docs", []):
            books.append({
                "id": item.get("key"),
                "title": item.get("title"),
                "authors": item.get("author_name", []),
                "publishedDate": str(item.get("first_publish_year")) if item.get("first_publish_year") else None,
                "categories": item.get("subject", [])[:5],
                "pageCount": None,
                "averageRating": item.get("ratings_average"),
                "ratingsCount": item.get("ratings_count"),
                "description": None,
                "previewLink": f"https://openlibrary.org{item.get('key')}" if item.get("key") else None,
                "source": "openlibrary",
            })
        return books

    def doctor(self, from_chrome: bool = False) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        try:
            summary = self.course_summary("marketing")
            courses = summary.get("courses")
            if courses is None:
                checks["public_courses_summary"] = {
                    "ok": False,
                    "reason": "response missing 'courses' field; backend shape may have changed",
                }
            else:
                checks["public_courses_summary"] = {"ok": True, "courses": courses}
        except Exception as exc:
            checks["public_courses_summary"] = {"ok": False, "error": str(exc)}

        try:
            data = self.graphql("{ __typename }")
            checks["graphql_introspection"] = {"ok": data.get("__typename") == "Query"}
        except Exception as exc:
            checks["graphql_introspection"] = {"ok": False, "error": str(exc)}

        try:
            warnings: list[str] = []
            books = self.search_books("digital marketing", 1, warnings=warnings)
            source = books[0].get("source") if books else None
            check: dict[str, Any] = {"ok": bool(books), "count": len(books), "source": source}
            if warnings:
                check["warnings"] = warnings
            checks["book_search"] = check
        except Exception as exc:
            checks["book_search"] = {"ok": False, "error": str(exc)}

        try:
            trend = self.trend("marketing")
            points = trend.get("trend") or {}
            checks["trend"] = {"ok": bool(points), "points": len(points)}
        except Exception as exc:
            checks["trend"] = {"ok": False, "error": str(exc)}

        try:
            auth = resolve_auth(from_chrome=from_chrome)
            # Email is intentionally omitted here: doctor output often lands in CI logs.
            checks["auth"] = {"ok": auth.present, "source": auth.source, "token": auth.masked()}
        except Exception as exc:
            checks["auth"] = {"ok": False, "source": "Chrome Nuxt store", "error": str(exc)}

        return checks
