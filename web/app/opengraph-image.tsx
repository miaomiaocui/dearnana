import { readFileSync } from "fs";
import { join } from "path";
import { ImageResponse } from "next/og";

export const runtime = "nodejs";
export const alt = "DearNana — find a nursing home from public CMS data, not ads";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const dataUri = (p: string) =>
  `data:image/png;base64,${readFileSync(join(process.cwd(), p)).toString("base64")}`;

export default async function Image() {
  const news = readFileSync(join(process.cwd(), "app/og-newsreader.woff"));
  const markTerracotta = dataUri("public/nana-terracotta.png");
  const markCream = dataUri("public/nana-cream.png");

  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          position: "relative",
          overflow: "hidden",
          background: "#f3eee0",
          fontFamily: "Newsreader",
          color: "#2a241d",
        }}
      >
        {/* rocking-chair mark bleeding off the right, like the landing hero */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={markTerracotta} alt="" height={580} style={{ position: "absolute", right: -56, top: 60 }} />

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: "64px 80px",
            width: 770,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div
              style={{
                width: 66,
                height: 66,
                borderRadius: 17,
                background: "#b14a2c",
                display: "flex",
                alignItems: "flex-end",
                justifyContent: "center",
                overflow: "hidden",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={markCream} alt="" height={53} style={{ marginBottom: -1 }} />
            </div>
            <div style={{ fontSize: 42, fontWeight: 600 }}>DearNana</div>
          </div>

          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 94, fontWeight: 600, lineHeight: 0.98, letterSpacing: -2 }}>
              Find a nursing home.
            </div>
            <div style={{ fontSize: 30, color: "#5f574c", marginTop: 24, maxWidth: 600, lineHeight: 1.3 }}>
              Ranked from public CMS quality data — not ads, not referral fees. Free, and it works without AI.
            </div>
          </div>

          <div style={{ fontSize: 20, color: "#a99c89", letterSpacing: 4, textTransform: "uppercase" }}>
            Public data · No ads · No referral fees
          </div>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [{ name: "Newsreader", data: news, weight: 600, style: "normal" }],
    },
  );
}
