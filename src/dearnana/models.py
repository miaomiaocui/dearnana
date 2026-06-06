"""Data models for DearNana."""

from pydantic import BaseModel, Field


class UserInput(BaseModel):
    address: str
    latitude: float
    longitude: float
    state: str
    budget_monthly: float
    condition_description: str


class Facility(BaseModel):
    ccn: str
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    latitude: float | None = None
    longitude: float | None = None
    phone: str = ""
    ownership_type: str = ""
    number_of_beds: int = 0
    average_residents_per_day: float = 0.0
    overall_rating: int = 0
    health_inspection_rating: int = 0
    qm_rating: int = 0
    staffing_rating: int = 0
    total_nurse_staffing_hours: float = 0.0
    rn_staffing_hours: float = 0.0
    total_nursing_turnover: float | None = None
    rn_turnover: float | None = None
    number_of_fines: int = 0
    total_fines_dollars: float = 0.0
    number_of_penalties: int = 0
    abuse_icon: bool = False
    sprinkler_systems: str = ""
    in_hospital: bool = False
    continuing_care: bool = False
    special_focus_status: str = ""
    # Chain / ownership context (from CMS provider data)
    chain_name: str = ""
    chain_id: str = ""
    chain_facility_count: int | None = None
    chain_avg_overall: float | None = None
    chain_avg_health_inspection: float | None = None
    chain_avg_staffing: float | None = None
    chain_avg_qm: float | None = None
    changed_ownership_12mo: bool = False


class StateFacilities(BaseModel):
    """Parsed facilities for a state, with exclusion/quality counts."""

    facilities: list[Facility]
    excluded_no_location: int = 0
    unrated_count: int = 0


class RankedFacility(BaseModel):
    facility: Facility
    distance_miles: float
    composite_score: float
    score_breakdown: dict[str, float]
    deficiencies: list[dict] | None = None
    penalties: list[dict] | None = None
    ownership: list[dict] | None = None
    chain_warnings: list[str] = Field(default_factory=list)
    condition_details: list[dict] | None = None
