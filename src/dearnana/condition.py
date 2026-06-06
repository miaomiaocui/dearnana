"""Parse a free-text care-needs description into a structured needs profile.

The profile drives condition-aware ranking: each need category maps to CMS
MDS quality measures (lower = better) that get weighted in the composite
score. Parsing uses a small Claude call when an API key is available, with
a keyword matcher as fallback so personalization works offline.
"""

import os
import re
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from dearnana.config import CONDITION_PARSER_MODEL

NeedCategory = Literal[
    "dementia",
    "fall_risk",
    "mobility",
    "skin_integrity",
    "mental_health",
    "continence",
    "weight_nutrition",
]


class Need(BaseModel):
    category: NeedCategory
    weight: float = 1.0  # relative importance, 0-1
    rationale: str = ""


class NeedsProfile(BaseModel):
    needs: list[Need] = Field(default_factory=list)
    summary: str = ""
    source: Literal["ai", "keywords", "none"] = "none"

    @property
    def is_empty(self) -> bool:
        return not self.needs

    def categories(self) -> set[str]:
        return {n.category for n in self.needs}


# Each category maps to (MDS measure code, relative weight within category).
# Lower measure scores are better for all of these.
MEASURE_MAP: dict[str, list[tuple[str, float]]] = {
    "dementia": [("481", 1.0), ("434", 0.5), ("452", 0.6), ("409", 0.6)],
    "fall_risk": [("410", 1.0), ("401", 0.4)],
    "mobility": [("451", 1.0), ("401", 0.7), ("409", 0.4)],
    "skin_integrity": [("479", 1.0), ("401", 0.3)],
    "mental_health": [("408", 1.0), ("452", 0.7), ("481", 0.4)],
    "continence": [("407", 1.0), ("406", 0.8), ("480", 0.8)],
    "weight_nutrition": [("404", 1.0), ("401", 0.3)],
}

MEASURE_LABELS: dict[str, str] = {
    "401": "ADL help needs increased",
    "404": "excessive weight loss",
    "406": "catheter use",
    "407": "UTI rate",
    "408": "depressive symptoms",
    "409": "physical restraint use",
    "410": "falls with major injury",
    "434": "short-stay new antipsychotic",
    "451": "walking ability worsened",
    "452": "antianxiety/hypnotic use",
    "479": "pressure ulcers",
    "480": "bowel/bladder incontinence worsened",
    "481": "long-stay antipsychotic use",
}

CATEGORY_LABELS: dict[str, str] = {
    "dementia": "dementia / memory care",
    "fall_risk": "fall risk",
    "mobility": "mobility",
    "skin_integrity": "skin integrity / wound care",
    "mental_health": "mental health",
    "continence": "continence / urinary care",
    "weight_nutrition": "weight & nutrition",
}

_KEYWORD_PATTERNS: dict[str, str] = {
    "dementia": r"dementia|alzheim|memory",
    "fall_risk": r"\bfall(s|en|ing)?\b|\bfell\b|balance",
    "mobility": r"mobilit|wheelchair|walk|walker|bedridden|ambulat|immobile",
    "skin_integrity": r"wound|ulcer|bedsore|pressure sore|skin",
    "mental_health": r"depress|anxiet|mood|psychiatric|mental",
    "continence": r"catheter|\buti\b|incontinen|bladder|urinary",
    "weight_nutrition": r"weight|appetite|\beat(ing)?\b|nutrition|swallow|feeding",
}

_PARSER_PROMPT = """\
A family is looking for a nursing home. Map their description of their loved \
one's condition and care needs onto the fixed need categories. Only include \
categories clearly supported by the text, with weight reflecting how central \
each need is (1.0 = primary concern). Write a one-line summary restating the \
needs. Ignore anything that doesn't fit a category.

Description:
{text}\
"""


def _parse_keywords(text: str) -> NeedsProfile:
    lower = text.lower()
    needs = [
        Need(category=cat, weight=1.0, rationale="keyword match")
        for cat, pattern in _KEYWORD_PATTERNS.items()
        if re.search(pattern, lower)
    ]
    if not needs:
        return NeedsProfile(source="none")
    return NeedsProfile(needs=needs, summary=text.strip(), source="keywords")


def _parse_with_llm(text: str, api_key: str) -> NeedsProfile | None:
    """Single small Claude call returning a validated NeedsProfile.

    Returns None on any API or validation failure so the caller can fall
    back to keyword parsing.
    """
    client = anthropic.Anthropic(api_key=api_key)
    if not hasattr(client.messages, "parse"):
        return None  # SDK too old for structured outputs — use keyword fallback
    try:
        response = client.messages.parse(
            model=CONDITION_PARSER_MODEL,
            max_tokens=500,
            output_format=NeedsProfile,
            messages=[{"role": "user", "content": _PARSER_PROMPT.format(text=text)}],
        )
        profile = response.parsed_output
        if profile is None:
            return None
        profile.source = "ai"
        return profile
    except (anthropic.APIError, anthropic.APIConnectionError, ValidationError):
        return None


def parse_condition(text: str, use_llm: bool = True) -> NeedsProfile:
    """Parse free-text care needs into a NeedsProfile.

    Uses Claude when use_llm is True and ANTHROPIC_API_KEY is set; falls back
    to keyword matching otherwise (or on any API failure). Never raises.
    """
    if not text or not text.strip():
        return NeedsProfile(source="none")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if use_llm and api_key:
        profile = _parse_with_llm(text, api_key)
        if profile is not None and not profile.is_empty:
            return profile

    return _parse_keywords(text)


def build_measure_weights(profile: NeedsProfile) -> dict[str, float]:
    """Union the per-category measure lists scaled by need weight.

    Overlapping measures sum; the result is normalized to sum to 1.0.
    Returns an empty dict for an empty profile.
    """
    raw: dict[str, float] = {}
    for need in profile.needs:
        for code, rel_weight in MEASURE_MAP.get(need.category, []):
            raw[code] = raw.get(code, 0.0) + rel_weight * max(need.weight, 0.0)
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {code: w / total for code, w in raw.items()}


def describe_profile(profile: NeedsProfile) -> str:
    """Human-readable one-liner, e.g. for CLI echo."""
    parts = []
    for need in sorted(profile.needs, key=lambda n: -n.weight):
        measures = ", ".join(
            MEASURE_LABELS[code] for code, _ in MEASURE_MAP.get(need.category, [])[:2]
        )
        parts.append(f"{CATEGORY_LABELS.get(need.category, need.category)} ({measures})")
    return "; ".join(parts)
