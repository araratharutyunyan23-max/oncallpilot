"use client";

import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { fetchRecent, fetchSummary, Summary, Trace } from "../../lib/metrics";

// model tiers are ordinal (haiku < sonnet < opus by cost/capability) -> a single
// teal ramp, light->dark, not a categorical palette.
const MODEL_RAMP: Record<string, string> = {
  "claude-haiku-4-5": "#99F6E4",
  "claude-sonnet-5": "#2DD4BF",
  "claude-opus-4-8": "#0F766E",
  "claude-fable-5": "#134E4A",
  "-": "#5A6377",
};

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [recent, setRecent] = useState<Trace[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([fetchSummary(), fetchRecent()]);
      setSummary(s);
      setRecent(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load metrics");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const chrono = [...recent].reverse();

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-5 px-5 py-8">
      <header className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-baseline gap-2">
          <span className="h-2 w-2 rounded-full bg-accent" />
          <h1 className="text-lg font-semibold tracking-tight">Observability</h1>
          <span className="text-xs text-faint">cost · latency · tokens per request</span>
        </div>
        <Link href="/" className="text-xs text-muted hover:text-fg">
          ← console
        </Link>
      </header>

      {error && (
        <div className="rounded-md border border-p1/40 bg-p1/10 px-3 py-2 text-sm text-p1">
          {error} — is the agent running on :8000?
        </div>
      )}

      {(!summary || summary.count === 0) && !error && (
        <div className="text-sm text-faint">
          No requests recorded yet. Run a query in the{" "}
          <Link href="/" className="text-accent">
            console
          </Link>{" "}
          and this fills in.
        </div>
      )}

      {summary && summary.count > 0 && (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Tile label="requests" value={String(summary.count)} />
            <Tile label="total cost" value={`$${(summary.total_cost_usd ?? 0).toFixed(3)}`} />
            <Tile label="avg / req" value={`$${(summary.avg_cost_usd ?? 0).toFixed(4)}`} accent />
            <Tile label="p95 latency" value={`${((summary.p95_latency_ms ?? 0) / 1000).toFixed(1)}s`} />
            <Tile label="cache hit" value={`${Math.round((summary.cache_hit_rate ?? 0) * 100)}%`} />
          </section>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Panel title={`cost per request  ·  $${(summary.avg_cost_usd ?? 0).toFixed(4)} avg`}>
              <SparkBars
                values={chrono.map((t) => t.cost_usd)}
                color="#2DD4BF"
                fmt={(v) => `$${v.toFixed(4)}`}
              />
            </Panel>
            <Panel title={`latency per request  ·  p50 ${((summary.p50_latency_ms ?? 0) / 1000).toFixed(1)}s / p95 ${((summary.p95_latency_ms ?? 0) / 1000).toFixed(1)}s`}>
              <SparkBars
                values={chrono.map((t) => t.latency_ms)}
                color="#60A5FA"
                fmt={(v) => `${(v / 1000).toFixed(2)}s`}
              />
            </Panel>
          </section>

          <Panel title="model mix">
            <ModelMix models={summary.models ?? {}} />
          </Panel>

          <Panel title="recent requests">
            <RecentTable rows={recent} />
          </Panel>
        </>
      )}
    </main>
  );
}

function Tile({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wider text-faint">{label}</div>
      <div className={`mt-1 text-xl font-semibold tabular-nums ${accent ? "text-accent" : "text-fg"}`}>
        {value}
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-surface">
      <div className="border-b border-border px-3 py-2 text-xs uppercase tracking-wider text-faint">
        {title}
      </div>
      <div className="px-3 py-3">{children}</div>
    </section>
  );
}

function SparkBars({ values, color, fmt }: { values: number[]; color: string; fmt: (v: number) => string }) {
  if (values.length === 0) return <div className="text-xs text-faint">no data</div>;
  const max = Math.max(...values, 1e-9);
  const w = 100 / values.length;
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-16 w-full" role="img">
      {values.map((v, i) => {
        const h = Math.max(1.5, (v / max) * 38);
        return (
          <rect key={i} x={i * w + w * 0.15} y={40 - h} width={w * 0.7} height={h} rx={0.5} fill={color}>
            <title>{fmt(v)}</title>
          </rect>
        );
      })}
    </svg>
  );
}

function ModelMix({ models }: { models: Record<string, number> }) {
  const entries = Object.entries(models);
  const total = entries.reduce((a, [, n]) => a + n, 0) || 1;
  return (
    <div>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded">
        {entries.map(([m, n]) => (
          <div key={m} style={{ width: `${(n / total) * 100}%`, background: MODEL_RAMP[m] ?? "#5A6377" }} title={`${m}: ${n}`} />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {entries.map(([m, n]) => (
          <span key={m} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm" style={{ background: MODEL_RAMP[m] ?? "#5A6377" }} />
            <span className="font-mono text-muted">{m}</span>
            <span className="tabular-nums text-faint">{n}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function RecentTable({ rows }: { rows: Trace[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs tabular-nums">
        <thead className="text-faint">
          <tr className="[&>th]:px-2 [&>th]:py-1 [&>th]:font-normal">
            <th>endpoint</th>
            <th>model</th>
            <th className="text-right">in/out</th>
            <th className="text-right">$</th>
            <th className="text-right">latency</th>
            <th>tools</th>
            <th>status</th>
          </tr>
        </thead>
        <tbody className="[&>tr]:border-t [&>tr]:border-border/60 [&>tr>td]:px-2 [&>tr>td]:py-1.5">
          {rows.map((t, i) => (
            <tr key={i}>
              <td>
                <span className="rounded border border-border px-1.5 py-0.5 text-[11px] text-muted">
                  {t.endpoint}
                </span>
              </td>
              <td className="font-mono text-muted">{t.model}</td>
              <td className="text-right text-muted">
                {t.tokens_in}/{t.tokens_out}
              </td>
              <td className="text-right text-accent">${t.cost_usd.toFixed(4)}</td>
              <td className="text-right text-muted">{(t.latency_ms / 1000).toFixed(2)}s</td>
              <td className="font-mono text-faint">{t.tools.join(", ") || "—"}</td>
              <td>
                {t.paused ? (
                  <span className="text-p2">paused</span>
                ) : t.ok ? (
                  <span className="text-ok">ok</span>
                ) : (
                  <span className="text-p1">error</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
