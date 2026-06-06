"""Unit tests for the dearnana ranking engine."""

import pytest

from dearnana.models import Facility
from dearnana.ranker import (
    haversine,
    _score_rating,
    _score_safety,
    _score_staffing_quality,
    _score_penalty_history,
    _score_staff_stability,
    build_weights,
    compute_chain_warnings,
    compute_composite_score,
    compute_measure_benchmarks,
    rank_facilities,
    score_condition_match,
)


def test_haversine_zero_distance():
    """Same point should return distance of 0.0."""
    result = haversine(47.6062, -122.3321, 47.6062, -122.3321)
    assert result == 0.0


def test_haversine_seattle_to_bellevue():
    """Seattle to Bellevue is roughly 7 miles."""
    dist = haversine(47.6062, -122.3321, 47.6101, -122.2015)
    assert 5 <= dist <= 10, f"Expected 5-10 miles but got {dist:.2f}"


def test_compute_composite_score_range(sample_facility):
    """Composite score must fall between 0 and 100."""
    score, breakdown = compute_composite_score(sample_facility, distance_miles=5, radius=50)
    assert 0 <= score <= 100, f"Score {score} out of range"
    assert isinstance(breakdown, dict)
    assert len(breakdown) > 0


def test_abuse_icon_reduces_score(sample_facility):
    """Facility flagged for abuse should score at least 50 points lower."""
    clean_score, _ = compute_composite_score(sample_facility, distance_miles=5, radius=50)

    # Build an abusive-icon version
    abusive_facility = sample_facility.model_copy(update={"abuse_icon": True})
    abusive_score, _ = compute_composite_score(abusive_facility, distance_miles=5, radius=50)

    assert clean_score - abusive_score >= 50, (
        f"Expected >=50 point reduction but only got {clean_score - abusive_score:.1f}"
    )


def test_rank_facilities_filters_by_radius():
    """Only facilities inside the radius should appear in results."""
    # Seattle (user location)
    user_lat, user_lng = 47.6062, -122.3321

    inside = Facility(
        ccn="111111",
        name="Close Facility",
        address="Near St",
        city="Bellevue",
        state="WA",
        zip_code="98004",
        latitude=47.6101,
        longitude=-122.2015,  # ~7 miles from Seattle
    )
    outside = Facility(
        ccn="222222",
        name="Far Facility",
        address="Far Rd",
        city="Olympia",
        state="WA",
        zip_code="98501",
        latitude=47.0379,
        longitude=-122.9007,  # ~55 miles from Seattle
    )

    results = rank_facilities([inside, outside], user_lat, user_lng, radius_miles=25)
    ccns = [r.facility.ccn for r in results]

    assert "111111" in ccns, "Inside facility should be returned"
    assert "222222" not in ccns, "Outside facility should be filtered out"


def test_rank_facilities_sorts_descending():
    """Results must be sorted by composite_score in descending order."""
    user_lat, user_lng = 47.6062, -122.3321

    # Three facilities with different quality scores, all nearby
    high = Facility(
        ccn="A", name="High", address="A", city="Seattle", state="WA", zip_code="98001",
        latitude=47.61, longitude=-122.33, overall_rating=5, health_inspection_rating=5,
        staffing_rating=5, sprinkler_systems="Yes", number_of_penalties=0,
    )
    mid = Facility(
        ccn="B", name="Mid", address="B", city="Seattle", state="WA", zip_code="98001",
        latitude=47.61, longitude=-122.33, overall_rating=3, health_inspection_rating=3,
        staffing_rating=3, sprinkler_systems="Partial", number_of_penalties=1,
        total_fines_dollars=5000.0,
    )
    low = Facility(
        ccn="C", name="Low", address="C", city="Seattle", state="WA", zip_code="98001",
        latitude=47.61, longitude=-122.33, overall_rating=1, health_inspection_rating=1,
        staffing_rating=1, sprinkler_systems="No", number_of_penalties=5,
        total_fines_dollars=50000.0,
    )

    results = rank_facilities([mid, low, high], user_lat, user_lng, radius_miles=25)

    assert len(results) == 3
    scores = [r.composite_score for r in results]
    assert scores == sorted(scores, reverse=True), f"Expected descending order but got {scores}"


def test_penalty_history_zero_penalties():
    """A facility with 0 penalties should receive a perfect penalty score of 100."""
    facility = Facility(
        ccn="X", name="X", address="X", city="X", state="WA", zip_code="00000",
        number_of_penalties=0,
        total_fines_dollars=0.0,
    )
    score = _score_penalty_history(facility)
    assert score == 100


def test_staff_stability_no_data():
    """A facility with no turnover data should return neutral score of 50."""
    facility = Facility(
        ccn="X", name="X", address="X", city="X", state="WA", zip_code="00000",
        total_nursing_turnover=None,
        rn_turnover=None,
    )
    score = _score_staff_stability(facility)
    assert score == 50


def _bare_facility(**overrides) -> Facility:
    base = dict(ccn="X", name="X", address="X", city="X", state="WA", zip_code="00000")
    base.update(overrides)
    return Facility(**base)


class TestMissingDataNeutrality:
    """Missing data components score neutral (50), per the README contract."""

    def test_unrated_is_neutral(self):
        assert _score_rating(0) == 50

    def test_rated_unchanged(self):
        assert _score_rating(5) == 100
        assert _score_rating(1) == 20

    def test_staffing_both_missing(self):
        assert _score_staffing_quality(_bare_facility()) == 50

    def test_staffing_stars_only(self):
        f = _bare_facility(staffing_rating=5)
        assert _score_staffing_quality(f) == 100

    def test_staffing_hours_only(self):
        f = _bare_facility(total_nurse_staffing_hours=4.1)
        assert _score_staffing_quality(f) == 100

    def test_safety_unknown_is_neutral(self):
        assert _score_safety(_bare_facility()) == 50

    def test_safety_no_is_zero(self):
        assert _score_safety(_bare_facility(sprinkler_systems="No")) == 0


class TestBuildWeights:
    def test_base_weights_sum_to_one(self):
        assert abs(sum(build_weights(False).values()) - 1.0) < 1e-9

    def test_condition_weights_sum_to_one(self):
        weights = build_weights(True)
        assert "condition_match" in weights
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestConditionMatch:
    BENCHMARKS = {"481": [float(v) for v in range(5, 105)]}  # 100 values, 5..104
    WEIGHTS = {"481": 1.0}

    def test_best_facility_scores_high(self):
        score, details = score_condition_match({"481": 1.0}, self.WEIGHTS, self.BENCHMARKS)
        assert score == 100
        assert details[0]["code"] == "481"

    def test_worst_facility_scores_low(self):
        score, _ = score_condition_match({"481": 999.0}, self.WEIGHTS, self.BENCHMARKS)
        assert score == 0

    def test_missing_value_is_neutral(self):
        score, details = score_condition_match({}, self.WEIGHTS, self.BENCHMARKS)
        assert score == 50
        assert details[0]["value"] is None

    def test_thin_benchmark_is_neutral(self):
        thin = {"481": [1.0, 2.0, 3.0]}  # below MIN_BENCHMARK_SAMPLES
        score, _ = score_condition_match({"481": 1.0}, self.WEIGHTS, thin)
        assert score == 50

    def test_benchmarks_built_sorted(self):
        mds = {"a": {"481": 9.0}, "b": {"481": 3.0}, "c": {"481": 6.0}}
        benchmarks = compute_measure_benchmarks(mds)
        assert benchmarks["481"] == [3.0, 6.0, 9.0]


class TestConditionInComposite:
    def test_condition_score_shifts_ranking(self, sample_facility):
        base, _ = compute_composite_score(sample_facility, 5, 50)
        boosted, breakdown = compute_composite_score(
            sample_facility, 5, 50, condition_score=100.0
        )
        worsened, _ = compute_composite_score(
            sample_facility, 5, 50, condition_score=0.0
        )
        assert boosted > worsened
        assert "condition_match" in breakdown

    def test_vulnerable_abuse_penalty_heavier(self, sample_facility):
        abusive = sample_facility.model_copy(update={"abuse_icon": True})
        normal, _ = compute_composite_score(abusive, 5, 50)
        vulnerable, _ = compute_composite_score(abusive, 5, 50, vulnerable=True)
        assert normal - vulnerable == 10  # ABUSE_PENALTY_VULNERABLE - ABUSE_PENALTY


class TestChainWarnings:
    def test_low_chain_average(self):
        f = _bare_facility(chain_name="Bad Chain", chain_avg_overall=2.0, chain_facility_count=30)
        warnings = compute_chain_warnings(f)
        assert any("Bad Chain" in w for w in warnings)

    def test_good_chain_no_warning(self):
        f = _bare_facility(chain_name="Good Chain", chain_avg_overall=4.5)
        assert compute_chain_warnings(f) == []

    def test_ownership_change(self):
        f = _bare_facility(changed_ownership_12mo=True)
        assert any("Ownership changed" in w for w in compute_chain_warnings(f))

    def test_special_focus(self):
        f = _bare_facility(special_focus_status="SFF")
        assert any("Special Focus" in w for w in compute_chain_warnings(f))
