"use client";

import { useState } from "react";
import { NEED_CATEGORIES, SEVERITY } from "@/lib/types";

export interface SearchPayload {
  zip: string;
  budget: number;
  radius: number;
  topN: number;
  needs: { category: string; weight: number }[];
  filters: Record<string, boolean | number>;
}

const FILTERS: { key: string; label: string }[] = [
  { key: "excludeAbuse", label: "Hide abuse-flagged" },
  { key: "excludeSpecialFocus", label: "Hide CMS Special Focus" },
  { key: "sprinklerOnly", label: "Full sprinklers only" },
  { key: "independentOnly", label: "Independent only" },
];

export default function SearchForm({
  onSearch,
  loading,
}: {
  onSearch: (p: SearchPayload) => void;
  loading: boolean;
}) {
  const [zip, setZip] = useState("95113"); // pre-fill: downtown San Jose, CA
  const [budget, setBudget] = useState("8000");
  const [radius, setRadius] = useState("25");
  const [topN, setTopN] = useState("5");
  const [minStars, setMinStars] = useState("0");
  const [needs, setNeeds] = useState<Record<string, number>>({});
  const [filters, setFilters] = useState<Record<string, boolean>>({});
  const [locating, setLocating] = useState(false);

  const locate = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const r = await fetch("/api/reverse-zip", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
          });
          const d = await r.json();
          if (r.ok && d.zip) setZip(String(d.zip).slice(0, 5));
        } catch {
          /* leave ZIP editable on failure */
        }
        setLocating(false);
      },
      () => setLocating(false),
      { timeout: 10000, maximumAge: 600000 },
    );
  };

  const toggleNeed = (key: string) =>
    setNeeds((n) => {
      const next = { ...n };
      if (key in next) delete next[key];
      else next[key] = 0.7; // default moderate
      return next;
    });

  const zipValid = /^\d{5}$/.test(zip);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!zipValid) return;
    onSearch({
      zip,
      budget: parseFloat(budget) || 0,
      radius: parseFloat(radius) || 25,
      topN: parseInt(topN) || 5,
      needs: Object.entries(needs).map(([category, weight]) => ({ category, weight })),
      filters: { ...filters, minStars: parseInt(minStars) || 0 },
    });
  };

  return (
    <form className="panel" onSubmit={submit}>
      <div className="grid grid-2">
        <div className="field">
          <label htmlFor="zip">Your ZIP code</label>
          <div className="zip-wrap">
            <input
              id="zip"
              type="text"
              inputMode="numeric"
              pattern="\d{5}"
              maxLength={5}
              placeholder="e.g. 95113"
              value={zip}
              onChange={(e) => setZip(e.target.value.replace(/\D/g, "").slice(0, 5))}
              required
            />
            <button
              type="button"
              className="locate"
              onClick={locate}
              disabled={locating}
              title="Use my location"
              aria-label="Use my location"
            >
              {locating ? <span className="spin" style={{ margin: 0 }} /> : <span className="target" />}
            </button>
          </div>
          <span className="hint">5-digit US ZIP — we search outward from there.</span>
        </div>
        <div className="field">
          <label htmlFor="budget">Monthly budget</label>
          <input
            id="budget"
            type="number"
            min={0}
            step={500}
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            required
          />
          <span className="hint">In US dollars.</span>
        </div>
      </div>

      <div className="grid grid-3" style={{ marginTop: 18 }}>
        <div className="field">
          <label htmlFor="radius">Search radius (miles)</label>
          <input id="radius" type="number" min={1} value={radius} onChange={(e) => setRadius(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="topn">Results to show</label>
          <input id="topn" type="number" min={1} max={15} value={topN} onChange={(e) => setTopN(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="stars">Minimum CMS rating</label>
          <select id="stars" value={minStars} onChange={(e) => setMinStars(e.target.value)}>
            <option value="0">Any rating</option>
            <option value="3">3+ stars</option>
            <option value="4">4+ stars</option>
            <option value="5">5 stars only</option>
          </select>
        </div>
      </div>

      <div className="section-title">Care needs — personalizes the ranking (no AI)</div>
      <div className="chips">
        {NEED_CATEGORIES.map((c) => {
          const on = c.key in needs;
          return (
            <div key={c.key} className={`chip ${on ? "on" : ""}`} onClick={() => toggleNeed(c.key)}>
              {c.label}
              {on && (
                <span className="sev" onClick={(e) => e.stopPropagation()}>
                  {SEVERITY.map((s) => (
                    <button
                      key={s.key}
                      type="button"
                      className={needs[c.key] === s.weight ? "on" : ""}
                      onClick={() => setNeeds((n) => ({ ...n, [c.key]: s.weight }))}
                    >
                      {s.label}
                    </button>
                  ))}
                </span>
              )}
            </div>
          );
        })}
      </div>

      <div className="section-title">Filters (optional)</div>
      <div className="chips">
        {FILTERS.map((f) => {
          const on = !!filters[f.key];
          return (
            <div
              key={f.key}
              className={`chip ${on ? "on" : ""}`}
              onClick={() => setFilters((s) => ({ ...s, [f.key]: !s[f.key] }))}
            >
              {f.label}
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 26 }}>
        <button className="btn btn-primary" type="submit" disabled={loading || !zipValid}>
          {loading ? (
            <>
              <span className="spin" />
              Searching CMS data…
            </>
          ) : (
            "Find nursing homes"
          )}
        </button>
      </div>
    </form>
  );
}
