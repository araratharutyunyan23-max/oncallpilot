// Typed SSE client for the agent's POST /chat stream.
// EventSource can't POST, so we read the fetch body stream and parse SSE frames
// ("event: <name>\ndata: <json>\n\n") by hand.

export type ChatHandlers = {
  onToken?: (t: string) => void;
  onUsage?: (u: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
};

const BASE =
  process.env.NEXT_PUBLIC_AGENT_BASE_URL ?? "http://localhost:8000";
const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_API_KEY;

export async function streamChat(
  query: string,
  conversationId: string | null,
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (DEMO_KEY) headers["x-demo-key"] = DEMO_KEY;

  let res: Response;
  try {
    res = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({ query, conversation_id: conversationId }),
      signal,
    });
  } catch (e) {
    handlers.onError?.(e instanceof Error ? e.message : "network error");
    return;
  }

  if (!res.ok || !res.body) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      msg = (j.error ?? j.detail ?? msg) as string;
    } catch {
      /* body was not json */
    }
    handlers.onError?.(msg);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) dispatch(frame, handlers);
  }
  if (buf.trim()) dispatch(buf, handlers);
}

function dispatch(frame: string, h: ChatHandlers): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  const data = dataLines.join("\n");
  if (!data && event === "message") return; // keep-alive comment / blank

  if (event === "token") {
    try {
      h.onToken?.(JSON.parse(data).text as string);
    } catch {
      /* ignore malformed */
    }
  } else if (event === "usage") {
    try {
      h.onUsage?.(JSON.parse(data) as Record<string, unknown>);
    } catch {
      /* ignore */
    }
  } else if (event === "error") {
    try {
      h.onError?.(JSON.parse(data).message as string);
    } catch {
      h.onError?.(data);
    }
  } else if (event === "done") {
    h.onDone?.();
  }
}
