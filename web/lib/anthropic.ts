// Browser-direct Anthropic call. The user's key is used HERE, in the browser,
// and sent ONLY to api.anthropic.com — never to the DearNana server. The CSP
// (connect-src 'self' https://api.anthropic.com) guarantees this fetch can't be
// redirected to any other host.

export async function generateAiReport(
  apiKey: string,
  prompt: string,
  model: string,
  maxTokens: number,
): Promise<string> {
  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey.trim(),
      "anthropic-version": "2023-06-01",
      // Required to call the API from a browser with the user's own key.
      "anthropic-dangerous-direct-browser-access": "true",
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      messages: [{ role: "user", content: prompt }],
    }),
  });

  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const err = await resp.json();
      detail = err?.error?.message || detail;
    } catch {
      /* ignore */
    }
    if (resp.status === 401) {
      throw new Error("Anthropic rejected the key (401). Check that it's valid and active.");
    }
    if (resp.status === 429) {
      throw new Error("Anthropic rate limit or insufficient credit (429). Try again shortly.");
    }
    throw new Error(`Anthropic API error: ${detail}`);
  }

  const data = await resp.json();
  const text = (data?.content || [])
    .filter((b: { type: string }) => b.type === "text")
    .map((b: { text: string }) => b.text)
    .join("\n")
    .trim();
  return text || "(The model returned an empty response.)";
}
