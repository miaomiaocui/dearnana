"""Vercel Python serverless function: the full DearNana search pipeline.

Reuses the published `dearnana` library. Does ALL the non-AI work (geocode,
fetch, rank, enrich, rule-based report, comparison, export) and additionally
returns a ready-to-send Anthropic prompt. It NEVER receives or handles the
user's API key — the browser sends that prompt to Anthropic directly.
"""

import base64
import gzip
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# Vercel's home dir is read-only; point the library's cache at a writable path
# before importing dearnana (config reads DEARNANA_CACHE_DIR at import time).
os.environ.setdefault("DEARNANA_CACHE_DIR", "/tmp/dearnana-cache")

from http.server import BaseHTTPRequestHandler

import httpx
import zipcodes  # offline US ZIP -> lat/lng/state; no network, no rate limits

from dearnana import (
    build_advisor_prompt,
    build_comparison_table,
    build_measure_weights,
    compute_measure_benchmarks,
    filter_facilities,
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
from dearnana.models import StateFacilities

DEFAULT_RADIUS = 50.0
DEFAULT_TOP_N = 5
MAX_TOP_N = 15  # bound enrichment work to stay within the serverless time limit
MAX_BODY_BYTES = 16384  # reject oversized request bodies
MAX_CONDITION_CHARS = 1000  # cap free-text that flows into the AI prompt

# --- Optional Upstash Redis: per-IP rate limiting + shared CMS cache ---------
# Both features no-op unless these env vars are set, so the app works locally
# and before Upstash is provisioned. Provision a free Redis at upstash.com and
# add UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN in Vercel.
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
RATE_LIMIT = int(os.environ.get("SEARCH_RATE_LIMIT", "15"))  # requests…
RATE_WINDOW = int(os.environ.get("SEARCH_RATE_WINDOW", "60"))  # …per this many seconds
CACHE_TTL = 86400  # 24h — CMS refreshes monthly, so a day is plenty


def _redis_enabled() -> bool:
    return bool(UPSTASH_URL and UPSTASH_TOKEN)


def _redis_cmd(*args):
    """Run one Redis command via the Upstash REST API. Caller handles errors."""
    resp = httpx.post(
        UPSTASH_URL,
        headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
        json=[str(a) for a in args],
        timeout=3.0,
    )
    resp.raise_for_status()
    return resp.json().get("result")


def is_allowed(ip: str) -> bool:
    """Per-IP fixed-window rate limit. Fail-open: never block on limiter errors
    or when Upstash isn't configured."""
    if not _redis_enabled() or not ip:
        return True
    try:
        key = f"rl:search:{ip}"
        count = _redis_cmd("INCR", key)
        if int(count) == 1:
            _redis_cmd("EXPIRE", key, RATE_WINDOW)
        return int(count) <= RATE_LIMIT
    except Exception:
        return True


def _cache_get(key: str) -> str | None:
    if not _redis_enabled():
        return None
    try:
        packed = _redis_cmd("GET", key)
        if not packed:
            return None
        return gzip.decompress(base64.b64decode(packed)).decode()
    except Exception:
        return None


def _cache_set(key: str, text: str) -> None:
    if not _redis_enabled():
        return
    try:
        packed = base64.b64encode(gzip.compress(text.encode())).decode()
        _redis_cmd("SET", key, packed, "EX", CACHE_TTL)
    except Exception:
        pass


def _fetch_providers_cached(state: str) -> StateFacilities:
    raw = _cache_get(f"dn:prov:{state}")
    if raw:
        try:
            return StateFacilities.model_validate_json(raw)
        except Exception:
            pass
    result = fetch_state_facilities(state)
    _cache_set(f"dn:prov:{state}", result.model_dump_json())
    return result


def _fetch_mds_cached(state: str) -> dict:
    raw = _cache_get(f"dn:mds:{state}")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    mds = fetch_mds_measures_by_state(state)
    _cache_set(f"dn:mds:{state}", json.dumps(mds))
    return mds


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


def _lookup_zip(zip_code: str) -> tuple[float, float, str, str]:
    """Resolve a 5-digit US ZIP to (lat, lng, state, city) fully offline."""
    zip_code = (zip_code or "").strip()
    if not re.fullmatch(r"\d{5}", zip_code):
        raise SearchError(400, "Please enter a 5-digit US ZIP code.")
    matches = zipcodes.matching(zip_code)
    if not matches:
        raise SearchError(400, f"We couldn't find ZIP code {zip_code}. Please double-check it.")
    m = matches[0]
    return float(m["lat"]), float(m["long"]), m["state"], m["city"]


def run_search(payload: dict) -> dict:
    """Pure pipeline function (no HTTP), so it is unit-testable directly."""
    lat, lng, state, city = _lookup_zip(payload.get("zip"))
    zip_code = str(payload.get("zip")).strip()
    try:
        budget = float(payload.get("budget"))
    except (TypeError, ValueError):
        raise SearchError(400, "A numeric monthly budget is required.")

    radius = float(payload.get("radius") or DEFAULT_RADIUS)
    if radius <= 0:
        raise SearchError(400, "Radius must be greater than 0.")
    top_n = int(payload.get("topN") or DEFAULT_TOP_N)
    top_n = max(1, min(MAX_TOP_N, top_n))

    needs = (payload.get("needs") or [])[:20]
    condition_text = (payload.get("conditionText") or "")[:MAX_CONDITION_CHARS]
    filters = payload.get("filters") or {}

    # Care-needs profile (no AI)
    profile = _build_profile(needs, condition_text)
    condition = condition_text.strip() or profile.summary

    # 3 + 4. Fetch the two independent state-wide datasets concurrently — the
    # provider list and (when needed) the MDS quality measures — to cut wall
    # time on big states and stay within the serverless time limit.
    weights = build_measure_weights(profile) if not profile.is_empty else {}

    def _mds() -> dict:
        try:
            return _fetch_mds_cached(state)
        except DataFetchError:
            return {}

    with ThreadPoolExecutor(max_workers=2) as ex:
        fac_future = ex.submit(_fetch_providers_cached, state)
        mds_future = ex.submit(_mds) if weights else None
        try:
            result = fac_future.result()
        except DataFetchError as e:
            raise SearchError(502, str(e))
        mds = mds_future.result() if mds_future else {}

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

    condition_scores = None
    if weights and mds:
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
            "zip": zip_code, "city": city, "state": state, "lat": lat, "lng": lng,
            "budget": budget, "radius": radius, "topN": top_n,
            "needs": sorted(profile.categories()), "filterNotes": filter_notes,
        },
        "facilities": [r.model_dump() for r in ranked],
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

    def _client_ip(self) -> str:
        xff = self.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
        return self.headers.get("x-real-ip", "") or self.client_address[0]

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return self._send(413, {"error": "Request too large."})

        # Same-origin guard: block other sites' browsers from calling the API.
        # (Non-browser clients send no Origin and are bounded by the rate limit.)
        origin = self.headers.get("Origin")
        if origin:
            host = (self.headers.get("Host") or "").split(":")[0]
            if urlparse(origin).hostname not in (host, "localhost", "127.0.0.1"):
                return self._send(403, {"error": "Cross-origin requests are not allowed."})

        # Per-IP rate limit (no-op unless Upstash is configured).
        if not is_allowed(self._client_ip()):
            return self._send(
                429, {"error": "Too many searches from your network — please wait a minute and try again."}
            )

        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "Invalid JSON body."})
        try:
            self._send(200, run_search(payload))
        except SearchError as e:
            self._send(e.status, {"error": e.message})
        except Exception:  # never leak internals/stack traces to clients
            self._send(500, {"error": "Something went wrong processing the search."})
