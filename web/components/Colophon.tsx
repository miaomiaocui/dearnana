/* Colophon band — a calm, first-party "more tools from us" signature. */

import type { ReactNode } from "react";

interface Tool {
  href: string;
  name: string;
  blurb: string;
  tile?: string; // accent tile color; omit when the icon brings its own background
  icon: ReactNode;
}

const TOOLS: Tool[] = [
  {
    href: "https://app.compfinder.app/",
    name: "CompFinder",
    blurb: "Overpaying property tax? Check public records in ~30s.",
    tile: "#ffffff",
    // eslint-disable-next-line @next/next/no-img-element
    icon: <img src="/compfinder-icon.svg" alt="" />,
  },
  {
    href: "https://www.escape-velocity.app/",
    name: "Escape Velocity",
    blurb: "Your FIRE number, and manifest what freedom from early retirement looks like.",
    // No tile — the app icon brings its own navy background.
    // eslint-disable-next-line @next/next/no-img-element
    icon: <img src="/escape-velocity-icon.png" alt="" className="fill" />,
  },
];

export default function Colophon() {
  return (
    <section className="colophon">
      <div className="colophon-head">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/nana-cream.png" alt="" className="colophon-mark" />
        <span className="colophon-eyebrow">P.S. — more tools from us</span>
      </div>
      <div className="colophon-grid">
        {TOOLS.map((t) => (
          <a key={t.href} href={t.href} target="_blank" rel="noopener noreferrer" className="colophon-link">
            <span className="colophon-tile" style={t.tile ? { background: t.tile } : undefined}>
              {t.icon}
            </span>
            <span className="colophon-text">
              <span className="colophon-name">{t.name}</span>
              <span className="colophon-blurb">{t.blurb}</span>
            </span>
            <span className="colophon-arrow">→</span>
          </a>
        ))}
      </div>
    </section>
  );
}
