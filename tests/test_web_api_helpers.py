"""Tests for library helpers added for the web backend (0.1.1)."""

from dearnana.filters import filter_facilities
from dearnana.llm_advisor import build_advisor_prompt, generate_recommendation
from dearnana.models import Facility, RankedFacility


def _facility(ccn="1", **overrides) -> Facility:
    overrides.setdefault("overall_rating", 4)
    return Facility(
        ccn=ccn, name=f"Home {ccn}", address="1 Main St", city="Seattle",
        state="WA", zip_code="98101", latitude=47.6, longitude=-122.3,
        **overrides,
    )


def _ranked(**overrides) -> RankedFacility:
    return RankedFacility(
        facility=_facility(**overrides), distance_miles=2.5, composite_score=80.0,
        score_breakdown={"overall_rating": 80.0},
    )


# --- filter_facilities ---

def test_filter_min_stars():
    facs = [_facility("1", overall_rating=5), _facility("2", overall_rating=2)]
    kept, notes = filter_facilities(facs, min_stars=3)
    assert [f.ccn for f in kept] == ["1"]
    assert notes == ["1 below 3 CMS stars"]


def test_filter_exclude_abuse_and_independent():
    facs = [
        _facility("1", abuse_icon=True),
        _facility("2", chain_name="Big Chain"),
        _facility("3"),
    ]
    kept, notes = filter_facilities(facs, exclude_abuse=True, independent_only=True)
    assert [f.ccn for f in kept] == ["3"]
    assert any("abuse-flagged" in n for n in notes)
    assert any("chain-affiliated" in n for n in notes)


def test_filter_no_active_filters_is_noop():
    facs = [_facility("1"), _facility("2")]
    kept, notes = filter_facilities(facs)
    assert len(kept) == 2 and notes == []


# --- build_advisor_prompt ---

def test_build_advisor_prompt_contains_inputs():
    prompt = build_advisor_prompt([_ranked()], "Mom has dementia", 8000,
                                  needs_summary="dementia")
    assert "Mom has dementia" in prompt
    assert "8,000" in prompt
    assert "Home 1" in prompt
    assert "Identified Care Needs" in prompt


def test_build_advisor_prompt_matches_what_recommendation_sends(monkeypatch, mocker):
    # generate_recommendation must send exactly build_advisor_prompt's output.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("DEARNANA_LLM_PROVIDER", raising=False)
    ranked = [_ranked()]
    expected = build_advisor_prompt(ranked, "dementia", 8000)

    captured = {}

    class FakeProvider:
        def generate(self, prompt):
            captured["prompt"] = prompt
            return "REPORT"

    mocker.patch("dearnana.llm_advisor.get_provider", return_value=FakeProvider())
    out = generate_recommendation(ranked, "dementia", 8000)
    assert out == "REPORT"
    assert captured["prompt"] == expected
