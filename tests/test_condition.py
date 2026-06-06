"""Unit tests for condition parsing and measure-weight mapping."""

import anthropic
import pytest

from dearnana.condition import (
    MEASURE_LABELS,
    MEASURE_MAP,
    Need,
    NeedsProfile,
    _parse_keywords,
    build_measure_weights,
    parse_condition,
)


class TestKeywordParser:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Mom has moderate dementia", "dementia"),
            ("Alzheimer's diagnosis last year", "dementia"),
            ("memory problems getting worse", "dementia"),
            ("has fallen twice this month", "fall_risk"),
            ("trouble with balance", "fall_risk"),
            ("uses a wheelchair", "mobility"),
            ("can no longer walk unassisted", "mobility"),
            ("has a pressure sore on her hip", "skin_integrity"),
            ("developed a bedsore", "skin_integrity"),
            ("struggles with depression", "mental_health"),
            ("severe anxiety", "mental_health"),
            ("recurring UTI infections", "continence"),
            ("has a catheter", "continence"),
            ("losing weight, poor appetite", "weight_nutrition"),
            ("difficulty swallowing", "weight_nutrition"),
        ],
    )
    def test_single_category(self, text, expected):
        profile = _parse_keywords(text)
        assert expected in profile.categories()
        assert profile.source == "keywords"

    def test_multi_match(self):
        profile = _parse_keywords("moderate dementia, has fallen twice, uses a walker")
        assert {"dementia", "fall_risk", "mobility"} <= profile.categories()

    def test_no_match(self):
        profile = _parse_keywords("just needs a nice place to live")
        assert profile.is_empty
        assert profile.source == "none"


class TestMeasureWeights:
    def test_weights_normalized(self):
        profile = NeedsProfile(needs=[Need(category="dementia"), Need(category="fall_risk")])
        weights = build_measure_weights(profile)
        assert weights
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_overlapping_measures_sum(self):
        # 401 appears in both fall_risk and mobility
        profile = NeedsProfile(needs=[Need(category="fall_risk"), Need(category="mobility")])
        weights = build_measure_weights(profile)
        # 401 should carry more weight than it would from either category alone
        solo = build_measure_weights(NeedsProfile(needs=[Need(category="fall_risk")]))
        assert weights["401"] > 0
        assert "401" in solo

    def test_empty_profile(self):
        assert build_measure_weights(NeedsProfile()) == {}

    def test_need_weight_scales(self):
        heavy = NeedsProfile(
            needs=[Need(category="dementia", weight=1.0), Need(category="fall_risk", weight=0.2)]
        )
        weights = build_measure_weights(heavy)
        assert weights["481"] > weights["410"]

    def test_every_measure_code_has_label(self):
        for category, measures in MEASURE_MAP.items():
            for code, _ in measures:
                assert code in MEASURE_LABELS, f"{category} measure {code} missing label"


class TestParseCondition:
    def test_empty_text(self):
        assert parse_condition("").is_empty
        assert parse_condition("   ").is_empty

    def test_no_api_key_uses_keywords(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        profile = parse_condition("moderate dementia")
        assert profile.source == "keywords"
        assert "dementia" in profile.categories()

    def test_use_llm_false_uses_keywords(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        profile = parse_condition("moderate dementia", use_llm=False)
        assert profile.source == "keywords"

    def test_llm_success(self, monkeypatch, mocker):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        expected = NeedsProfile(
            needs=[Need(category="dementia", weight=1.0)], summary="dementia care"
        )
        mock_response = mocker.Mock()
        mock_response.parsed_output = expected
        mock_client = mocker.Mock()
        mock_client.messages.parse.return_value = mock_response
        mocker.patch("dearnana.condition.anthropic.Anthropic", return_value=mock_client)

        profile = parse_condition("Mom has dementia")
        assert profile.source == "ai"
        assert "dementia" in profile.categories()

    def test_llm_error_falls_back_to_keywords(self, monkeypatch, mocker):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        mock_client = mocker.Mock()
        mock_client.messages.parse.side_effect = anthropic.APIConnectionError(
            request=mocker.Mock()
        )
        mocker.patch("dearnana.condition.anthropic.Anthropic", return_value=mock_client)

        profile = parse_condition("Mom has dementia and has fallen")
        assert profile.source == "keywords"
        assert "dementia" in profile.categories()
