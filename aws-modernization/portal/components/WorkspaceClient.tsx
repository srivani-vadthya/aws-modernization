"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { PHASES } from "@/lib/phases";
import type { Engagement, PhaseId } from "@/lib/types";
import { ISSUE_POLICY_CS, SCHEMA_SQL } from "@/lib/dotnet-sample";

export function WorkspaceClient({ initial }: { initial: Engagement }) {
  const [e, setE] = useState(initial);
  const [actor, setActor] = useState("architect");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [scope, setScope] = useState<string[]>(
    initial.scopedCapabilityIds.length
      ? initial.scopedCapabilityIds
      : ["nbuw"],
  );

  const phase = e.currentPhase;
  const meta = PHASES.find((p) => p.id === phase)!;

  async function gate(decision: "approved" | "rejected") {
    setBusy(true);
    setMessage(null);
    const res = await fetch(`/api/engagements/${e.id}/gates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        phase,
        decision,
        comment,
        actor,
        scopedCapabilityIds: phase === "scope" ? scope : undefined,
      }),
    });
    const json = await res.json();
    setBusy(false);
    if (!res.ok) {
      setMessage(json.error || "Gate failed");
      return;
    }
    setE(json);
    setComment("");
  }

  async function exportAdo() {
    setBusy(true);
    const res = await fetch(`/api/engagements/${e.id}/export/ado`, {
      method: "POST",
    });
    const json = await res.json();
    setBusy(false);
    setMessage(
      json.exported
        ? `Created ${json.created.length} ADO work items`
        : json.reason || JSON.stringify(json.workItems?.slice(0, 3)),
    );
  }

  const counts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const a of e.assets) map[a.language] = (map[a.language] || 0) + 1;
    return map;
  }, [e.assets]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-[#243049] px-6 py-4">
        <div>
          <Link href="/" className="text-xs tracking-[0.2em] text-[#3dd6c6]">
            NEXUS MODERNIZE
          </Link>
          <h1 className="text-xl font-semibold">{e.name}</h1>
          <p className="text-xs text-[#93a0b8]">
            {e.sourceType}
            {e.gitUrl ? ` · ${e.gitUrl}` : ""} · us-east-1 · target .NET 8 /
            Aurora PostgreSQL
          </p>
        </div>
        <label className="text-xs text-[#93a0b8]">
          Reviewer
          <input
            className="ml-2 rounded border border-[#243049] bg-[#121a2b] px-2 py-1 text-sm text-[#e8eef8]"
            value={actor}
            onChange={(ev) => setActor(ev.target.value)}
          />
        </label>
      </header>

      <nav className="flex gap-1 overflow-x-auto border-b border-[#243049] px-4 py-2">
        {PHASES.map((p) => {
          const g = e.gates.find((x) => x.phase === p.id);
          const active = p.id === phase;
          const done = g?.decision === "approved";
          return (
            <div
              key={p.id}
              className={`min-w-[9.5rem] rounded-lg px-3 py-2 text-xs ${
                active
                  ? "bg-[#3dd6c6] text-[#0b1220]"
                  : done
                    ? "bg-[#1a3d38] text-[#3dd6c6]"
                    : "bg-[#121a2b] text-[#93a0b8]"
              }`}
            >
              <div className="font-mono">{p.step}</div>
              <div className="font-medium">{p.title}</div>
            </div>
          );
        })}
      </nav>

      <div className="grid flex-1 grid-cols-1 lg:grid-cols-[1fr_320px]">
        <section className="p-6">
          <p className="text-sm text-[#93a0b8]">{meta.blurb}</p>
          {phase === "intake" && <IntakePanel e={e} counts={counts} />}
          {phase === "discovery" && <DiscoveryPanel e={e} counts={counts} />}
          {phase === "graph" && <GraphPanel e={e} />}
          {phase === "scope" && (
            <ScopePanel e={e} scope={scope} setScope={setScope} />
          )}
          {phase === "requirements" && <ReqPanel e={e} />}
          {phase === "backlog" && (
            <BacklogPanel e={e} onAdo={() => void exportAdo()} busy={busy} />
          )}
          {phase === "modernize" && <ModernizePanel e={e} />}
          {phase === "tests" && <TestsPanel e={e} />}
          {phase === "failures" && <FailPanel e={e} />}
          {phase === "artifacts" && <ArtifactsPanel e={e} />}
        </section>

        <aside className="border-l border-[#243049] bg-[#121a2b] p-5">
          <h2 className="text-sm font-semibold">Human gate</h2>
          <p className="mt-2 text-sm text-[#93a0b8]">
            Approve to advance. Reject blocks the pipeline until the comment is
            addressed.
          </p>
          <textarea
            className="mt-4 h-28 w-full rounded-lg border border-[#243049] bg-[#0b1220] p-2 text-sm"
            placeholder="Comment (required on reject)"
            value={comment}
            onChange={(ev) => setComment(ev.target.value)}
          />
          <div className="mt-3 flex flex-col gap-2">
            <button
              disabled={busy || phase === "artifacts"}
              onClick={() => void gate("approved")}
              className="rounded-lg bg-[#3dd6c6] px-3 py-2 text-sm font-medium text-[#0b1220] disabled:opacity-40"
            >
              Approve {meta.title}
            </button>
            <button
              disabled={busy}
              onClick={() => void gate("rejected")}
              className="rounded-lg border border-[#f07178] px-3 py-2 text-sm text-[#f07178] disabled:opacity-40"
            >
              Reject
            </button>
          </div>
          {message && (
            <p className="mt-4 text-xs text-[#f0b429]">{message}</p>
          )}
          <dl className="mt-6 space-y-2 text-xs text-[#93a0b8]">
            <div>Assets: {e.assets.length}</div>
            <div>Scope snapshot: {e.scopeId || "—"}</div>
            <div>Requirements: {e.requirements.length}</div>
            <div>Backlog items: {e.backlog.length}</div>
          </dl>
        </aside>
      </div>
    </div>
  );
}

function IntakePanel({
  e,
  counts,
}: {
  e: Engagement;
  counts: Record<string, number>;
}) {
  return (
    <div className="mt-4">
      <h2 className="text-2xl font-semibold">Classified inventory</h2>
      <div className="mt-4 flex flex-wrap gap-2">
        {Object.entries(counts).map(([k, v]) => (
          <span
            key={k}
            className="rounded-full border border-[#243049] px-3 py-1 text-sm"
          >
            {k}: {v}
          </span>
        ))}
      </div>
      <div className="mt-4 max-h-[480px] overflow-auto rounded-xl border border-[#243049]">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#121a2b] text-[#93a0b8]">
            <tr>
              <th className="px-3 py-2">Path</th>
              <th>Language</th>
              <th>Module</th>
              <th>LOC</th>
            </tr>
          </thead>
          <tbody>
            {e.assets.map((a) => (
              <tr key={a.path} className="border-t border-[#243049]">
                <td className="px-3 py-2 font-mono text-xs">{a.path}</td>
                <td>{a.language}</td>
                <td>{a.moduleHint}</td>
                <td>{a.loc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DiscoveryPanel({
  e,
  counts,
}: {
  e: Engagement;
  counts: Record<string, number>;
}) {
  const loc = e.assets.reduce((s, a) => s + a.loc, 0);
  return (
    <div className="mt-4 space-y-4">
      <h2 className="text-2xl font-semibold">Discovery pack</h2>
      <p className="text-[#93a0b8]">
        AWS Transform engine: IBM i / AS/400 (RPGLE, COBOL, CL, DDS). Region
        us-east-1. This demo stage uses classified assets plus a Transform-shaped
        summary; live job wiring is the next slice.
      </p>
      <div className="grid gap-3 md:grid-cols-4">
        <Stat label="Programs / jobs" value={String(e.assets.length)} />
        <Stat label="Lines" value={String(loc)} />
        <Stat label="Languages" value={String(Object.keys(counts).length)} />
        <Stat label="Capabilities" value={String(e.capabilities.length)} />
      </div>
      {e.transformJobs.map((j) => (
        <div
          key={j.engine}
          className="rounded-xl border border-[#243049] bg-[#121a2b] p-4 text-sm"
        >
          <div className="font-medium">{j.engine}</div>
          <div className="text-[#3dd6c6]">{j.status}</div>
          <p className="mt-2 text-[#93a0b8]">{j.note}</p>
        </div>
      ))}
    </div>
  );
}

function GraphPanel({ e }: { e: Engagement }) {
  return (
    <div className="mt-4">
      <h2 className="text-2xl font-semibold">Application knowledge graph</h2>
      <p className="mt-2 text-sm text-[#93a0b8]">
        CALLS / WRITES / MAPS_TO / TRIGGERED_BY. Hover a node in a later slice;
        for the architect demo the clusters are the three insurance domains.
      </p>
      <div className="relative mt-4 h-[640px] overflow-auto rounded-xl border border-[#243049] bg-[#0b1220]">
        <svg viewBox="0 0 860 680" className="h-[640px] w-[860px]">
          {e.graph.edges.map((edge, i) => {
            const a = e.graph.nodes.find((n) => n.id === edge.from);
            const b = e.graph.nodes.find((n) => n.id === edge.to);
            if (!a || !b) return null;
            return (
              <line
                key={i}
                x1={a.x + 50}
                y1={a.y + 16}
                x2={b.x + 50}
                y2={b.y + 16}
                stroke="#243049"
                strokeWidth="1.5"
              />
            );
          })}
          {e.graph.nodes.map((n) => (
            <g key={n.id} transform={`translate(${n.x},${n.y})`}>
              <rect
                width="110"
                height="36"
                rx="8"
                fill={
                  n.type === "capability"
                    ? "#1a3d38"
                    : n.type === "service"
                      ? "#1b2a4a"
                      : "#121a2b"
                }
                stroke={n.type === "capability" ? "#3dd6c6" : "#243049"}
              />
              <text
                x="55"
                y="22"
                textAnchor="middle"
                fill="#e8eef8"
                fontSize="10"
              >
                {n.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}

function ScopePanel({
  e,
  scope,
  setScope,
}: {
  e: Engagement;
  scope: string[];
  setScope: (ids: string[]) => void;
}) {
  return (
    <div className="mt-4">
      <h2 className="text-2xl font-semibold">Select business module</h2>
      <p className="mt-2 text-sm text-[#93a0b8]">
        Wave 1 recommendation: New Business & Underwriting. Servicing and Claims
        stay coupled through POLICY.
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {e.capabilities.map((c) => {
          const on = scope.includes(c.id);
          return (
            <button
              key={c.id}
              onClick={() =>
                setScope(
                  on ? scope.filter((x) => x !== c.id) : [...scope, c.id],
                )
              }
              className={`rounded-2xl border p-4 text-left ${
                on
                  ? "border-[#3dd6c6] bg-[#1a3d38]"
                  : "border-[#243049] bg-[#121a2b]"
              }`}
            >
              <div className="font-medium">{c.name}</div>
              <p className="mt-2 text-sm text-[#93a0b8]">{c.summary}</p>
              <p className="mt-3 text-xs text-[#7aa2ff]">
                {c.assetPaths.length} assets in blast radius
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ReqPanel({ e }: { e: Engagement }) {
  return (
    <div className="mt-4">
      <h2 className="text-2xl font-semibold">Mined requirements</h2>
      <div className="mt-4 space-y-2">
        {e.requirements.map((r) => (
          <div
            key={r.id}
            className="rounded-xl border border-[#243049] bg-[#121a2b] p-4"
          >
            <div className="text-xs text-[#3dd6c6]">
              {r.id} · {r.type}
            </div>
            <div className="mt-1">{r.statement}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {r.traces.map((t) => (
                <span
                  key={t}
                  className="rounded bg-[#0b1220] px-2 py-1 font-mono text-[11px] text-[#93a0b8]"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function BacklogPanel({
  e,
  onAdo,
  busy,
}: {
  e: Engagement;
  onAdo: () => void;
  busy: boolean;
}) {
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold">Wave backlog</h2>
        <button
          onClick={onAdo}
          disabled={busy}
          className="rounded-lg border border-[#7aa2ff] px-3 py-1 text-sm text-[#7aa2ff]"
        >
          Export to Azure DevOps
        </button>
      </div>
      <ul className="mt-4 space-y-2">
        {e.backlog.map((b) => (
          <li
            key={b.id}
            className="flex items-center justify-between rounded-xl border border-[#243049] bg-[#121a2b] px-4 py-3"
          >
            <div>
              <div className="text-xs text-[#93a0b8]">
                {b.id} · {b.type} · {b.adoType} · wave {b.wave}
              </div>
              <div>{b.title}</div>
            </div>
            <div className="text-xs text-[#7aa2ff]">
              {b.requirementIds.join(", ")}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ModernizePanel({ e }: { e: Engagement }) {
  return (
    <div className="mt-4 space-y-4">
      <h2 className="text-2xl font-semibold">Technology modernization</h2>
      <p className="text-[#93a0b8]">
        Technology-first target — not a Lambda vs ECS wizard. Services are .NET
        8 vertical slices; AWS is the landing zone (API, events, Aurora
        PostgreSQL in us-east-1).
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-[#243049] bg-[#121a2b] p-4 text-sm">
          <div className="text-[#93a0b8]">Language / framework</div>
          <div className="text-lg">
            {e.target.language} · {e.target.framework}
          </div>
          <div className="mt-2">{e.target.style}</div>
          <div className="mt-2">Data: {e.target.data}</div>
        </div>
        <div className="rounded-xl border border-[#243049] bg-[#121a2b] p-4 text-sm">
          <div className="text-[#93a0b8]">Bounded contexts</div>
          {e.target.services.map((s) => (
            <div key={s.name}>{s.name}</div>
          ))}
          <div className="mt-2 text-[#3dd6c6]">
            Events: {e.target.events.join(", ")}
          </div>
        </div>
      </div>
      <pre className="overflow-auto rounded-xl border border-[#243049] bg-[#0b1220] p-4 text-xs leading-5">
        {ISSUE_POLICY_CS}
      </pre>
    </div>
  );
}

function TestsPanel({ e }: { e: Engagement }) {
  const cases = e.requirements.filter((r) => r.type === "rule");
  return (
    <div className="mt-4">
      <h2 className="text-2xl font-semibold">Generated tests</h2>
      <p className="mt-2 text-sm text-[#93a0b8]">
        xUnit facts named by requirement id. HTTP scripts for IssuePolicy.
        Coverage is rule-derived — not a certified IBM i compare harness.
      </p>
      <ul className="mt-4 space-y-2 text-sm">
        {cases.map((r) => (
          <li
            key={r.id}
            className="rounded-xl border border-[#243049] bg-[#121a2b] px-4 py-3"
          >
            <span className="font-mono text-[#3dd6c6]">{r.id}</span> —{" "}
            {r.statement}
            <div className="mt-1 font-mono text-xs text-[#93a0b8]">
              UnderwritingTests.{r.id.replaceAll("-", "")}_FromRpgle()
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FailPanel({ e }: { e: Engagement }) {
  return (
    <div className="mt-4 space-y-3">
      <h2 className="text-2xl font-semibold">Failure analysis</h2>
      {e.failures.length === 0 && (
        <p className="text-[#93a0b8]">No residual failures in this engagement.</p>
      )}
      {e.failures.map((f) => (
        <div
          key={f.id}
          className="rounded-xl border border-[#f0b429]/40 bg-[#121a2b] p-4"
        >
          <div className="text-xs text-[#f0b429]">
            {f.id} · {f.code} · {f.phase}
          </div>
          <p className="mt-2">{f.message}</p>
          <p className="mt-2 text-sm text-[#93a0b8]">{f.suggestedAction}</p>
        </div>
      ))}
    </div>
  );
}

function ArtifactsPanel({ e }: { e: Engagement }) {
  return (
    <div className="mt-4 space-y-4">
      <h2 className="text-2xl font-semibold">Final artifacts</h2>
      <p className="text-[#93a0b8]">
        Download the pack (JSON + generated .NET + Aurora DDL). GitHub push
        uses GITHUB_TOKEN when configured.
      </p>
      <div className="flex gap-3">
        <a
          className="rounded-lg bg-[#3dd6c6] px-4 py-2 text-sm font-medium text-[#0b1220]"
          href={`/api/engagements/${e.id}/artifacts`}
        >
          Download pack
        </a>
        <a
          className="rounded-lg border border-[#7aa2ff] px-4 py-2 text-sm text-[#7aa2ff]"
          href={`/api/engagements/${e.id}/export/github`}
        >
          GitHub export status
        </a>
      </div>
      <pre className="overflow-auto rounded-xl border border-[#243049] bg-[#0b1220] p-4 text-xs">
        {SCHEMA_SQL}
      </pre>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#243049] bg-[#121a2b] p-4">
      <div className="text-xs text-[#93a0b8]">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}
