"use client";

import type { RankedFacility, SearchResult } from "@/lib/types";

const SEVERE = new Set(["G", "H", "I", "J", "K", "L"]);

// Composite score components (from the ranker), in compact card-friendly labels.
const COMPONENT_LABELS: Record<string, string> = {
  overall_rating: "CMS rating",
  health_inspection: "inspections",
  staffing_quality: "staffing",
  staff_stability: "staff retention",
  penalty_history: "penalty record",
  distance: "proximity",
  safety: "fire safety",
  condition_match: "fit for needs",
};

function assessment(breakdown: Record<string, number>) {
  const items = Object.entries(breakdown)
    .filter(([k]) => k in COMPONENT_LABELS)
    .sort((a, b) => b[1] - a[1]);
  return {
    strong: items.filter(([, v]) => v >= 75).slice(0, 3),
    weak: items.filter(([, v]) => v < 45).slice(-2),
  };
}

function stars(n: number) {
  if (!n) return <span className="star-dim">not yet rated</span>;
  return (
    <span className="stars">
      {"★".repeat(n)}
      <span className="star-dim">{"★".repeat(5 - n)}</span>
    </span>
  );
}

function betterPhrase(pct: number | null) {
  if (pct === null) return "";
  const b = Math.round((1 - pct) * 100);
  if (b >= 100) return "better than nearly all";
  if (b <= 0) return "lower-ranked than most";
  return `better than ${b}%`;
}

function redFlags(r: RankedFacility): string[] {
  const f = r.facility;
  const out: string[] = [];
  if (f.abuse_icon) out.push("Flagged by CMS for abuse or neglect — investigate carefully.");
  if (f.special_focus_status) out.push(`CMS Special Focus: ${f.special_focus_status}.`);
  out.push(...(r.chain_warnings || []));
  if (f.number_of_penalties > 0) {
    const fines = f.total_fines_dollars ? ` totaling $${f.total_fines_dollars.toLocaleString()}` : "";
    out.push(`${f.number_of_penalties} federal penalt${f.number_of_penalties === 1 ? "y" : "ies"}${fines}.`);
  }
  const severe = (r.deficiencies || [])
    .filter((d) => SEVERE.has((d.severity || "").trim().toUpperCase()[0]))
    .sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  if (severe.length) out.push(`Actual-harm citation [${severe[0].severity}]: ${severe[0].description}`);
  return out;
}

function download(name: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Results({
  result,
  saved,
  onToggleSave,
  children,
}: {
  result: SearchResult;
  saved: Set<string>;
  onToggleSave: (r: RankedFacility) => void;
  children?: React.ReactNode;
}) {
  const { facilities, query } = result;

  return (
    <div>
      <div className="results-head">
        <h2>
          Top {facilities.length} near {query.city}, {query.state} {query.zip}
        </h2>
        <div className="toolbar">
          <button className="btn btn-ghost btn-sm" onClick={() => download("dearnana.csv", result.csv, "text/csv")}>
            Download CSV
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => download("dearnana.html", result.html, "text/html")}>
            Download HTML
          </button>
        </div>
      </div>
      {query.filterNotes.length > 0 && (
        <p className="notes">Filters removed: {query.filterNotes.join("; ")}.</p>
      )}
      {result.budgetNote && <div className="budget-note">{result.budgetNote}</div>}

      {facilities.map((r, i) => {
        const f = r.facility;
        const flags = redFlags(r);
        const measures = (r.condition_details || []).filter((d) => d.value !== null).slice(0, 3);
        const { strong, weak } = assessment(r.score_breakdown);
        return (
          <div key={f.ccn} className="card" style={{ animationDelay: `${i * 70}ms`, marginTop: 16 }}>
            <div className="card-top">
              <div className="rank">{i + 1}</div>
              <div style={{ flex: 1 }}>
                <h3>{f.name}</h3>
                <div className="addr">
                  {f.address}, {f.city}, {f.state} {f.zip_code} · {r.distance_miles} mi away
                </div>
                <div className="meta">
                  <span>CMS {stars(f.overall_rating)}</span>
                  <span>
                    Staffing <b>{f.staffing_rating ? `${f.staffing_rating}/5` : "—"}</b>
                  </span>
                  {f.total_nursing_turnover !== null && (
                    <span>
                      Turnover <b>{Math.round(f.total_nursing_turnover)}%</b>
                    </span>
                  )}
                  <span>
                    {f.chain_name ? (
                      <>
                        Chain <b>{f.chain_name}</b>
                      </>
                    ) : (
                      <b>Independent</b>
                    )}
                  </span>
                  {f.phone && (
                    <span>
                      ☎ <b>{f.phone}</b>
                    </span>
                  )}
                </div>
              </div>
              <div className="score">
                <div className="num">{r.composite_score}</div>
                <div className="lab">DearNana</div>
              </div>
            </div>

            {(strong.length > 0 || weak.length > 0) && (
              <div className="assess">
                {strong.length > 0 && (
                  <span>
                    <span className="tag good">Strong</span>
                    {strong.map(([k, v]) => `${COMPONENT_LABELS[k]} (${Math.round(v)})`).join(", ")}
                  </span>
                )}
                {weak.length > 0 && (
                  <span>
                    <span className="tag bad">Weak</span>
                    {weak.map(([k, v]) => `${COMPONENT_LABELS[k]} (${Math.round(v)})`).join(", ")}
                  </span>
                )}
              </div>
            )}

            {measures.length > 0 && (
              <div className="measures">
                {measures.map((d, j) => (
                  <div key={j} className="measure">
                    {d.label}: <b>{d.value?.toFixed(1)}%</b>
                    {d.state_median !== null ? (
                      <>
                        {" "}
                        vs state median {d.state_median.toFixed(1)}%{" "}
                        {d.percentile !== null && <span className="good">({betterPhrase(d.percentile)})</span>}
                      </>
                    ) : (
                      " (state benchmark unavailable)"
                    )}
                  </div>
                ))}
              </div>
            )}

            {flags.length > 0 && (
              <div className="flags">
                {flags.map((flag, j) => (
                  <div key={j} className="flag">
                    {flag}
                  </div>
                ))}
              </div>
            )}

            <div className="toolbar">
              <button className="btn btn-ghost btn-sm" onClick={() => onToggleSave(r)}>
                {saved.has(f.ccn) ? "★ Saved" : "☆ Save to watchlist"}
              </button>
            </div>
          </div>
        );
      })}

      {children}

      <div className="section-title" style={{ marginTop: 40 }}>
        Side by side
      </div>
      <div className="tablewrap">
        <table className="cmp">
          <thead>
            <tr>
              <th>#</th>
              <th>Facility</th>
              <th>Dist</th>
              <th>Score</th>
              <th>CMS</th>
              <th>Staffing</th>
              <th>Turnover</th>
              <th>Penalties</th>
              <th>Chain</th>
            </tr>
          </thead>
          <tbody>
            {facilities.map((r, i) => {
              const f = r.facility;
              return (
                <tr key={f.ccn}>
                  <td>{i + 1}</td>
                  <td className="name">{f.name}</td>
                  <td>{r.distance_miles} mi</td>
                  <td>
                    <b>{r.composite_score}</b>
                  </td>
                  <td>{f.overall_rating ? `${f.overall_rating}/5` : "n/r"}</td>
                  <td>{f.staffing_rating ? `${f.staffing_rating}/5` : "n/r"}</td>
                  <td>{f.total_nursing_turnover !== null ? `${Math.round(f.total_nursing_turnover)}%` : "—"}</td>
                  <td>{f.number_of_penalties || 0}</td>
                  <td>{f.chain_name || "Independent"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
