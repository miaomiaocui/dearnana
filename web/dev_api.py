"""Local dev server for the Python API.

`npm run dev` only serves the Next.js frontend — not the Vercel Python
functions. Run this alongside it so `/api/search` (port 8001) and
`/api/reverse-zip` (port 8002) work locally; the dev-only rewrites in
next.config.mjs proxy to these. Requires `pip install dearnana zipcodes`.

    python web/dev_api.py
"""

import importlib.util
import os
import sys
import threading
from http.server import HTTPServer

os.environ.setdefault("DEARNANA_CACHE_DIR", "/tmp/dearnana-cache")
_API = os.path.join(os.path.dirname(__file__), "api")
sys.path.insert(0, _API)

from search import handler as search_handler  # noqa: E402


def _load(fname: str, modname: str):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(_API, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reverse_zip = _load("reverse-zip.py", "reverse_zip")  # hyphenated filename


def _serve(port: int, h):
    HTTPServer(("127.0.0.1", port), h).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=_serve, args=(8002, reverse_zip.handler), daemon=True).start()
    print("DearNana dev API → search :8001 · reverse-zip :8002")
    _serve(8001, search_handler)
