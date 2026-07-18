"use client";

import { useRef, useState } from "react";
import { streamChat } from "../lib/agentClient";

export default function Home() {
  const [input, setInput] = useState("");
  const [answer, setAnswer] = useState("");
  const [usage, setUsage] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const convId = useRef<string>(
    typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : "dev",
  );

  async function send() {
    const q = input.trim();
    if (!q || busy) return;
    setBusy(true);
    setAnswer("");
    setUsage(null);
    setError(null);
    setInput("");
    await streamChat(q, convId.current, {
      onToken: (t) => setAnswer((a) => a + t),
      onUsage: (u) => setUsage(u),
      onError: (m) => setError(m),
      onDone: () => setBusy(false),
    });
    setBusy(false);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-4 px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold">OncallPilot</h1>
        <p className="text-sm text-neutral-500">
          SRE / on-call assistant · Phase 0 skeleton
        </p>
      </header>

      <div className="flex gap-2">
        <input
          className="flex-1 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="Ask about an incident, a runbook, a service…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={busy}
        />
        <button
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-neutral-900"
          onClick={send}
          disabled={busy || !input.trim()}
        >
          {busy ? "…" : "Send"}
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      {answer && (
        <div className="whitespace-pre-wrap rounded-md border border-neutral-200 bg-white px-4 py-3 text-sm leading-relaxed dark:border-neutral-800 dark:bg-neutral-900">
          {answer}
        </div>
      )}

      {usage && (
        <div className="text-xs text-neutral-400">
          {String(usage.model)} · in {String(usage.tokens_in)} / out{" "}
          {String(usage.tokens_out)} tok · ${Number(usage.cost_usd).toFixed(4)}
        </div>
      )}
    </main>
  );
}
