// SSE client for the agent's streaming endpoints. EventSource can't POST, so we
// read the fetch body and parse SSE frames ("event: X\ndata: Y\n\n"). sse-starlette
// uses CRLF, so we normalize \r\n -> \n before splitting.

export type Source = { slug: string; title: string; heading_path?: string | null; chunk_id: number };
export type Citation = {
  slug: string;
  chunk_id: number;
  title: string;
  cited_text: string;
  doc_char_start?: number;
  doc_char_end?: number;
};
export type Step = {
  node: string;
  action?: string;
  calls?: string[];
  tool?: string;
  result?: string;
  sources?: string[];
  decided?: Record<string, string>;
};
export type PendingAction = {
  tool_call_id: string;
  name: string;
  args: Record<string, unknown>;
  preview: string;
};
export type Pending = { conversation_id: string; pending_actions: PendingAction[] };
export type Usage = {
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  cache_read?: number;
  cost_usd?: number;
};

export type Handlers = {
  onMeta?: (conversationId: string) => void;
  onToken?: (t: string) => void;
  onSources?: (s: Source[]) => void;
  onCitations?: (c: Citation[]) => void;
  onStep?: (s: Step) => void;
  onPending?: (p: Pending) => void;
  onAnswer?: (a: { text: string | null; sources?: Source[] }) => void;
  onUsage?: (u: Usage) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
};

const BASE = process.env.NEXT_PUBLIC_AGENT_BASE_URL ?? "http://localhost:8000";
const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_API_KEY;

function reqHeaders(): Record<string, string> {
  const h: Record<string, string> = { "content-type": "application/json" };
  if (DEMO_KEY) h["x-demo-key"] = DEMO_KEY;
  return h;
}

async function streamSSE(url: string, body: unknown, h: Handlers, signal?: AbortSignal): Promise<void> {
  let res: Response;
  try {
    res = await fetch(url, { method: "POST", headers: reqHeaders(), body: JSON.stringify(body), signal });
  } catch (e) {
    h.onError?.(e instanceof Error ? e.message : "network error");
    h.onDone?.();
    return;
  }
  if (!res.ok || !res.body) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      msg = (j.error ?? j.detail ?? msg) as string;
    } catch {
      /* not json */
    }
    h.onError?.(msg);
    h.onDone?.();
    return;
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      dispatch(buf.slice(0, idx), h);
      buf = buf.slice(idx + 2);
    }
  }
  if (buf.trim()) dispatch(buf, h);
}

function dispatch(frame: string, h: Handlers): void {
  let ev = "message";
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) ev = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  const raw = data.join("\n");
  const j = (): any => {
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  };
  switch (ev) {
    case "meta": {
      const d = j();
      if (d?.conversation_id) h.onMeta?.(d.conversation_id);
      break;
    }
    case "token": {
      const d = j();
      if (d?.text != null) h.onToken?.(d.text);
      break;
    }
    case "sources": {
      const d = j();
      if (Array.isArray(d)) h.onSources?.(d);
      break;
    }
    case "citations": {
      const d = j();
      if (Array.isArray(d)) h.onCitations?.(d);
      break;
    }
    case "step": {
      const d = j();
      if (d) h.onStep?.(d);
      break;
    }
    case "pending_action": {
      const d = j();
      if (d) h.onPending?.(d);
      break;
    }
    case "answer": {
      const d = j();
      if (d) h.onAnswer?.(d);
      break;
    }
    case "usage": {
      const d = j();
      if (d) h.onUsage?.(d);
      break;
    }
    case "error": {
      const d = j();
      h.onError?.(d?.message ?? raw);
      break;
    }
    case "done":
      h.onDone?.();
      break;
  }
}

export function streamRag(query: string, h: Handlers, signal?: AbortSignal): Promise<void> {
  return streamSSE(`${BASE}/rag`, { query }, h, signal);
}

export function streamAgent(query: string, h: Handlers, signal?: AbortSignal): Promise<void> {
  return streamSSE(`${BASE}/agent`, { query }, h, signal);
}

export function resumeAgent(
  conversationId: string,
  approvals: Record<string, string>,
  h: Handlers,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE(`${BASE}/agent/${conversationId}/resume`, { approvals }, h, signal);
}
