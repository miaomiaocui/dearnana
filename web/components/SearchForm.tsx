"use client";

import { useState } from "react";
import { NEED_CATEGORIES, SEVERITY } from "@/lib/types";

export interface SearchPayload {
  address: string;
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
  const [address, setAddress] = useState("");
  const [budget, setBudget] = useState("8000");
  const [radius, setRadius] = useState("25");
  const [topN, setTopN] = useState("5");
  const [minStars, setMinStars] = useState("0");
  const [needs, setNeeds] = useState<Record<string, number>>({});
  const [filters, setFilters] = useState<Record<string, boolean>>({});

  const toggleNeed = (key: string) =>
    setNeeds((n) => {
      const next = { ...n };
      if (key in next) delete next[key];
      else next[key] = 0.7; // default moderate
      return next;
    });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch({
      address: address.trim(),
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
          <label htmlFor="addr">Where are you looking?</label>
          <input
            id="addr"
            type="text"
            placeholder="e.g. Bellevue, WA 98008"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            required
          />
          <span className="hint">A city, ZIP, or full address in the US.</span>
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
        <button className="btn btn-primary" type="submit" disabled={loading}>
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
