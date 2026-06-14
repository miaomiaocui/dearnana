"""Vercel Python serverless function: the full DearNana search pipeline.

Reuses the published `dearnana` library. Does ALL the non-AI work (geocode,
fetch, rank, enrich, rule-based report, comparison, export) and additionally
returns a ready-to-send Anthropic prompt. It NEVER receives or handles the
user's API key — the browser sends that prompt to Anthropic directly.
"""

import json
import os

# Vercel's home dir is read-only; point the library's cache at a writable path
# before importing dearnana (config reads DEARNANA_CACHE_DIR at import time).
os.environ.setdefault("DEARNANA_CACHE_DIR", "/tmp/dearnana-cache")

from http.server import BaseHTTPRequestHandler

from dearnana import (
    build_advisor_prompt,
    build_comparison_table,
    build_data_report,
    build_measure_weights,
    compute_measure_benchmarks,
    filter_facilities,
    geocode_address,
    parse_condition,
    rank_facilities,
    score_condition_match,
    to_csv,
    to_html,
)
from dearnana.cms_client import (
    enrich_facilities,
    fetch_mds_measures_by_state,
    fetch_state_facilities,
)
from dearnana.condition import CATEGORY_LABELS, Need, NeedsProfile
from dearnana.config import (
    LLM_MAX_TOKENS,
    LLM_MODEL,
    NATIONAL_MEDIAN_MONTHLY_COST,
    STATE_MEDIAN_MONTHLY_COST,
)
from dearnana.errors import DataFetchError

DEFAULT_RADIUS = 50.0
DEFAULT_TOP_N = 5
MAX_TOP_N = 15  # bound enrichment work to stay within the serverless time limit


class SearchError(Exception):
    """User-facing error with an HTTP status code."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _build_profile(needs: list[dict], condition_text: str) -> NeedsProfile:
    """Checklist needs (deterministic) take priority; else keyword-parse the
    free text. Neither path uses an API key."""
    if needs:
        items = []
        for n in needs:
            category = n.get("category")
            if category not in CATEGORY_LABELS:
                continue
            weight = float(n.get("weight", 1.0))
            items.append(Need(category=category, weight=max(0.0, min(1.0, weight))))
        if items:
            summary = ", ".join(CATEGORY_LABELS[i.category] for i in items)
            return NeedsProfile(needs=items, summary=summary, source="interactive")
    if condition_text and condition_text.strip():
        return parse_condition(condition_text, use_llm=False)
    return NeedsProfile(source="none")


def run_search(payload: dict) -> dict:
    """Pure pipeline function (no HTTP), so it is unit-testable directly."""
    address = (payload.get("address") or "").strip()
    if not address:
        raise SearchError(400, "An address or area is required.")
    try:
        budget = float(payload.get("budget"))
    except (TypeError, ValueError):
        raise SearchError(400, "A numeric monthly budget is required.")

    radius = float(payload.get("radius") or DEFAULT_RADIUS)
    if radius <= 0:
        raise SearchError(400, "Radius must be greater than 0.")
    top_n = int(payload.get("topN") or DEFAULT_TOP_N)
    top_n = max(1, min(MAX_TOP_N, top_n))

    needs = payload.get("needs") or []
    condition_text = payload.get("conditionText") or ""
    filters = payload.get("filters") or {}

    # 1. Geocode
    try:
        lat, lng, state = geocode_address(address)
    except ValueError as e:
        raise SearchError(400, str(e))

    # 2. Care-needs profile (no AI)
    profile = _build_profile(needs, condition_text)
    condition = condition_text.strip() or profile.summary

    # 3. Fetch + filter
    try:
        result = fetch_state_facilities(state)
    except DataFetchError as e:
        raise SearchError(502, str(e))
    facilities, filter_notes = filter_facilities(
        result.facilities,
        min_stars=int(filters.get("minStars") or 0),
        exclude_abuse=bool(filters.get("excludeAbuse")),
        exclude_special_focus=bool(filters.get("excludeSpecialFocus")),
        sprinkler_only=bool(filters.get("sprinklerOnly")),
        independent_only=bool(filters.get("independentOnly")),
    )
    if not facilities:
        raise SearchError(404, "No facilities match those filters in this state.")

    # 4. Condition-specific measures (no AI)
    condition_scores = None
    if not profile.is_empty:
        weights = build_measure_weights(profile)
        if weights:
            try:
                mds = fetch_mds_measures_by_state(state)
            except DataFetchError:
                mds = {}
            if mds:
                benchmarks = compute_measure_benchmarks(mds)
                condition_scores = {
                    ccn: score_condition_match(fac_mds, weights, benchmarks)
                    for ccn, fac_mds in mds.items()
                }

    vulnerable = bool(profile.categories() & {"dementia", "mental_health"})

    # 5. Rank
    ranked = rank_facilities(
        facilities, lat, lng, radius_miles=radius, top_n=top_n,
        condition_scores=condition_scores, vulnerable=vulnerable,
    )
    if not ranked:
        raise SearchError(404, f"No facilities within {radius:.0f} miles. Try a larger radius.")

    # 6. Enrich top picks (parallel)
    try:
        enrichment = enrich_facilities([r.facility.ccn for r in ranked])
    except DataFetchError:
        enrichment = {}
    for r in ranked:
        data = enrichment.get(r.facility.ccn, {})
        r.deficiencies = data.get("deficiencies")
        r.penalties = data.get("penalties")
        r.ownership = data.get("ownership")

    # 7. Budget note (same rule as the CLI)
    state_median = STATE_MEDIAN_MONTHLY_COST.get(state, NATIONAL_MEDIAN_MONTHLY_COST)
    budget_note = ""
    if budget < state_median * 0.7:
        budget_note = (
            f"Your budget (${budget:,.0f}/mo) is below the {state} median for "
            f"semi-private rooms (~${state_median:,}/mo). Options may be limited — "
            "contact facilities directly; many accept Medicaid."
        )

    # 8. Build outputs (all non-AI) + the optional AI prompt
    return {
        "query": {
            "address": address, "state": state, "lat": lat, "lng": lng,
            "budget": budget, "radius": radius, "topN": top_n,
            "needs": sorted(profile.categories()), "filterNotes": filter_notes,
        },
        "facilities": [r.model_dump() for r in ranked],
        "reportMarkdown": build_data_report(
            ranked, condition, budget, budget_note, needs_summary=profile.summary,
            notice="_This report is built entirely from public CMS data — no AI required._",
        ),
        "comparisonMarkdown": build_comparison_table(ranked),
        "csv": to_csv(ranked),
        "html": to_html(ranked),
        "budgetNote": budget_note,
        "ai": {
            "advisorPrompt": build_advisor_prompt(
                ranked, condition, budget, budget_note, needs_summary=profile.summary
            ),
            "model": LLM_MODEL,
            "maxTokens": LLM_MAX_TOKENS,
        },
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "Invalid JSON body."})
        try:
            self._send(200, run_search(payload))
        except SearchError as e:
            self._send(e.status, {"error": e.message})
        except Exception:  # never leak internals/stack traces to clients
            self._send(500, {"error": "Something went wrong processing the search."})
