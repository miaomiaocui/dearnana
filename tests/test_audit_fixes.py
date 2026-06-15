"""Regression tests for the pre-publish audit findings (bugs 1-3 + polish)."""

import json

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from dearnana import cms_client
from dearnana.cli import _format_facility_lines, main
from dearnana.condition import Need, parse_condition
from dearnana.llm_advisor import _format_facility, sort_deficiencies_recent_first
from dearnana.models import Facility, RankedFacility
from dearnana.report import build_data_report, format_condition_measures, percentile_phrase


def _ranked(condition_details=None, **facility_overrides) -> RankedFacility:
    facility = Facility(
        ccn="505001", name="Test Home", address="1 Main St", city="Seattle",
        state="WA", zip_code="98101", latitude=47.6, longitude=-122.3,
        overall_rating=4, **facility_overrides,
    )
    return RankedFacility(
        facility=facility, distance_miles=2.5, composite_score=80.0,
        score_breakdown={"overall_rating": 80.0, "staffing_quality": 80.0},
        condition_details=condition_details,
    )


# --- Bug 1: thin benchmark -> state_median is None must not crash formatters ---

# A real detail from score_condition_match() when the benchmark is too thin
# (e.g. DC / Alaska): value is recorded but median/percentile are None.
_THIN = [{"code": "481", "label": "long-stay antipsychotic use", "value": 2.5,
          "state_median": None, "percentile": None, "weight": 1.0, "score": 50.0}]


def test_report_formatter_handles_none_median():
    lines = format_condition_measures(_THIN, with_percentile=True)
    assert lines and "state benchmark unavailable" in lines[0]


def test_llm_advisor_formatter_handles_none_median():
    text = _format_facility(1, _ranked(condition_details=_THIN))  # must not raise
    assert "state benchmark unavailable" in text


def test_cli_formatter_handles_none_median():
    text = _format_facility_lines(0, _ranked(condition_details=_THIN))  # must not raise
    assert "state benchmark unavailable" in text


def test_full_report_handles_none_median():
    assert "Test Home" in build_data_report([_ranked(condition_details=_THIN)])


# --- Bug 2: corrupted / partial cache must not brick the tool ---

def test_corrupt_cache_is_a_miss_and_gets_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(cms_client, "CACHE_DIR", str(tmp_path))
    bad = tmp_path / "providers_WA.json"
    bad.write_text("{not valid json")  # e.g. interrupted write
    assert cms_client._read_cache("providers_WA") is None
    assert not bad.exists()  # healed for the next run


def test_cache_write_is_atomic_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cms_client, "CACHE_DIR", str(tmp_path))
    cms_client._write_cache("providers_WA", [{"ccn": "1"}])
    assert cms_client._read_cache("providers_WA") == [{"ccn": "1"}]
    assert not list(tmp_path.glob("*.tmp"))  # no leftover temp file


# --- Bug 3: a valid empty AI parse must be trusted over the keyword matcher ---

def test_empty_ai_profile_is_trusted_not_overridden(monkeypatch, mocker):
    # The model correctly reads the negation and returns no needs; the keyword
    # matcher would (wrongly) match "dementia" and "fallen".
    monkeypatch.setenv("DEARNANA_LLM_PROVIDER", "ollama")
    empty = json.dumps({"needs": [], "summary": "", "source": "none"})
    resp = mocker.Mock()
    resp.json.return_value = {"message": {"content": empty}}
    resp.raise_for_status.return_value = None
    mocker.patch("dearnana.llm.httpx.post", return_value=resp)

    profile = parse_condition("She does NOT have dementia and has never fallen")
    assert profile.is_empty
    assert profile.source == "ai"
    assert "dementia" not in profile.categories()


# --- Polish items ---

def test_need_weight_is_constrained_to_0_1():
    with pytest.raises(ValidationError):
        Need(category="dementia", weight=1.5)
    with pytest.raises(ValidationError):
        Need(category="dementia", weight=-0.1)


def test_percentile_phrase_never_overstates():
    assert percentile_phrase(0.0) == "better than nearly all"      # was "better than 100%"
    assert percentile_phrase(1.0) == "lower-ranked than nearly all"
    assert percentile_phrase(0.15) == "better than 85%"


def test_unreported_nurse_hours_say_not_reported():
    text = _format_facility(1, _ranked(total_nurse_staffing_hours=0.0, rn_staffing_hours=0.0))
    assert "not reported" in text
    assert "0.0" not in text.split("Nurse hours")[1].split("\n")[0]


def test_deficiencies_sorted_recent_first():
    defs = [
        {"date": "2023-01-01", "description": "old"},
        {"date": "2025-06-01", "description": "new"},
        {"date": "2024-03-01", "description": "mid"},
    ]
    ordered = [d["description"] for d in sort_deficiencies_recent_first(defs)]
    assert ordered == ["new", "mid", "old"]


@pytest.mark.parametrize("args", [["--top", "0"], ["--radius", "0"]])
def test_cli_rejects_nonpositive_numbers(args):
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 2  # click usage error, before any network
    assert "Invalid value" in result.output
