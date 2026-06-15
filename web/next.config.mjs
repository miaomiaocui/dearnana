import { fileURLToPath } from "url";
import { dirname } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */

// The one rule that actually protects the user's API key: outbound requests
// (fetch/XHR) may only go to our own origin or Anthropic. Even if markup were
// injected, the key could never be exfiltrated to an attacker-controlled host.
// Next.js dev mode needs eval() for React debugging/HMR; production never does,
// so only relax script-src in development and keep prod locked down.
const isDev = process.env.NODE_ENV !== "production";
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self' https://api.anthropic.com",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
];

const nextConfig = {
  turbopack: { root: __dirname },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  // In local dev, `npm run dev` doesn't run the Vercel Python function, so
  // proxy /api/search to a locally-run copy (web/dev_api.py). No effect in
  // production, where Vercel routes /api/search to the function directly.
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [
      { source: "/api/search", destination: "http://127.0.0.1:8001/api/search" },
      { source: "/api/reverse-zip", destination: "http://127.0.0.1:8002/api/reverse-zip" },
    ];
  },
};

export default nextConfig;
