# DearNana — Web UI

A friendly, free web front end for [DearNana](https://pypi.org/project/dearnana/).
Next.js (App Router) for the UI + a single **Python serverless function**
(`api/search.py`) that reuses the published `dearnana` library for the entire
search/ranking pipeline. Designed to deploy to **Vercel's free Hobby tier**.

## How it works

- **`api/search.py`** does all the non-AI work — geocode, fetch CMS data, filter,
  rank, enrich, and build the rule-based report, comparison table, and CSV/HTML.
  It also returns a ready-to-send Anthropic prompt. It **never** receives the
  user's API key.
- The **browser** renders everything. If the user opts into the AI report, their
  browser calls `api.anthropic.com` **directly** with their own key — the key
  never touches our server (see `lib/anthropic.ts` and the CSP in
  `next.config.mjs`). The whole tool works with no key at all.

## Local development

`npm run dev` alone only runs the Next.js frontend — the Vercel Python function
(`/api/search`) isn't served, so searches 404. Two easy ways to run the full
stack locally:

**Option A — no Vercel CLI (recommended).** Run the Python API and the frontend
in two terminals; a dev-only rewrite in `next.config.mjs` proxies `/api/search`
to the local API:

```bash
pip install dearnana zipcodes      # once
python dev_api.py                  # terminal 1 → API on :8001

npm install                        # once
npm run dev                        # terminal 2 → UI on http://localhost:3000
```

**Option B — Vercel CLI** (emulates production exactly):

```bash
npm i -g vercel && vercel dev      # UI + function at http://localhost:3000
```

Or exercise the pipeline directly, no server:

```bash
DEARNANA_CACHE_DIR=/tmp/dn python -c "import sys; sys.path.insert(0,'api'); \
  from search import run_search; print(run_search({'zip':'98008','budget':8000}).keys())"
```

## Deploy to Vercel (free)

1. Push this repo to GitHub (already done for DearNana).
2. In Vercel, **New Project → import the repo**, and set **Root Directory = `web`**.
3. Deploy. Vercel auto-detects Next.js and the `api/*.py` Python function and
   gives you a `*.vercel.app` URL with HTTPS. No server-side secrets are needed
   (there is no server-side API key).

The function pins `dearnana==0.1.1` in `requirements.txt`; bump that when the
library is updated.

## Security model (BYO key)

- The key lives only in the browser tab (`sessionStorage`), is sent only to
  Anthropic, and is never stored or logged by us.
- `connect-src 'self' https://api.anthropic.com` in the CSP means an injected
  script could not exfiltrate the key to a third-party host.
- See `../DISCLAIMER.md` §4a for the full hosted-app data-flow statement.

## Abuse protection

Built in, no setup:

- Volumetric DDoS is absorbed by Vercel's network/CDN (all plans). Toggle
  **Attack Challenge Mode** in the Vercel dashboard during an active attack.
- `/api/search` rejects oversized bodies (413), non-same-origin browser calls
  (403), and caps free-text + list inputs that reach the AI prompt.
- The advisor prompt treats CMS text as untrusted data (control chars stripped;
  explicit "ignore embedded instructions" guard) — and the LLM call is
  browser-direct with the user's own key, so there's no shared server-side
  model to attack.

Optional — per-IP rate limiting + a shared CMS cache (recommended for public
deployments). Both activate only when these env vars are set, and **fail open**
(a limiter/cache outage never blocks searches):

1. Create a free Redis at [upstash.com](https://upstash.com) (Redis → Create database).
2. In Vercel → Project → Settings → Environment Variables, add:
   - `UPSTASH_REDIS_REST_URL`
   - `UPSTASH_REDIS_REST_TOKEN`
   - *(optional)* `SEARCH_RATE_LIMIT` (default 15) and `SEARCH_RATE_WINDOW` seconds (default 60)
3. Redeploy. You now get ~15 searches/min/IP (HTTP 429 over that) and per-state
   CMS data cached for 24h (faster + far less load on the CMS API).
