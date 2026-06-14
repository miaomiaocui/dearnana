"""Validation tests for the web API's run_search (no network)."""

import os
import sys

import pytest

# The Vercel function lives outside the package; add it to the path.
_WEB_API = os.path.join(os.path.dirname(__file__), "..", "web", "api")
sys.path.insert(0, os.path.abspath(_WEB_API))

from search import SearchError, _build_profile, run_search  # noqa: E402


def test_missing_address_is_400():
    with pytest.raises(SearchError) as e:
        run_search({"budget": 8000})
    assert e.value.status == 400


def test_missing_budget_is_400():
    with pytest.raises(SearchError) as e:
        run_search({"address": "Bellevue, WA"})
    assert e.value.status == 400


def test_checklist_needs_build_interactive_profile():
    profile = _build_profile([{"category": "dementia", "weight": 1.0}], "")
    assert profile.source == "interactive"
    assert "dementia" in profile.categories()


def test_checklist_weight_is_clamped():
    profile = _build_profile([{"category": "dementia", "weight": 9.9}], "")
    assert profile.needs[0].weight == 1.0


def test_freetext_falls_back_to_keyword_parse_no_key():
    profile = _build_profile([], "Mom has dementia and has fallen")
    assert profile.source == "keywords"
    assert "dementia" in profile.categories()
