from __future__ import annotations

from dataclasses import dataclass
from math import log10
from typing import Any


@dataclass(frozen=True)
class OpportunityScore:
    score: int
    demand_score: float
    competition_score: float
    trend_score: float
    keyword_score: float
    rationale: str


def summarize_trend(points: dict[str, Any], window: int = 12) -> dict[str, Any]:
    """Summarize a Eurekaa/Google-Trends weekly interest dict {date: value}.

    Returns recent/prior window averages, momentum percent, latest and peak points.
    None/non-numeric values are treated as gaps and skipped.
    """
    series = []
    for date in sorted(points):
        value = points[date]
        if isinstance(value, (int, float)):
            series.append((date, float(value)))
    if not series:
        return {"ok": False, "weeks": 0}

    values = [value for _, value in series]
    recent = values[-window:]
    prior = values[-2 * window:-window] or recent
    recent_avg = sum(recent) / len(recent)
    prior_avg = sum(prior) / len(prior)
    momentum = ((recent_avg - prior_avg) / prior_avg) if prior_avg else 0.0
    peak_date, peak_value = max(series, key=lambda item: item[1])
    return {
        "ok": True,
        "weeks": len(series),
        "latestDate": series[-1][0],
        "latestValue": series[-1][1],
        "recentAvg": round(recent_avg, 1),
        "priorAvg": round(prior_avg, 1),
        "momentum": round(momentum, 4),
        "peakDate": peak_date,
        "peakValue": peak_value,
    }


def _trend_delta(monthly_searches: list[list[Any]] | None) -> float:
    if not monthly_searches or len(monthly_searches) < 2:
        return 0.0
    first = monthly_searches[0][1] or 0
    last = monthly_searches[-1][1] or 0
    if not first:
        return 0.0
    return (float(last) - float(first)) / float(first)


def calculate_opportunity(summary: dict[str, Any], keyword_summary: dict[str, Any] | None = None) -> OpportunityScore:
    # `courses` absent/None means the data source failed to report, which must not be
    # confused with a genuine zero-course market (an apparent green-field opportunity).
    course_data_missing = summary.get("courses") is None and summary.get("totalStudents") is None
    courses = max(float(summary.get("courses") or 0), 0.0)
    students = max(float(summary.get("totalStudents") or 0), 0.0)
    search_volume = 0.0
    trend_delta = 0.0

    if keyword_summary:
        search_volume = max(float(keyword_summary.get("search_volume") or 0), 0.0)
        trend_delta = _trend_delta(keyword_summary.get("monthly_searches"))

    demand_score = min(log10(students + 1) / 8.0, 1.0)
    keyword_score = min(log10(search_volume + 1) / 6.0, 1.0) if search_volume else 0.0

    # Lower course saturation is better, but empty markets are not automatically good.
    if course_data_missing:
        competition_score = 0.0
    elif courses <= 0:
        competition_score = 0.15
    else:
        students_per_course = students / courses if students else 0.0
        competition_score = min(log10(students_per_course + 1) / 5.0, 1.0)

    trend_score = max(min(0.5 + trend_delta, 1.0), 0.0)
    raw = (0.35 * demand_score) + (0.30 * competition_score) + (0.20 * keyword_score) + (0.15 * trend_score)
    score = int(round(raw * 100))

    course_part = (
        "course data unavailable"
        if course_data_missing
        else f"{int(courses):,} courses, {int(students):,} students"
    )
    rationale = (
        f"{course_part}, "
        f"{int(search_volume):,} monthly searches, trend delta {trend_delta:+.1%}"
    )
    return OpportunityScore(
        score=max(0, min(score, 100)),
        demand_score=demand_score,
        competition_score=competition_score,
        trend_score=trend_score,
        keyword_score=keyword_score,
        rationale=rationale,
    )
