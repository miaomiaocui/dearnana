"""Unit tests for geocode state parsing (no network calls)."""

from dearnana.geocode import _parse_state_from_address, STATE_ABBREVS


def test_parse_state_abbreviation():
    """Address with 2-letter state abbreviation should return that abbreviation."""
    result = _parse_state_from_address("Seattle, WA 98008")
    assert result == "WA"


def test_parse_state_full_name():
    """Address with full state name should return the correct abbreviation."""
    result = _parse_state_from_address("Portland, Oregon")
    assert result == "OR"


def test_parse_state_no_match():
    """Address with no recognizable state should return None."""
    result = _parse_state_from_address("Somewhere Unknown")
    assert result is None


def test_parse_state_abbreviation_case():
    """Lowercase 'wa' should NOT be matched as a state abbreviation.

    The regex requires uppercase ([A-Z]{2}), so lowercase input
    must not produce a match via abbreviation. STATE_ABBREVS only
    contains uppercase strings.
    """
    # Verify all abbreviations in STATE_ABBREVS are uppercase
    for abbrev in STATE_ABBREVS:
        assert abbrev == abbrev.upper(), f"STATE_ABBREVS contains lowercase: {abbrev!r}"

    # An address with only lowercase 'wa' should not match via abbreviation path
    # (It would only match if "washington" appears as well)
    result = _parse_state_from_address("somewhere in wa 98001")
    # lowercase 'wa' doesn't match [A-Z]{2} regex — no match via abbreviation
    # and 'wa' as full name doesn't exist in US_STATES (key is 'washington')
    assert result is None, f"Expected None for lowercase 'wa' but got {result!r}"


def test_directional_not_mistaken_for_state():
    """Street directionals like 'NE' must not be parsed as Nebraska."""
    result = _parse_state_from_address("1035 116th Ave NE, Bellevue, WA 98004")
    assert result == "WA"


def test_directional_without_zip():
    """The last valid abbreviation wins when no comma/zip anchors exist."""
    result = _parse_state_from_address("1035 116th Ave NE Bellevue WA")
    assert result == "WA"


def test_state_before_zip_anywhere():
    result = _parse_state_from_address("OR 97201 is the area we're looking at")
    assert result == "OR"


def test_comma_state_at_end():
    result = _parse_state_from_address("Portland, OR")
    assert result == "OR"
