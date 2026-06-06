"""Geocode an address to (lat, lng, state) using Nominatim (free, no API key)."""

import re

from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
STATE_ABBREVS = set(US_STATES.values())


def _parse_state_from_address(address: str) -> str | None:
    """Extract a state abbreviation from the address string.

    Tries position-aware patterns first so street directionals like the "NE"
    in "1035 116th Ave NE" don't get mistaken for Nebraska:
    1. ", XX" (optionally followed by a zip) at the end of the string
    2. "XX" immediately before a zip code anywhere
    3. The last standalone 2-letter abbreviation in the string
    4. A full state name
    """
    match = re.search(r",\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*$", address)
    if match and match.group(1) in STATE_ABBREVS:
        return match.group(1)

    match = re.search(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b", address)
    if match and match.group(1) in STATE_ABBREVS:
        return match.group(1)

    candidates = [
        m.group(1)
        for m in re.finditer(r"\b([A-Z]{2})\b", address)
        if m.group(1) in STATE_ABBREVS
    ]
    if candidates:
        return candidates[-1]

    lower = address.lower()
    for name, abbrev in US_STATES.items():
        if name in lower:
            return abbrev
    return None


def geocode_address(address: str) -> tuple[float, float, str]:
    """Convert an address to (latitude, longitude, state_abbreviation).

    Uses Nominatim (OpenStreetMap) for geocoding. Falls back to parsing
    state from address string if geocoding fails.

    Raises ValueError if neither geocoding nor parsing succeeds.
    """
    geolocator = Nominatim(user_agent="dearnana/0.1.0", timeout=10)
    try:
        location = geolocator.geocode(address, country_codes="us", addressdetails=True)
    except (GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable):
        location = None  # fall through to string parsing

    if location and location.raw.get("address"):
        lat = location.latitude
        lng = location.longitude
        addr = location.raw["address"]
        # Nominatim returns state as full name or ISO code
        state_code = addr.get("ISO3166-2-lvl4", "")
        if state_code.startswith("US-"):
            state = state_code.split("-")[1]
        else:
            state_name = addr.get("state", "")
            state = US_STATES.get(state_name.lower(), "")
        if state:
            return lat, lng, state

    # Fallback: try parsing state from the input address
    parsed = _parse_state_from_address(address)
    if location and parsed:
        return location.latitude, location.longitude, parsed

    if parsed:
        raise ValueError(
            f"Could not geocode '{address}' but found state {parsed}. "
            "Please provide a more specific address."
        )

    raise ValueError(
        f"Could not geocode '{address}'. Please provide a valid US address."
    )
