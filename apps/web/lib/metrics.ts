export const BASE = process.env.NEXT_PUBLIC_AGENT_BASE_URL ?? "http://localhost:8000";

export type Summary = {
  count: number;
  total_cost_usd?: number;
  avg_cost_usd?: number;
  p50_latency_ms?: number;
  p95_latency_ms?: number;
  tokens_in?: number;
  tokens_out?: number;
  tool_calls?: number;
  cache_hit_rate?: number;
  error_rate?: number;
  models?: Record<string, number>;
};

export type Trace = {
  ts: number;
  endpoint: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  cache_read: number;
  cost_usd: number;
  latency_ms: number;
  tools: string[];
  paused: boolean;
  ok: boolean;
};

export async function fetchSummary(): Promise<Summary> {
  const r = await fetch(`${BASE}/api/metrics/summary`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function fetchRecent(limit = 60): Promise<Trace[]> {
  const r = await fetch(`${BASE}/api/metrics/recent?limit=${limit}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
