"""Unit tests for the LLM advisor formatting and fallbacks."""

import anthropic

from dearnana.llm_advisor import _format_facility, generate_recommendation
from dearnana.models import Facility, RankedFacility


def _ranked(**facility_overrides) -> RankedFacility:
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
        composite_score=85.0,
        score_breakdown={},
    )


def test_format_includes_chain():
    r = _ranked(chain_name="Big Chain", chain_facility_count=40, chain_avg_overall=2.1)
    text = _format_facility(1, r)
    assert "Big Chain" in text
    assert "40 facilities" in text


def test_format_independent_when_no_chain():
    text = _format_facility(1, _ranked())
    assert "Independent" in text


def test_format_includes_ownership_sorted():
    r = _ranked()
    r.ownership = [
        {"owner_name": "SMALL, SAM", "owner_type": "Individual", "role": "OWNER",
         "ownership_percentage": "9%", "association_date": "since 2020"},
        {"owner_name": "BIG, BETTY", "owner_type": "Individual", "role": "OWNER",
         "ownership_percentage": "81%", "association_date": "since 1990"},
    ]
    text = _format_facility(1, r)
    assert text.index("BIG, BETTY") < text.index("SMALL, SAM")


def test_format_includes_condition_measures():
    r = _ranked()
    r.condition_details = [
        {"code": "481", "label": "long-stay antipsychotic use", "value": 8.2,
         "state_median": 22.1, "percentile": 0.15, "weight": 0.4, "score": 85.0},
    ]
    text = _format_facility(1, r)
    assert "antipsychotic" in text
    assert "8.2%" in text


def test_format_includes_chain_warnings():
    r = _ranked()
    r.chain_warnings = ["Ownership changed within the last 12 months"]
    text = _format_facility(1, r)
    assert "WARNING: Ownership changed" in text


def test_no_provider_falls_back(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEARNANA_LLM_PROVIDER", raising=False)
    text = generate_recommendation([_ranked()], "dementia", 8000)
    assert "Test Home" in text
    assert "ANTHROPIC_API_KEY" in text


def test_api_error_falls_back(monkeypatch, mocker):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("DEARNANA_LLM_PROVIDER", raising=False)
    mock_client = mocker.Mock()
    mock_client.messages.create.side_effect = anthropic.APIConnectionError(
        request=mocker.Mock()
    )
    mocker.patch("dearnana.llm.anthropic.Anthropic", return_value=mock_client)

    text = generate_recommendation([_ranked()], "dementia", 8000)
    assert "AI recommendation unavailable" in text
    assert "Test Home" in text


def test_ollama_generates_report(monkeypatch, mocker):
    monkeypatch.setenv("DEARNANA_LLM_PROVIDER", "ollama")
    mock_resp = mocker.Mock()
    mock_resp.json.return_value = {"message": {"content": "LOCAL MODEL REPORT"}}
    mock_resp.raise_for_status.return_value = None
    mocker.patch("dearnana.llm.httpx.post", return_value=mock_resp)

    text = generate_recommendation([_ranked()], "dementia", 8000)
    assert text == "LOCAL MODEL REPORT"


def test_ollama_down_falls_back(monkeypatch, mocker):
    monkeypatch.setenv("DEARNANA_LLM_PROVIDER", "ollama")
    import httpx

    mocker.patch("dearnana.llm.httpx.post", side_effect=httpx.ConnectError("refused"))
    text = generate_recommendation([_ranked()], "dementia", 8000)
    assert "AI recommendation unavailable" in text
    assert "Test Home" in text
