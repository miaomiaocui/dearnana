"use client";

import Link from "next/link";
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
  const [copied, setCopied] = useState(false);

  // No-key path: copy the ready-made prompt (homes + data) for any AI chat app.
  const copyForAnyApp = async () => {
    try {
      await navigator.clipboard.writeText(ai.advisorPrompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 4000);
    } catch {
      setError("Couldn't access the clipboard — try selecting and copying manually.");
    }
  };

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
    <section className={`panel ai-feature ${open ? "open" : ""}`} style={{ marginTop: 24 }}>
      <div className="eyebrow">AI analysis · your own key</div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
        <div>
          <h3>Surface the issues that matter</h3>
          <p className="pitch">
            The AI reads each home&apos;s citations, penalties, and quality data to flag the
            risks — and the questions to ask — for your needs.
          </p>
        </div>
        {!open && (
          <button className="btn btn-primary" onClick={() => setOpen(true)} style={{ whiteSpace: "nowrap" }}>
            Analyze with my key
          </button>
        )}
      </div>

      <Link href="/sample" className="sample-link" target="_blank" rel="noreferrer">
        See a sample report — dementia &amp; fall risk as primary concerns →
      </Link>

      <div className="byo-alt">
        <div className="byo-alt-row">
          <span className="byo-alt-label">No Anthropic key, or not sure how to get one?</span>
          <button className="byo-copy" onClick={copyForAnyApp} type="button">
            {copied ? "✓ Copied — paste into ChatGPT, Claude, or Gemini" : "Copy a prompt for any AI app"}
          </button>
        </div>
        <p className="byo-caveat">
          The prompt includes the homes above and their CMS data, so you can paste it into any AI chat.
          A couple of honest caveats, though: the rankings, scores, and red flags above were already
          computed by DearNana from live CMS records — a general AI app only sees the snapshot you paste,
          can&apos;t re-check anything, and may blend in outdated facts from its own training. Treat its
          reply as a plain-language summary of the data here, not new information, and verify with the
          facility. (The “use my key” option above runs this exact prompt for you — no copy-paste, and it
          won&apos;t get truncated.)
        </p>
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
                  Analyzing…
                </>
              ) : (
                "Generate analysis"
              )}
            </button>
            {apiKey && (
              <button className="btn btn-ghost" onClick={forget} type="button">
                Forget key
              </button>
            )}
          </div>

          <div className="privacy">
            <b>Your key stays in your browser</b> — sent only to Anthropic, never to us, and kept for this
            tab only. Tip: use a revocable key from{" "}
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
