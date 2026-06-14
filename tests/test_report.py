"""Unit tests for the rule-based report (token-free recommendation)."""

from dearnana.models import Facility, RankedFacility
from dearnana.report import build_data_report, format_condition_measures


def _ranked(breakdown=None, **facility_overrides) -> RankedFacility:
    facility = Facility(
        ccn="505001",
        name="Test Home",
        address="1 Main St",
        city="Seattle",
        state="WA",
        zip_code="98101",
        latitude=47.6,
        longitude=-122.3,
        overall_rating=4,
        **facility_overrides,
    )
    return RankedFacility(
        facility=facility,
        distance_miles=2.5,
        composite_score=72.0,
        score_breakdown=breakdown
        or {
            "overall_rating": 80.0,
            "health_inspection": 80.0,
            "staffing_quality": 85.0,
            "staff_stability": 20.0,  # weak -> should surface
            "penalty_history": 100.0,
            "distance": 95.0,
            "safety": 100.0,
        },
    )


def test_report_surfaces_strengths_and_weaknesses():
    text = build_data_report([_ranked()])
    assert "Test Home" in text
    assert "Strong on:" in text
    assert "Weaker on:" in text
    assert "staff retention" in text  # the weak component


def test_report_flags_abuse_and_special_focus():
    r = _ranked(abuse_icon=True, special_focus_status="Special Focus Facility")
    text = build_data_report([r])
    assert "Red flags:" in text
    assert "abuse" in text.lower()
    assert "Special Focus" in text


def test_report_flags_severe_deficiency():
    r = _ranked()
    r.deficiencies = [
        {"severity": "G", "category": "Quality of Care", "description": "Failure to prevent pressure ulcers"},
        {"severity": "B", "category": "Admin", "description": "Minor paperwork issue"},
    ]
    text = build_data_report([r])
    assert "pressure ulcers" in text
    # The B (no-harm) citation should not be surfaced as a red flag.
    assert "paperwork" not in text


def test_report_generates_tour_question_for_weak_component():
    text = build_data_report([_ranked()])
    assert "Ask on your tour:" in text
    assert "turnover" in text.lower()  # staff_stability question


def test_report_includes_next_steps_and_top_pick():
    text = build_data_report([_ranked()], condition="dementia", budget=8000)
    assert "Best overall match" in text
    assert "Next steps" in text
    assert "$8,000" in text


def test_report_notice_shown_when_provided():
    text = build_data_report([_ranked()], notice="AI recommendation unavailable (LLM error)")
    assert "AI recommendation unavailable" in text
    assert "ANTHROPIC_API_KEY" not in text  # tip suppressed when a notice is given


def test_report_tip_mentions_api_key_by_default():
    text = build_data_report([_ranked()])
    assert "ANTHROPIC_API_KEY" in text


def test_format_condition_measures_with_percentile():
    details = [
        {"label": "long-stay antipsychotic use", "value": 8.2, "state_median": 22.1, "percentile": 0.15},
    ]
    lines = format_condition_measures(details, with_percentile=True)
    assert "8.2%" in lines[0]
    assert "better than 85%" in lines[0]


def test_empty_ranked_returns_message():
    assert "No facilities" in build_data_report([])
