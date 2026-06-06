"""Shared pytest fixtures for dearnana tests."""

import pytest

from dearnana.models import Facility


@pytest.fixture
def sample_facility() -> Facility:
    """A realistic Facility for use in scoring tests."""
    return Facility(
        ccn="123456",
        name="Test Nursing Home",
        address="123 Main St",
        city="Seattle",
        state="WA",
        zip_code="98001",
        latitude=47.6,
        longitude=-122.3,
        overall_rating=4,
        health_inspection_rating=4,
        staffing_rating=3,
        total_nurse_staffing_hours=4.5,
        total_nursing_turnover=45.0,
        rn_turnover=40.0,
        number_of_penalties=0,
        total_fines_dollars=0.0,
        abuse_icon=False,
        sprinkler_systems="Yes",
    )
