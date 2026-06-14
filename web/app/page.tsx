"use client";

import { useEffect, useState } from "react";
import SearchForm, { SearchPayload } from "@/components/SearchForm";
import Results from "@/components/Results";
import AIReportPanel from "@/components/AIReportPanel";
import type { RankedFacility, SearchResult } from "@/lib/types";

const WATCH_STORE = "dearnana_watchlist";

interface WatchItem {
  ccn: string;
  name: string;
  city: string;
  state: string;
  score: number;
  phone: string;
}

export default function Home() {
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [watch, setWatch] = useState<WatchItem[]>([]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(WATCH_STORE);
      if (raw) setWatch(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, []);

  const persistWatch = (items: WatchItem[]) => {
    setWatch(items);
    localStorage.setItem(WATCH_STORE, JSON.stringify(items));
  };

  const toggleSave = (r: RankedFacility) => {
    const f = r.facility;
    const exists = watch.some((w) => w.ccn === f.ccn);
    if (exists) {
      persistWatch(watch.filter((w) => w.ccn !== f.ccn));
    } else {
      persistWatch([
        ...watch,
        { ccn: f.ccn, name: f.name, city: f.city, state: f.state, score: r.composite_score, phone: f.phone },
      ]);
    }
  };

  const search = async (payload: SearchPayload) => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const resp = await fetch("/api/search", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      // The server may return a non-JSON page on a platform timeout/crash —
      // read text first so we never throw an opaque "Unexpected token" error.
      const raw = await resp.text();
      let data: SearchResult | { error?: string } | null = null;
      try {
        data = raw ? JSON.parse(raw) : null;
      } catch {
        data = null;
      }
      if (!resp.ok || !data) {
        const timedOut = resp.status === 504 || resp.status === 502 || data === null;
        throw new Error(
          (data && "error" in data && data.error) ||
            (timedOut
              ? "That search took too long — the first lookup for a large state can be slow. Please try again; the next attempt is usually much faster."
              : `Search failed (${resp.status}).`),
        );
      }
      setResult(data as SearchResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    }
  };

  const savedSet = new Set(watch.map((w) => w.ccn));

  return (
    <main className="wrap">
      <header className="hero">
        <div className="brand">
          <span className="brand-mark">DearNana</span>
          <span className="brand-tag">Public data · no ads · no referral fees</span>
        </div>
        <h1>
          Find a nursing home you can <em>trust</em>.
        </h1>
        <p className="lede">
          We rank every Medicare &amp; Medicaid certified nursing home near you on objective CMS quality data —
          personalized to your loved one&apos;s needs. Free, and it works entirely without AI.
        </p>
        <div className="assurances">
          <span className="assurance">No facility can pay to rank higher</span>
          <span className="assurance">Inspection, staffing &amp; penalty records</span>
          <span className="assurance">Your search never leaves with an ad network</span>
        </div>
      </header>

      {watch.length > 0 && (
        <div className="panel" style={{ marginBottom: 22 }}>
          <div className="section-title" style={{ margin: "0 0 10px" }}>
            Your watchlist ({watch.length})
          </div>
          <div className="chips">
            {watch.map((w) => (
              <span key={w.ccn} className="chip" title={`${w.city}, ${w.state} · ${w.phone}`}>
                {w.name} · {w.score}
                <button
                  type="button"
                  className="sev"
                  style={{ border: "none", background: "none", cursor: "pointer", color: "var(--rust)" }}
                  onClick={() => persistWatch(watch.filter((x) => x.ccn !== w.ccn))}
                  aria-label={`Remove ${w.name}`}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      <SearchForm onSearch={search} loading={loading} />

      {error && (
        <div className="panel" style={{ marginTop: 22 }}>
          <div className="error" style={{ margin: 0 }}>
            {error}
          </div>
        </div>
      )}

      {result && (
        <>
          <Results result={result} saved={savedSet} onToggleSave={toggleSave} />
          <AIReportPanel ai={result.ai} />
        </>
      )}

      <footer>
        DearNana ranks facilities from the{" "}
        <a href="https://data.cms.gov/provider-data/topics/nursing-homes" target="_blank" rel="noreferrer">
          CMS Provider Data Catalog
        </a>
        . It is a decision-support tool, not medical or legal advice — always visit in person and confirm
        current pricing and Medicaid acceptance directly with each facility.
      </footer>
    </main>
  );
}
