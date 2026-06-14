// Mirrors the JSON returned by /api/search (dearnana RankedFacility.model_dump()).

export interface Facility {
  ccn: string;
  name: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  phone: string;
  overall_rating: number;
  health_inspection_rating: number;
  staffing_rating: number;
  qm_rating: number;
  total_nursing_turnover: number | null;
  number_of_penalties: number;
  total_fines_dollars: number;
  abuse_icon: boolean;
  special_focus_status: string;
  chain_name: string;
  chain_facility_count: number | null;
  chain_avg_overall: number | null;
}

export interface ConditionDetail {
  label: string;
  value: number | null;
  state_median: number | null;
  percentile: number | null;
}

export interface Deficiency {
  date: string;
  category: string;
  description: string;
  severity: string;
}

export interface RankedFacility {
  facility: Facility;
  distance_miles: number;
  composite_score: number;
  score_breakdown: Record<string, number>;
  condition_details: ConditionDetail[] | null;
  deficiencies: Deficiency[] | null;
  penalties: Record<string, unknown>[] | null;
  chain_warnings: string[];
}

export interface SearchResult {
  query: {
    address: string;
    state: string;
    budget: number;
    radius: number;
    topN: number;
    needs: string[];
    filterNotes: string[];
  };
  facilities: RankedFacility[];
  reportMarkdown: string;
  comparisonMarkdown: string;
  csv: string;
  html: string;
  budgetNote: string;
  ai: { advisorPrompt: string; model: string; maxTokens: number };
}

export const NEED_CATEGORIES: { key: string; label: string }[] = [
  { key: "dementia", label: "Dementia / memory care" },
  { key: "fall_risk", label: "Fall risk" },
  { key: "mobility", label: "Mobility" },
  { key: "skin_integrity", label: "Skin integrity / wound care" },
  { key: "mental_health", label: "Mental health" },
  { key: "continence", label: "Continence / urinary care" },
  { key: "weight_nutrition", label: "Weight & nutrition" },
];

// mild / moderate / primary -> weight (matches dearnana questionnaire.py)
export const SEVERITY: { key: string; label: string; weight: number }[] = [
  { key: "mild", label: "Mild", weight: 0.4 },
  { key: "moderate", label: "Moderate", weight: 0.7 },
  { key: "primary", label: "Primary concern", weight: 1.0 },
];
