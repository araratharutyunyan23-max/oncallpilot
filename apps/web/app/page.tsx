"use client";

import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import {
  Citation,
  Handlers,
  Pending,
  resumeAgent,
  Source,
  Step,
  streamAgent,
  streamRag,
  Usage,
} from "../lib/agentClient";

type Mode = "ask" | "act";

const EXAMPLES: Record<Mode, string> = {
  ask: "Redis is at 95% memory and rejecting writes with OOM. What are the first mitigation steps?",
  act: "The api-deploy CI pipeline is red. Check it, then file an SRE incident ticket at priority P1.",
};

export default function Console() {
  const [mode, setMode] = useState<Mode>("act");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const cid = useRef<string | null>(null);
  const ac = useRef<AbortController | null>(null);

  // abort any in-flight stream when the console unmounts (e.g. navigating to
  // /dashboard mid-run) so the fetch/reader doesn't leak until the server closes
  useEffect(() => () => ac.current?.abort(), []);

  const handlers: Handlers = {
    onMeta: (c) => (cid.current = c),
    onToken: (t) => setAnswer((a) => a + t),
    onSources: (s) => setSources(s),
    onCitations: (c) => setCitations(c),
    onStep: (s) => setSteps((prev) => [...prev, s]),
    onPending: (p) => {
      setPending(p);
      cid.current = p.conversation_id;
    },
    onAnswer: (a) => setAnswer(a.text ?? ""),
    onUsage: (u) => setUsage(u),
    onError: (m) => setError(m),
    onDone: () => setBusy(false),
  };

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setSteps([]);
    setAnswer("");
    setSources([]);
    setCitations([]);
    setPending(null);
    setUsage(null);
    cid.current = null;
    setInput("");
    ac.current?.abort();
    const c = new AbortController();
    ac.current = c;
    if (mode === "ask") await streamRag(q, handlers, c.signal);
    else await streamAgent(q, handlers, c.signal);
  }, [input, busy, mode]);

  const decide = useCallback(
    async (decision: "approved" | "denied") => {
      if (!pending || !cid.current) return;
      const approvals: Record<string, string> = {};
      for (const a of pending.pending_actions) approvals[a.tool_call_id] = decision;
      setPending(null);
      setBusy(true);
      ac.current?.abort();
      const c = new AbortController();
      ac.current = c;
      await resumeAgent(cid.current, approvals, handlers, c.signal);
    },
    [pending],
  );

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 px-5 py-8">
      <Header mode={mode} setMode={setMode} disabled={busy} />

      <div className="flex items-stretch gap-2">
        <input
          aria-label="Incident or question"
          className="min-w-0 flex-1 rounded-md border border-border bg-surface2 px-3 py-2.5 text-sm outline-none placeholder:text-faint focus:border-accent/60"
          placeholder={mode === "act" ? "Describe an incident, or ask to act…" : "Ask about a runbook, alert, or incident…"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={busy}
        />
        <button
          className="rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-base disabled:opacity-40"
          onClick={send}
          disabled={busy || !input.trim()}
        >
          {busy ? "…" : mode === "act" ? "Run" : "Ask"}
        </button>
      </div>

      {!busy && !answer && steps.length === 0 && (
        <button
          className="self-start text-xs text-faint hover:text-muted"
          onClick={() => setInput(EXAMPLES[mode])}
        >
          try an example →
        </button>
      )}

      {error && (
        <div className="rounded-md border border-p1/40 bg-p1/10 px-3 py-2 text-sm text-p1">{error}</div>
      )}

      {mode === "act" && steps.length > 0 && <Trace steps={steps} />}

      {pending && <Approval pending={pending} busy={busy} onDecide={decide} />}

      {answer && <Answer text={answer} citations={citations} />}

      {(sources.length > 0 || citations.length > 0) && (
        <Sources sources={sources} citations={citations} />
      )}

      {usage && <UsageBar usage={usage} />}

      {busy && steps.length === 0 && !answer && (
        <div className="text-xs text-faint">working…</div>
      )}
    </main>
  );
}

function Header({ mode, setMode, disabled }: { mode: Mode; setMode: (m: Mode) => void; disabled: boolean }) {
  return (
    <header className="flex items-center justify-between border-b border-border pb-3">
      <div className="flex items-baseline gap-2">
        <span className="h-2 w-2 rounded-full bg-accent" />
        <h1 className="text-lg font-semibold tracking-tight">OncallPilot</h1>
        <span className="text-xs text-faint">SRE on-call assistant</span>
      </div>
      <div className="flex items-center gap-3">
        <Link href="/dashboard" className="text-xs text-muted hover:text-fg">
          metrics →
        </Link>
        <div className="flex rounded-md border border-border p-0.5 text-xs">
          {(["ask", "act"] as Mode[]).map((m) => (
            <button
              key={m}
              disabled={disabled}
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
              className={`rounded px-2.5 py-1 ${mode === m ? "bg-surface text-fg" : "text-muted"} disabled:opacity-50`}
            >
              {m === "ask" ? "Ask" : "Act"}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

function stepView(s: Step): { icon: string; tone: string; body: ReactNode } {
  if (s.node === "retrieve")
    return { icon: "⌕", tone: "text-muted", body: <>retrieved <span className="text-faint">{(s.sources || []).length} chunks</span></> };
  if (s.node === "decide" && s.action === "tools")
    return { icon: "→", tone: "text-accent", body: <>decide → call <span className="font-mono">{(s.calls || []).join(", ")}</span></> };
  if (s.node === "decide")
    return { icon: "→", tone: "text-muted", body: <>decide → compose answer</> };
  if (s.node === "tool_exec") {
    const denied = s.result === "denied";
    return {
      icon: denied ? "✕" : "✓",
      tone: denied ? "text-p1" : "text-ok",
      body: <><span className="font-mono">{s.tool}</span> <span className="text-faint">{s.result}</span></>,
    };
  }
  if (s.node === "human_approval") return { icon: "⏸", tone: "text-p2", body: <>approval recorded</> };
  if (s.node === "respond") return { icon: "●", tone: "text-muted", body: <>done</> };
  return { icon: "·", tone: "text-faint", body: s.node };
}

function Trace({ steps }: { steps: Step[] }) {
  return (
    <section className="rounded-md border border-border bg-surface">
      <div className="border-b border-border px-3 py-2 text-xs uppercase tracking-wider text-faint">agent trace</div>
      <ol className="divide-y divide-border/60">
        {steps.map((s, i) => {
          const v = stepView(s);
          return (
            <li key={i} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className={`w-4 text-center ${v.tone}`}>{v.icon}</span>
              <span>{v.body}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Approval({ pending, busy, onDecide }: { pending: Pending; busy: boolean; onDecide: (d: "approved" | "denied") => void }) {
  const approveRef = useRef<HTMLButtonElement>(null);
  // the component only mounts when an approval is pending, so focus on mount
  // moves the operator straight to the decision without a blind tab hunt
  useEffect(() => {
    approveRef.current?.focus();
  }, []);
  return (
    <section
      role="alertdialog"
      aria-modal="true"
      aria-label="Approval required — destructive action"
      className="rounded-md border border-p2/50 bg-p2/5"
    >
      <div className="flex items-center gap-2 border-b border-p2/30 px-3 py-2 text-xs uppercase tracking-wider text-p2">
        <span><span aria-hidden="true">⏸</span> approval required — destructive action</span>
      </div>
      <div className="space-y-2 px-3 py-3">
        {pending.pending_actions.map((a) => (
          <div key={a.tool_call_id} className="text-sm">
            <div className="font-mono text-accent">{a.name}</div>
            <div className="text-muted">{a.preview}</div>
            <pre className="mt-1 overflow-x-auto rounded bg-surface2 px-2 py-1 font-mono text-xs text-faint">
              {JSON.stringify(a.args, null, 2)}
            </pre>
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button
            ref={approveRef}
            className="rounded-md bg-ok px-3 py-1.5 text-sm font-medium text-base disabled:opacity-40"
            onClick={() => onDecide("approved")}
            disabled={busy}
          >
            Approve
          </button>
          <button
            className="rounded-md border border-p1/50 px-3 py-1.5 text-sm font-medium text-p1 disabled:opacity-40"
            onClick={() => onDecide("denied")}
            disabled={busy}
          >
            Deny
          </button>
        </div>
      </div>
    </section>
  );
}

function Answer({ text, citations }: { text: string; citations: Citation[] }) {
  return (
    <section className="rounded-md border border-border bg-surface px-4 py-3">
      <div className="whitespace-pre-wrap text-sm leading-relaxed">{text}</div>
      {citations.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {citations.map((c, i) => (
            <span
              key={i}
              title={c.cited_text}
              className="rounded border border-accent/30 bg-accent/10 px-1.5 py-0.5 font-mono text-[11px] text-accent"
            >
              {i + 1} {c.slug}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function Sources({ sources, citations }: { sources: Source[]; citations: Citation[] }) {
  const items = citations.length > 0 ? citations : sources;
  return (
    <section className="rounded-md border border-border bg-surface2 px-3 py-2">
      <div className="mb-1 text-xs uppercase tracking-wider text-faint">
        {citations.length > 0 ? "citations" : "retrieved sources"}
      </div>
      <ul className="space-y-1 text-xs">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-faint">{citations.length > 0 ? `${i + 1}` : "·"}</span>
            <span className="font-mono text-muted">{it.slug}</span>
            {"cited_text" in it && it.cited_text && (
              <span className="truncate text-faint">— {it.cited_text}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function UsageBar({ usage }: { usage: Usage }) {
  return (
    <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-faint">
      {usage.model && <span className="font-mono text-muted">{usage.model}</span>}
      <span>in {usage.tokens_in ?? 0} / out {usage.tokens_out ?? 0} tok</span>
      {usage.cache_read ? <span>cache {usage.cache_read}</span> : null}
      <span className="text-accent">${(usage.cost_usd ?? 0).toFixed(4)}</span>
    </footer>
  );
}
