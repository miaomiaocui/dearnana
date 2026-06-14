"""Rule-based recommendation report — the token-free counterpart to the AI
advisor.

Produces a structured, plain-language markdown report built entirely from data
DearNana already fetches (composite score breakdown, deficiencies, penalties,
ownership, condition-specific measures). This is what families without an API
key see in place of the AI-written recommendation, so it aims to be genuinely
useful on its own: per-facility strengths/weaknesses, red flags, condition fit,
and concrete questions to ask on a tour.
"""

from dearnana.models import RankedFacility

# Human labels for the composite score components produced by
# ranker.compute_composite_score().
COMPONENT_LABELS: dict[str, str] = {
    "overall_rating": "CMS overall rating",
    "health_inspection": "health-inspection record",
    "staffing_quality": "staffing levels",
    "staff_stability": "staff retention",
    "penalty_history": "penalty & fine history",
    "distance": "proximity",
    "safety": "fire safety (sprinklers)",
    "condition_match": "fit for your loved one's needs",
}

# CMS scope/severity codes G and above indicate actual harm or immediate
# jeopardy; A-F are no-harm or potential-for-harm citations.
_SEVERE_SEVERITY = set("GHIJKL")

# A weak component (low score) maps to a concrete question worth asking on a tour.
_COMPONENT_TOUR_QUESTIONS: dict[str, str] = {
    "staffing_quality": "Staffing looks thin here — how many residents is each aide responsible for on the day, evening, and night shifts?",
    "staff_stability": "Staff turnover looks high — how do you keep care consistent, and how long have the current charge nurses been on the unit?",
    "health_inspection": "The recent inspection record is below average — what were the most recent deficiencies and how were they corrected?",
    "penalty_history": "There are penalties or fines on record — what happened, and what has changed since?",
    "safety": "Sprinkler coverage is incomplete — what is your fire-safety and evacuation plan?",
    "overall_rating": "The overall CMS rating is below average — which area are you actively working to improve this year?",
    "condition_match": "How specifically do you care for residents with my loved one's needs day to day?",
}

# Bands for translating a 0-100 component score into a plain word.
_STRONG = 75.0
_WEAK = 45.0


def format_condition_measures(
    details: list[dict], limit: int = 4, with_percentile: bool = False
) -> list[str]:
    """Shared formatter for condition-specific measure lines (lower is better).

    Used by both the AI prompt builder (llm_advisor) and this report so the two
    paths describe the same numbers identically. Returns indented bullet lines.
    """
    lines: list[str] = []
    relevant = [d for d in details if d.get("value") is not None]
    for d in relevant[:limit]:
        median = d.get("state_median")
        if median is None:
            # Thin benchmark: the measure scored neutral and has no usable
            # state median/percentile (fewer than MIN_BENCHMARK_SAMPLES facilities).
            lines.append(f"  - {d['label']}: {d['value']:.1f}% (state benchmark unavailable)")
            continue
        line = f"  - {d['label']}: {d['value']:.1f}% (state median {median:.1f}%)"
        pct = d.get("percentile")
        if with_percentile and pct is not None:
            line += f" — {percentile_phrase(pct)} of facilities in the state"
        lines.append(line)
    return lines


def percentile_phrase(pct: float) -> str:
    """'better than N%' — but never the overstated 'better than 100%' (a
    facility is part of the state set it's compared against, so it can't beat
    all of it)."""
    better = round((1 - pct) * 100)
    if better >= 100:
        return "better than nearly all"
    if better <= 0:
        return "lower-ranked than nearly all"
    return f"better than {better}%"


def _present_components(r: RankedFacility) -> list[tuple[str, float]]:
    """Score-breakdown components that actually have a label, score-sorted high to low."""
    items = [
        (k, v) for k, v in r.score_breakdown.items() if k in COMPONENT_LABELS
    ]
    items.sort(key=lambda kv: kv[1], reverse=True)
    return items


def _assessment(r: RankedFacility) -> str:
    """One-line strengths/weaknesses summary from the score breakdown."""
    items = _present_components(r)
    if not items:
        return ""
    strengths = [
        f"{COMPONENT_LABELS[k]} ({v:.0f}/100)" for k, v in items if v >= _STRONG
    ][:3]
    weaknesses = [
        f"{COMPONENT_LABELS[k]} ({v:.0f}/100)" for k, v in items if v < _WEAK
    ][-3:]
    parts = []
    if strengths:
        parts.append("**Strong on:** " + ", ".join(strengths) + ".")
    if weaknesses:
        parts.append("**Weaker on:** " + ", ".join(reversed(weaknesses)) + ".")
    if not parts:
        parts.append("A solid all-around profile with no standout strengths or weaknesses.")
    return " ".join(parts)


def _red_flags(r: RankedFacility) -> list[str]:
    """Concrete warnings pulled from facility data — no AI judgment involved."""
    f = r.facility
    flags: list[str] = []
    if f.abuse_icon:
        flags.append("Flagged by CMS for abuse or neglect — investigate carefully before considering.")
    if f.special_focus_status:
        flags.append(f"CMS Special Focus status: {f.special_focus_status} (a history of serious quality problems).")
    flags.extend(r.chain_warnings)
    if f.number_of_penalties > 0:
        fines = f" totaling ${f.total_fines_dollars:,.0f}" if f.total_fines_dollars else ""
        flags.append(f"{f.number_of_penalties} federal penalt{'y' if f.number_of_penalties == 1 else 'ies'} on record{fines}.")
    if r.deficiencies:
        severe = sorted(
            (
                d for d in r.deficiencies
                if str(d.get("severity", "")).strip().upper()[:1] in _SEVERE_SEVERITY
            ),
            key=lambda d: d.get("date") or "",
            reverse=True,  # most recent actual-harm citation first
        )
        if severe:
            d = severe[0]
            more = f" (and {len(severe) - 1} more)" if len(severe) > 1 else ""
            flags.append(
                f"Actual-harm inspection citation [{d.get('severity', '?')}]: "
                f"{d.get('description', '').strip()[:140]}{more}"
            )
    return flags


def _tour_questions(r: RankedFacility) -> list[str]:
    """Questions to ask on a tour, derived from this facility's weak signals."""
    questions: list[str] = []
    for code, score in _present_components(r):
        if score < _WEAK and code in _COMPONENT_TOUR_QUESTIONS:
            questions.append(_COMPONENT_TOUR_QUESTIONS[code])
    # Always-useful baseline question when nothing specific stood out.
    if not questions:
        questions.append(
            "What does a typical day look like for a resident with my loved one's needs, "
            "and who would I call with concerns?"
        )
    return questions[:3]


def _facility_section(i: int, r: RankedFacility) -> str:
    f = r.facility
    rating = f"{f.overall_rating}/5 stars" if f.overall_rating > 0 else "not yet rated"
    lines = [
        f"### #{i}. {f.name}",
        f"{f.address}, {f.city}, {f.state} {f.zip_code} — {r.distance_miles} mi away",
        f"**DearNana score:** {r.composite_score}/100  |  **CMS:** {rating}  |  **Phone:** {f.phone or 'n/a'}",
    ]

    assessment = _assessment(r)
    if assessment:
        lines.append("")
        lines.append(assessment)

    if r.condition_details:
        measures = format_condition_measures(r.condition_details, with_percentile=True)
        if measures:
            lines.append("")
            lines.append("Care measures relevant to the described needs (lower is better):")
            lines.extend(measures)

    flags = _red_flags(r)
    if flags:
        lines.append("")
        lines.append("**Red flags:**")
        lines.extend(f"  - {flag}" for flag in flags)

    questions = _tour_questions(r)
    if questions:
        lines.append("")
        lines.append("**Ask on your tour:**")
        lines.extend(f"  - {q}" for q in questions)

    return "\n".join(lines)


def _top_pick_rationale(ranked: list[RankedFacility]) -> str:
    top = ranked[0]
    items = _present_components(top)
    strong = [COMPONENT_LABELS[k] for k, v in items[:2] if v >= _STRONG]
    reason = f" — strongest on {', '.join(strong)}" if strong else ""
    return (
        f"**Best overall match: #{1}. {top.facility.name}** "
        f"({top.composite_score}/100{reason}). "
        "Scores reflect CMS quality data, not paid placement — verify current "
        "availability, pricing, and Medicaid acceptance directly with the facility."
    )


_NEXT_STEPS = """\
**Next steps**
  - Call your top 2-3 picks to confirm openings, current pricing, and whether they accept Medicaid.
  - Schedule in-person tours; visit once during a meal and once unannounced if you can.
  - Bring a list of your loved one's needs and the tour questions above.
  - Ask to see the most recent state inspection report on site (facilities must provide it).
  - Check whether your state's long-term-care ombudsman has notes on the facility."""


def build_data_report(
    ranked: list[RankedFacility],
    condition: str = "",
    budget: float | None = None,
    budget_note: str = "",
    needs_summary: str = "",
    notice: str = "",
) -> str:
    """Build the full rule-based recommendation report (markdown, no AI).

    `notice` is shown verbatim at the top when set (e.g. an LLM-error message);
    otherwise a tip about enabling the AI report is shown instead.
    """
    if not ranked:
        return "No facilities to report on."

    header = notice or (
        "_No AI provider configured — this is a data-driven report. Set "
        "ANTHROPIC_API_KEY (or DEARNANA_LLM_PROVIDER=ollama for a local model) "
        "for an AI-written version._"
    )
    lines = [header, ""]
    if condition:
        lines.append(f"**Situation:** {condition}")
    if needs_summary and needs_summary.strip() != condition.strip():
        lines.append(f"**Identified needs:** {needs_summary}")
    if budget is not None:
        lines.append(f"**Monthly budget:** ${budget:,.0f}")
    if budget_note:
        lines.append(f"\n> {budget_note}")
    lines.append("")

    for i, r in enumerate(ranked, start=1):
        lines.append(_facility_section(i, r))
        lines.append("")

    lines.append(_top_pick_rationale(ranked))
    lines.append("")
    lines.append(_NEXT_STEPS)
    return "\n".join(lines)
