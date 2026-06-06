# DearNana

**Find trustworthy nursing homes using CMS public data — not ads, not referrals.**

[![PyPI](https://img.shields.io/pypi/v/dearnana)](https://pypi.org/project/dearnana/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

DearNana searches the CMS (Centers for Medicare & Medicaid Services) public database of all Medicare/Medicaid certified nursing homes in the US and scores each facility on objective criteria derived entirely from government data. Your description of your loved one's care needs personalizes the ranking: it is matched against CMS's per-facility clinical quality measures (antipsychotic medication rates for dementia, falls with major injury for fall risk, pressure ulcers for wound care, and more). Each facility's ownership chain — and the chain's average track record — is surfaced alongside the score. Optionally, DearNana generates a plain-language recommendation report using AI. No facility pays to be included, and no referral fees are ever involved. CMS refreshes the underlying datasets monthly.

---

## Installation

```bash
pip install dearnana
```

Until the first PyPI release lands, install straight from GitHub:

```bash
pip install git+https://github.com/miaomiaocui/dearnana
```

**Requirements:**

- Python 3.11 or higher
- For AI-generated recommendations: set the `ANTHROPIC_API_KEY` environment variable (get a key at [console.anthropic.com](https://console.anthropic.com))
- Use `--no-ai` to skip AI entirely — ranking (including condition personalization via keyword matching) still works using CMS data only

**Optional environment variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEARNANA_REPORTS_DIR` | `./dearnana-reports` | Where markdown reports are written |
| `DEARNANA_LLM_PROVIDER` | `anthropic` | `anthropic` (API key required) or `ollama` (local models) |
| `DEARNANA_LLM_MODEL` | `claude-sonnet-4-6` / `llama3.1:8b` | Model for the recommendation report (default depends on provider) |
| `DEARNANA_PARSER_MODEL` | `claude-haiku-4-5` / same as LLM model | Model for condition parsing |
| `DEARNANA_OLLAMA_HOST` | `http://localhost:11434` | Ollama server address |

---

## Run Fully Local with Ollama

Prefer not to send anything to a cloud API? DearNana can use a local model
via [Ollama](https://ollama.com) — **the care-needs description never leaves
your machine** (the only network calls are to CMS for facility data and
OpenStreetMap for geocoding your search address):

```bash
ollama pull llama3.1:8b

export DEARNANA_LLM_PROVIDER=ollama
dearnana --address "Bellevue, WA 98008" --budget 8000 \
  --condition "Mom has moderate dementia and has fallen twice"
```

No API key needed. Pick any model you have pulled with `DEARNANA_LLM_MODEL`
(e.g. `llama3.1:70b`, `qwen2.5:14b`).

**Quality note:** local model output quality varies widely by model and
size — expect smaller models (e.g. 8B) to produce more generic
recommendation reports than the cloud default. Try a couple of models you
can run and compare. The condition-parsing step works well even on small
models, and if the model fails or Ollama isn't running, DearNana degrades
gracefully to keyword-based personalization and the data-only ranking.

---

## Quick Start (CLI)

```bash
dearnana \
  --address "Bellevue, WA 98008" \
  --budget 8000 \
  --condition "Mom has moderate dementia, needs memory care and mobility assistance" \
  --radius 25 \
  --top 5
```

**Flag reference:**

| Flag | Required | Description |
|------|----------|-------------|
| `--address` | Yes | US address or city/zip to search near |
| `--budget` | Yes | Monthly budget in dollars |
| `--condition` | Yes | Description of care needs — personalizes the ranking and the AI report |
| `--radius` | No | Search radius in miles (default: 50) |
| `--top` | No | Number of results to show (default: 5) |
| `--no-ai` | No | Skip AI recommendation, show ranked list only |

**Example output (real run, June 2026, abbreviated):**

```
Geocoding: Bellevue, WA 98008
  -> (47.5851, -122.1470) in WA
Personalizing for: dementia / memory care (long-stay antipsychotic use, ...);
  fall risk (falls with major injury, ...) — parsed via keyword matching
Fetching nursing homes in WA...
  -> 194 facilities found (2 not yet rated by CMS)
Fetching care quality measures for WA...
Ranking within 25.0 miles...

--- DearNana Top 5 ---

#1. COVENANT SHORES HEALTH CENTER
    9107 FORTUNA DRIVE, MERCER ISLAND, WA 98040
    3.0 mi | Score: 86.1/100 | CMS: 5/5 | Phone: 2063168042
    Chain: COVENANT LIVING (15 facilities, avg 4.3/5)
    long-stay antipsychotic use: 10.3% vs state median 14.0% (better than 75% of WA facilities)
    falls with major injury: 0.0% vs state median 2.3% (better than 100% of WA facilities)
```

(Facility data shown is from the CMS dataset at the time of the run and will change as CMS refreshes it.)

---

## Library Usage

DearNana is also importable as a Python library. The FastAPI backend uses this pattern:

```python
from dearnana import (
    build_measure_weights,
    compute_measure_benchmarks,
    geocode_address,
    parse_condition,
    rank_facilities,
    score_condition_match,
)
from dearnana.cms_client import fetch_facilities_by_state, fetch_mds_measures_by_state

lat, lng, state = geocode_address("Bellevue, WA 98008")
facilities = fetch_facilities_by_state(state)

# Optional: personalize the ranking with a needs profile
profile = parse_condition("moderate dementia, has fallen twice")
weights = build_measure_weights(profile)
mds = fetch_mds_measures_by_state(state)
benchmarks = compute_measure_benchmarks(mds)
condition_scores = {
    ccn: score_condition_match(m, weights, benchmarks) for ccn, m in mds.items()
}

ranked = rank_facilities(
    facilities, lat, lng, radius_miles=25, top_n=5,
    condition_scores=condition_scores,
)

for r in ranked:
    print(f"{r.facility.name}: {r.composite_score}/100")
```

All public-facing functions are importable directly from the `dearnana` package. No subprocess calls are required.

---

## How Scores Are Calculated

DearNana uses a weighted composite score (0–100) based entirely on public CMS data. Here's what goes into it:

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| Overall CMS Rating | 25% | CMS's own 1–5 star summary rating based on inspections, staffing, and quality measures |
| Health Inspection | 20% | Results of state health inspections — citations for care problems, medication errors, and safety issues |
| Staffing Quality | 20% | Blend of the CMS staffing star rating and actual nurse hours per resident per day vs. the 4.1 hrs/day minimum recommended by the 2001 CMS-commissioned staffing study |
| Staff Stability | 10% | Annual nursing staff turnover rate — high turnover often signals poor management and care continuity |
| Penalty History | 10% | Number of enforcement actions and total fines levied by CMS |
| Distance | 10% | Proximity to the address you searched — closer facilities score higher |
| Fire Safety | 5% | Whether the facility has full sprinkler coverage |

**Condition match (15%, when care needs are recognized):** Your `--condition` text is parsed into a needs profile (via a small AI call, or a built-in keyword matcher when no API key is set or `--no-ai` is used). Each need maps to CMS MDS clinical quality measures — e.g. dementia → long-stay antipsychotic medication rate and physical restraint use; fall risk → falls with major injury. Each facility's measures are scored against the **state percentile distribution** (lower is better for all tracked measures). When the condition component is active, the base weights above are scaled by 0.85 so all weights still sum to 100%. If no needs are recognized in the text, the ranking is identical to the base weights.

**Abuse flag:** If a facility has an active CMS abuse flag, 50 points are deducted from its score — this is treated as a near-disqualifying finding. When the needs profile includes a vulnerable population (dementia or mental health), the deduction increases to 60 points.

**Missing data:** Facilities with missing data for a component receive a neutral score (50) for that component. Facilities not yet rated by CMS (typically newer facilities) are included with neutral component scores and labeled "not yet rated".

**Ownership transparency (not scored):** Each facility's chain affiliation and the chain's average CMS ratings are shown alongside results. Warnings are flagged — not folded into the score, since chain averages aggregate the same star ratings already weighted above — when a facility belongs to a chain averaging ≤ 2.5 stars, changed ownership in the last 12 months, or carries CMS Special Focus status. For top picks, individual owners (name, role, percentage) from the CMS Ownership dataset are included in the report.

### Scoring details

- **Overall CMS Rating** maps the 1–5 star summary directly to 0–100 (5 stars = 100, 1 star = 20).
- **Staffing Quality** is a weighted blend: 60% from the CMS staffing star rating, 40% from actual nurse hours compared to 4.1 hrs/resident/day — the minimum recommended by the 2001 CMS-commissioned staffing study (the actual national average is lower, ~3.6 hrs). If only one part is reported, it is used alone.
- **Staff Stability** inverts the turnover rate against national reference points (~52% total nursing, ~50% RN — CMS staffing-data analyses report national means of roughly 53% and 52%). A facility at the reference point scores 50; a facility with 0% turnover scores 100.
- **Penalty History** starts at 100 and deducts 15 points per enforcement action, plus 5 points per $10,000 in total fines.
- **Distance** uses linear decay: 100 at 0 miles, 0 at the search radius boundary.
- **Fire Safety** gives 100 for full sprinkler coverage, 50 for partial, 0 for none, 50 if unreported.
- **Condition Match** scores each relevant MDS measure as `100 × (1 − state percentile)` and averages them by need weight. Measures with missing data, or with fewer than 20 reporting facilities in the state, score a neutral 50.

---

## Data Source

| Attribute | Detail |
|-----------|--------|
| Source | [CMS Provider Data Catalog](https://data.cms.gov/provider-data/topics/nursing-homes) |
| Datasets | Provider information (ratings, staffing, chain), MDS Quality Measures (clinical measures), Health Deficiencies, Penalties, Ownership |
| Updated | Monthly by CMS (per dataset metadata) |
| Coverage | All Medicare/Medicaid certified nursing homes in the US (~14,700 facilities as of mid-2026) |
| Cost data | State-level monthly medians for semi-private rooms from the [CareScout (Genworth) Cost of Care Survey 2024](https://www.carescout.com/cost-of-care) — **not** facility-specific pricing |
| Caching | API responses are cached for 24h under `~/.dearnana/cache` |

CMS does not publish per-facility pricing. Budget comparisons use state-level median costs as a rough proxy. Contact facilities directly for current rates. Many facilities accept Medicaid — contact them directly if your budget is below the state median.

---

## Disclaimer

DearNana is a decision-support tool, not a substitute for professional medical or legal advice. Always visit facilities in person, speak with staff, and consult with a healthcare professional before making placement decisions. See [DISCLAIMER.md](DISCLAIMER.md) for full details.

---

## Contributing

Issues and PRs are welcome. Before contributing changes to scoring weights or methodology, please read [DISCLAIMER.md](DISCLAIMER.md) for notes on data accuracy and known limitations. Scoring changes should include a rationale and a before/after comparison on a representative set of facilities.

---

## License

MIT — see [LICENSE](LICENSE)
