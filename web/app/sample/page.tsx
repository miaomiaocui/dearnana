"use client";

import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SAMPLE_REPORT } from "@/lib/sampleReport";

export default function SamplePage() {
  return (
    <main className="wrap" style={{ paddingBottom: 60 }}>
      <header className="lockup">
        <Link href="/" className="badge" aria-label="DearNana home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/nana-cream.png" alt="" className="badge-mark" />
        </Link>
        <Link href="/" className="wordmark">
          DearNana
        </Link>
        <span className="tagline">Sample AI report</span>
      </header>

      <section className="hero">
        <h1 className="headline" style={{ fontSize: "clamp(32px, 5vw, 48px)" }}>
          See what the AI adds.
        </h1>
        <p className="subhead" style={{ maxWidth: 640 }}>
          A real example of the AI analysis — generated for a San Francisco search (ZIP 94105) with{" "}
          <strong>dementia / memory care</strong> and <strong>fall risk</strong> as primary concerns.
          The free results give you the rankings and data; with your own Anthropic key, the AI reads
          each home&apos;s citations, penalties, and quality measures to surface the risks and questions
          that matter for those needs.
        </p>
        <div style={{ marginTop: 22 }}>
          <Link href="/" className="btn btn-primary">
            ← Run your own search
          </Link>
        </div>
      </section>

      <article className="panel prose">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{SAMPLE_REPORT}</ReactMarkdown>
      </article>

      <footer>
        This sample is illustrative; facility data changes as CMS refreshes it. DearNana is a
        decision-support tool, not medical or legal advice — always visit in person and confirm
        details directly with each facility.
      </footer>
    </main>
  );
}
