"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { generateAiReport } from "@/lib/anthropic";
import type { SearchResult } from "@/lib/types";

const KEY_STORE = "dearnana_anthropic_key";

export default function AIReportPanel({ ai }: { ai: SearchResult["ai"] }) {
  const [open, setOpen] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [report, setReport] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Restore a key the user chose to keep for THIS browser session only.
  useEffect(() => {
    const saved = sessionStorage.getItem(KEY_STORE);
    if (saved) setApiKey(saved);
  }, []);

  const run = async () => {
    setError("");
    setReport("");
    if (!apiKey.trim()) {
      setError("Paste an Anthropic API key first.");
      return;
    }
    setLoading(true);
    try {
      sessionStorage.setItem(KEY_STORE, apiKey.trim());
      const text = await generateAiReport(apiKey, ai.advisorPrompt, ai.model, ai.maxTokens);
      setReport(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The AI request failed.");
    } finally {
      setLoading(false);
    }
  };

  const forget = () => {
    sessionStorage.removeItem(KEY_STORE);
    setApiKey("");
    setReport("");
    setError("");
  };

  return (
    <section className={`panel ai-panel ${open ? "open" : ""}`} style={{ marginTop: 22 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ fontSize: 22 }}>Optional: an AI-written summary</h3>
          <p style={{ color: "var(--ink-soft)", margin: "6px 0 0", fontSize: 15 }}>
            Everything above is already complete. If you have an Anthropic API key, you can turn the data into
            a warm, plain-language report — using <b>your</b> key, with the model {ai.model}.
          </p>
        </div>
        {!open && (
          <button className="btn btn-ghost" onClick={() => setOpen(true)}>
            Use my Anthropic key
          </button>
        )}
      </div>

      {open && (
        <>
          <div className="keyrow" style={{ marginTop: 18 }}>
            <div className="field">
              <label htmlFor="key">Anthropic API key</label>
              <input
                id="key"
                type="password"
                placeholder="sk-ant-…"
                value={apiKey}
                autoComplete="off"
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
            <button className="btn btn-primary" onClick={run} disabled={loading}>
              {loading ? (
                <>
                  <span className="spin" />
                  Writing…
                </>
              ) : (
                "Generate report"
              )}
            </button>
            {apiKey && (
              <button className="btn btn-ghost" onClick={forget} type="button">
                Forget key
              </button>
            )}
          </div>

          <div className="privacy">
            <b>Your key stays in your browser.</b> It is sent <b>directly to Anthropic</b> over HTTPS and never
            to DearNana&apos;s servers — we never see it, store it, or log it. It is kept only for this browser tab
            (cleared when you close it, or with “Forget key”). For maximum safety, create a key you can revoke at{" "}
            <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
              console.anthropic.com
            </a>
            .
          </div>

          {error && <div className="error">{error}</div>}

          {report && (
            <div className="prose" style={{ marginTop: 22 }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
            </div>
          )}
        </>
      )}
    </section>
  );
}
