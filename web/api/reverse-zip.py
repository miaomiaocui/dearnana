"""Vercel Python function: nearest US ZIP for a lat/lng — fully offline.

Powers the search form's "use my location" button. Browser geolocation gives
lat/lng; this returns the nearest ZIP centroid from the bundled `zipcodes`
dataset. No external geocoding service, no key.
"""

import json
from http.server import BaseHTTPRequestHandler

import zipcodes

# Build the point list once per cold start.
_POINTS = [
    (float(z["lat"]), float(z["long"]), z["zip_code"], z.get("city", ""), z.get("state", ""))
    for z in zipcodes.list_all()
    if z.get("lat") and z.get("long")
]


def _nearest(lat: float, lng: float):
    best = None
    best_d = float("inf")
    for la, lo, zc, city, state in _POINTS:
        d = (la - lat) ** 2 + (lo - lng) ** 2
        if d < best_d:
            best_d = d
            best = (zc, city, state)
    return best


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
            if length > 1024:
                return self._send(413, {"error": "Request too large."})
            p = json.loads(self.rfile.read(length) or b"{}")
            lat, lng = float(p["lat"]), float(p["lng"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return self._send(400, {"error": "lat and lng are required numbers."})
        found = _nearest(lat, lng)
        if not found:
            return self._send(404, {"error": "No ZIP found near that location."})
        zc, city, state = found
        self._send(200, {"zip": zc, "city": city, "state": state})
