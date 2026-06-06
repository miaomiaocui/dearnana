"""Pure-Python ranking engine. No LLM calls — just math."""

import bisect
import math

from dearnana.config import (
    ABUSE_PENALTY,
    ABUSE_PENALTY_VULNERABLE,
    CONDITION_MATCH_WEIGHT,
    DEFAULT_RADIUS_MILES,
    MIN_BENCHMARK_SAMPLES,
    NATIONAL_MEDIAN_RN_TURNOVER,
    NATIONAL_MEDIAN_TOTAL_TURNOVER,
    NATIONAL_TOTAL_NURSE_HOURS_PER_RESIDENT_DAY,
    WEIGHTS,
)
from dearnana.condition import MEASURE_LABELS
from dearnana.models import Facility, RankedFacility

NEUTRAL_SCORE = 50.0  # used whenever data is missing for a component


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in miles between two lat/lng points."""
    R = 3959  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _score_rating(rating: int) -> float:
    """Convert a 1-5 star rating to 0-100. Missing/unrated (0) is neutral."""
    return (rating / 5) * 100 if rating > 0 else NEUTRAL_SCORE


def _score_staffing_quality(facility: Facility) -> float:
    """Blend of staffing star rating and actual nurse hours vs benchmark.

    Only available parts contribute; both missing -> neutral.
    """
    parts = []
    if facility.staffing_rating > 0:
        parts.append(((facility.staffing_rating / 5) * 100, 0.6))
    if facility.total_nurse_staffing_hours > 0:
        benchmark = NATIONAL_TOTAL_NURSE_HOURS_PER_RESIDENT_DAY
        hours_score = min((facility.total_nurse_staffing_hours / benchmark) * 100, 100)
        parts.append((hours_score, 0.4))
    if not parts:
        return NEUTRAL_SCORE
    total_weight = sum(w for _, w in parts)
    return sum(score * w for score, w in parts) / total_weight


def _score_staff_stability(facility: Facility) -> float:
    """Lower turnover = higher score. Inverse of national median."""
    scores = []
    if facility.total_nursing_turnover is not None:
        # 0% turnover = 100, national median = 50, 100%+ = 0
        ratio = facility.total_nursing_turnover / NATIONAL_MEDIAN_TOTAL_TURNOVER
        scores.append(max(0, 100 * (1 - ratio / 2)))
    if facility.rn_turnover is not None:
        ratio = facility.rn_turnover / NATIONAL_MEDIAN_RN_TURNOVER
        scores.append(max(0, 100 * (1 - ratio / 2)))
    return sum(scores) / len(scores) if scores else NEUTRAL_SCORE


def _score_penalty_history(facility: Facility) -> float:
    """Penalty-free = 100. Deductions by count and fine amounts."""
    if facility.number_of_penalties == 0:
        return 100
    # Each penalty costs 15 points, each $10K in fines costs 5 points
    penalty_deduction = facility.number_of_penalties * 15
    fine_deduction = (facility.total_fines_dollars / 10_000) * 5
    return max(0, 100 - penalty_deduction - fine_deduction)


def _score_distance(distance_miles: float, radius: float) -> float:
    """Linear decay: 100 at 0 miles, 0 at radius."""
    if distance_miles >= radius:
        return 0
    return 100 * (1 - distance_miles / radius)


def _score_safety(facility: Facility) -> float:
    """Sprinkler coverage check. Unknown -> neutral."""
    if facility.sprinkler_systems == "Yes":
        return 100
    if facility.sprinkler_systems == "Partial":
        return 50
    if facility.sprinkler_systems == "No":
        return 0
    return NEUTRAL_SCORE


def build_weights(condition_active: bool) -> dict[str, float]:
    """Composite weights, renormalized when the condition component is active."""
    if not condition_active:
        return dict(WEIGHTS)
    scaled = {k: v * (1 - CONDITION_MATCH_WEIGHT) for k, v in WEIGHTS.items()}
    scaled["condition_match"] = CONDITION_MATCH_WEIGHT
    return scaled


def compute_measure_benchmarks(
    mds: dict[str, dict[str, float]],
) -> dict[str, list[float]]:
    """Sorted per-measure value lists across the state, for percentile ranks."""
    benchmarks: dict[str, list[float]] = {}
    for facility_measures in mds.values():
        for code, value in facility_measures.items():
            benchmarks.setdefault(code, []).append(value)
    for values in benchmarks.values():
        values.sort()
    return benchmarks


def score_condition_match(
    facility_mds: dict[str, float],
    measure_weights: dict[str, float],
    benchmarks: dict[str, list[float]],
) -> tuple[float, list[dict]]:
    """Score a facility's relevant MDS measures against state percentiles.

    Lower measure values are better for all tracked measures, so the score is
    100 * (1 - percentile). Missing data or thin benchmarks score neutral.
    """
    weighted_sum = 0.0
    total_weight = 0.0
    details: list[dict] = []
    for code, weight in measure_weights.items():
        values = benchmarks.get(code, [])
        facility_value = facility_mds.get(code)
        if facility_value is None or len(values) < MIN_BENCHMARK_SAMPLES:
            score = NEUTRAL_SCORE
            percentile = None
            median = None
        else:
            rank = bisect.bisect_left(values, facility_value)
            percentile = rank / len(values)
            score = 100 * (1 - percentile)
            median = values[len(values) // 2]
        weighted_sum += score * weight
        total_weight += weight
        details.append(
            {
                "code": code,
                "label": MEASURE_LABELS.get(code, code),
                "value": facility_value,
                "state_median": median,
                "percentile": round(percentile, 3) if percentile is not None else None,
                "weight": round(weight, 3),
                "score": round(score, 1),
            }
        )
    details.sort(key=lambda d: -d["weight"])
    final = weighted_sum / total_weight if total_weight > 0 else NEUTRAL_SCORE
    return final, details


def compute_chain_warnings(facility: Facility) -> list[str]:
    """User-facing warnings derived from chain/ownership context."""
    warnings = []
    if (
        facility.chain_avg_overall is not None
        and facility.chain_avg_overall <= 2.5
        and facility.chain_name
    ):
        count = facility.chain_facility_count or 0
        warnings.append(
            f"Part of {facility.chain_name} ({count} facilities, "
            f"chain avg {facility.chain_avg_overall:.1f}/5 — below average)"
        )
    if facility.changed_ownership_12mo:
        warnings.append("Ownership changed within the last 12 months")
    if facility.special_focus_status:
        warnings.append(f"CMS Special Focus status: {facility.special_focus_status}")
    return warnings


def compute_composite_score(
    facility: Facility,
    distance_miles: float,
    radius: float,
    condition_score: float | None = None,
    vulnerable: bool = False,
) -> tuple[float, dict[str, float]]:
    """Compute weighted composite score (0-100) with breakdown.

    When condition_score is provided, base weights are scaled by
    (1 - CONDITION_MATCH_WEIGHT) and a condition_match component is added.
    """
    components = {
        "overall_rating": _score_rating(facility.overall_rating),
        "health_inspection": _score_rating(facility.health_inspection_rating),
        "staffing_quality": _score_staffing_quality(facility),
        "staff_stability": _score_staff_stability(facility),
        "penalty_history": _score_penalty_history(facility),
        "distance": _score_distance(distance_miles, radius),
        "safety": _score_safety(facility),
    }
    if condition_score is not None:
        components["condition_match"] = condition_score

    weights = build_weights(condition_active=condition_score is not None)
    weighted = sum(components[k] * weights[k] for k in weights)

    # Abuse flag is a near-disqualifying penalty, heavier for vulnerable needs
    if facility.abuse_icon:
        penalty = ABUSE_PENALTY_VULNERABLE if vulnerable else ABUSE_PENALTY
        weighted = max(0, weighted - penalty)

    return round(weighted, 1), {k: round(v, 1) for k, v in components.items()}


def rank_facilities(
    facilities: list[Facility],
    user_lat: float,
    user_lng: float,
    radius_miles: float = DEFAULT_RADIUS_MILES,
    top_n: int | None = None,
    condition_scores: dict[str, tuple[float, list[dict]]] | None = None,
    vulnerable: bool = False,
) -> list[RankedFacility]:
    """Filter by distance, score, and rank facilities.

    condition_scores maps ccn -> (condition_match score, per-measure details);
    when provided, the condition component participates in the composite.

    Returns facilities sorted by composite score descending.
    """
    ranked = []
    for f in facilities:
        if f.latitude is None or f.longitude is None:
            continue
        dist = haversine(user_lat, user_lng, f.latitude, f.longitude)
        if dist > radius_miles:
            continue
        condition_score = None
        condition_details = None
        if condition_scores is not None:
            condition_score, condition_details = condition_scores.get(
                f.ccn, (NEUTRAL_SCORE, [])
            )
        score, breakdown = compute_composite_score(
            f, dist, radius_miles, condition_score=condition_score, vulnerable=vulnerable
        )
        ranked.append(
            RankedFacility(
                facility=f,
                distance_miles=round(dist, 1),
                composite_score=score,
                score_breakdown=breakdown,
                chain_warnings=compute_chain_warnings(f),
                condition_details=condition_details,
            )
        )

    ranked.sort(key=lambda r: r.composite_score, reverse=True)

    if top_n is not None:
        return ranked[:top_n]
    return ranked
