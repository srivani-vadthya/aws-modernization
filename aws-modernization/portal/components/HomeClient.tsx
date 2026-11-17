"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Engagement } from "@/lib/types";

export function HomeClient() {
  const router = useRouter();
  const [engagements, setEngagements] = useState<Engagement[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gitUrl, setGitUrl] = useState("");
  const [gitBranch, setGitBranch] = useState("main");
  const [name, setName] = useState("");

  useEffect(() => {
    fetch("/api/engagements")
      .then((r) => r.json())
      .then(setEngagements)
      .catch(() => undefined);
  }, []);

  async function start(mode: "sample" | "git") {
    setBusy(mode);
    setError(null);
    try {
      const res = await fetch("/api/engagements", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          name: name || undefined,
          gitUrl,
          gitBranch,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed");
      router.push(`/engagements/${json.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
      setBusy(null);
    }
  }

  async function uploadZip(file: File) {
    setBusy("zip");
    setError(null);
    try {
      const form = new FormData();
      form.set("file", file);
      form.set("name", name || file.name);
      const res = await fetch("/api/engagements", { method: "POST", body: form });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed");
      router.push(`/engagements/${json.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 py-10">
      <header className="flex flex-col gap-3">
        <p className="text-sm tracking-[0.2em] text-[#3dd6c6]">NEXUS MODERNIZE</p>
        <h1 className="text-4xl font-semibold tracking-tight">
          Reimagine IBM i and legacy estates to cloud-native .NET
        </h1>
        <p className="max-w-3xl text-[#93a0b8]">
          Orchestration around AWS Transform: reverse-engineer the estate, pick a
          business module, mine requirements, then forward-engineer event-driven
          .NET 8 on Aurora PostgreSQL. Every phase has a human gate.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <article className="rounded-2xl border border-[#243049] bg-[#121a2b] p-5">
          <h2 className="text-lg font-medium">LIFE400 sample</h2>
          <p className="mt-2 text-sm text-[#93a0b8]">
            ACME term life on IBM i: RPGLE, COBOL, CL, DDS. Scope New Business
            in the demo.
          </p>
          <button
            className="mt-4 w-full rounded-lg bg-[#3dd6c6] px-4 py-2 font-medium text-[#0b1220] disabled:opacity-50"
            disabled={!!busy}
            onClick={() => start("sample")}
          >
            {busy === "sample" ? "Loading…" : "Load sample"}
          </button>
        </article>

        <article className="rounded-2xl border border-[#243049] bg-[#121a2b] p-5">
          <h2 className="text-lg font-medium">Clone Git</h2>
          <p className="mt-2 text-sm text-[#93a0b8]">
            Public HTTPS URL. Private repos later via token.
          </p>
          <input
            className="mt-3 w-full rounded-lg border border-[#243049] bg-[#0b1220] px-3 py-2 text-sm"
            placeholder="https://github.com/org/repo"
            value={gitUrl}
            onChange={(ev) => setGitUrl(ev.target.value)}
          />
          <input
            className="mt-2 w-full rounded-lg border border-[#243049] bg-[#0b1220] px-3 py-2 text-sm"
            placeholder="branch"
            value={gitBranch}
            onChange={(ev) => setGitBranch(ev.target.value)}
          />
          <button
            className="mt-4 w-full rounded-lg border border-[#3dd6c6] px-4 py-2 font-medium text-[#3dd6c6] disabled:opacity-50"
            disabled={!!busy || !gitUrl}
            onClick={() => start("git")}
          >
            {busy === "git" ? "Cloning…" : "Clone and classify"}
          </button>
        </article>

        <article className="rounded-2xl border border-[#243049] bg-[#121a2b] p-5">
          <h2 className="text-lg font-medium">Upload zip</h2>
          <p className="mt-2 text-sm text-[#93a0b8]">
            Source tree of RPGLE / COBOL / CL / DDS or mixed legacy.
          </p>
          <input
            className="mt-3 w-full text-sm"
            type="file"
            accept=".zip"
            onChange={(ev) => {
              const f = ev.target.files?.[0];
              if (f) void uploadZip(f);
            }}
          />
          {busy === "zip" && (
            <p className="mt-3 text-sm text-[#93a0b8]">Unpacking…</p>
          )}
        </article>
      </section>

      <label className="flex max-w-md flex-col gap-1 text-sm text-[#93a0b8]">
        Engagement name (optional)
        <input
          className="rounded-lg border border-[#243049] bg-[#121a2b] px-3 py-2 text-[#e8eef8]"
          value={name}
          onChange={(ev) => setName(ev.target.value)}
        />
      </label>

      {error && (
        <p className="rounded-lg border border-[#f07178]/40 bg-[#f07178]/10 px-4 py-3 text-sm">
          {error}
        </p>
      )}

      <section>
        <h2 className="mb-3 text-sm tracking-wide text-[#93a0b8]">
          RECENT ENGAGEMENTS
        </h2>
        <div className="divide-y divide-[#243049] rounded-2xl border border-[#243049]">
          {engagements.length === 0 && (
            <p className="px-4 py-6 text-sm text-[#93a0b8]">None yet.</p>
          )}
          {engagements.map((e) => (
            <button
              key={e.id}
              className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-[#121a2b]"
              onClick={() => router.push(`/engagements/${e.id}`)}
            >
              <span>
                <span className="block font-medium">{e.name}</span>
                <span className="text-xs text-[#93a0b8]">
                  {e.sourceType} · {e.currentPhase} · {e.assets.length} assets
                </span>
              </span>
              <span className="text-xs uppercase text-[#3dd6c6]">{e.status}</span>
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
