# Contributing to DearNana

Thanks for helping make nursing home data more transparent. Issues and PRs are welcome.

## Development setup

```bash
git clone https://github.com/miaomiaocui/dearnana
cd dearnana
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.11+.

## Running tests

```bash
pytest
```

**No API key is needed for the test suite** — all Anthropic API calls are mocked. The tests also make no network calls to CMS or Nominatim.

To smoke-test against live data without any API cost:

```bash
dearnana --address "Bellevue, WA 98008" --budget 8000 \
  --condition "moderate dementia, has fallen twice" --no-ai
```

CMS responses are cached for 24h under `~/.dearnana/cache`, so repeat runs are fast and gentle on the API.

## Bringing your own API key

The AI features (condition parsing + recommendation report) require an Anthropic API key. Get one at [console.anthropic.com](https://console.anthropic.com) and either export `ANTHROPIC_API_KEY` or copy `.env.example` to `.env`. Everything else works without one.

## Changing the scoring methodology

Scoring changes affect real families making high-stakes decisions, so they get extra scrutiny. A PR that touches `WEIGHTS`, the per-component scorers in `ranker.py`, the condition→measure map in `condition.py`, or any benchmark constant must include:

1. **A rationale** — why is the new weighting/formula a better reflection of care quality? Cite evidence where possible (CMS technical docs, published research).
2. **A before/after comparison** on a representative set of facilities (one full state is a good unit — Washington is the convention used so far). Report: how many facilities changed score, the mean/min/max delta, and the facilities with the largest moves. A small script against the cached state file is fine.
3. **Updated documentation** — the README's "How Scores Are Calculated" section must stay in sync with the code.

Please also read [DISCLAIMER.md](DISCLAIMER.md) for known data-accuracy limitations before proposing changes.

## Code conventions

- Pure scoring logic lives in `ranker.py` and must stay LLM-free and network-free.
- All CMS API access goes through `cms_client.py` (retry helper + file cache).
- All LLM access goes through the provider layer in `llm.py` (Anthropic API or local Ollama); providers return `None` on failure so callers can fall back.
- New CLI behavior needs a test; LLM interactions are tested with mocks (`pytest-mock`).
- Anything user-facing should degrade gracefully without an API key.

## Releases (maintainers)

Publishing to PyPI uses GitHub Actions [trusted publishing](https://docs.pypi.org/trusted-publishers/) — no tokens are stored in the repo.

One-time setup: on pypi.org → your project (or "pending publisher" for the first release) → add a trusted publisher with repository `miaomiaocui/dearnana`, workflow `release.yml`, environment `pypi`.

To release:

1. Bump `version` in `pyproject.toml` and `__version__` in `src/dearnana/__init__.py`
2. Create a GitHub release with tag `vX.Y.Z`
3. The `release.yml` workflow builds the sdist/wheel and publishes automatically
