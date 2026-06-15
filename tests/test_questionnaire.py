"""Unit tests for the interactive needs questionnaire (deterministic, no AI)."""

from dearnana.condition import CATEGORY_LABELS
from dearnana.questionnaire import prompt_needs


def _run(confirm_answers, severity_answers):
    confirms = iter(confirm_answers)
    severities = iter(severity_answers)
    return prompt_needs(
        echo=lambda *a, **k: None,
        confirm=lambda *a, **k: next(confirms),
        prompt=lambda *a, **k: next(severities),
    )


def test_selected_categories_and_weights():
    # CATEGORY_LABELS order: dementia, fall_risk, mobility, skin_integrity,
    # mental_health, continence, weight_nutrition
    profile = _run([True, True, False, False, False, False, False], ["3", "2"])
    assert profile.source == "interactive"
    assert profile.categories() == {"dementia", "fall_risk"}
    weights = {n.category: n.weight for n in profile.needs}
    assert weights["dementia"] == 1.0  # severity 3
    assert weights["fall_risk"] == 0.7  # severity 2
    assert profile.summary  # human-readable summary built


def test_no_selection_yields_empty_profile():
    profile = _run([False] * len(CATEGORY_LABELS), [])
    assert profile.is_empty
    assert profile.source == "interactive"
