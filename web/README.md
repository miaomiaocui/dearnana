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

Requires the [Vercel CLI](https://vercel.com/docs/cli) so the Next.js app and the
Python function run together:

```bash
npm install
npm i -g vercel        # if you don't have it
vercel dev             # serves the UI + /api/search at http://localhost:3000
```

(`npm run dev` alone runs only the Next.js side; the Python `/api/search`
endpoint needs `vercel dev`.)

You can also exercise the pipeline directly without the server:

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
