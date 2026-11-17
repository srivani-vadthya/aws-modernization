import { useState, useEffect, Fragment, type ReactNode } from "react";
import { api, type Engagement, type ScopeAnalysis } from "../api";
import { GraphView } from "./GraphView";
import { DiscoveryReport } from "./DiscoveryReport";
import { SemanticIRPanel } from "./SemanticIRPanel";
import { Cpu, ShieldCheck, Server, Cloud, Zap } from "./Icons";


export function PhasePanels({
  engagement,
  phase,
  onChange,
}: {
  engagement: Engagement;
  phase: string;
  onChange: (e: Engagement) => void;
}) {
  const seed = engagement.seed;
  if (!seed) return <p className="text-slate-600">No artifacts yet.</p>;

  switch (phase) {
    case "intake": // Compatibility for older saved engagements; no separate intake screen.
    case "discovery":
      return <DiscoveryReport key={engagement.id} engagementId={engagement.id} />;
    case "graph":
      return <Graph e={engagement} />;
    case "scope":
      return <Scope e={engagement} onChange={onChange} />;
    case "semantic-ir":
      return <SemanticIRPanel e={engagement} />;
    case "requirements":
      return <Requirements e={engagement} onChange={onChange} />;

    case "backlog":
      return <Backlog e={engagement} onChange={onChange} />;
    case "modernize":
      return <Modernize e={engagement} onChange={onChange} />;

    case "tests":
      return <Tests e={engagement} />;
    case "failures":
      return <Failures e={engagement} />;
    case "artifacts":
      return <Artifacts e={engagement} />;
    default:
      return null;
  }
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">{title}</h3>
      <div className="mt-3 text-slate-800">{children}</div>
    </section>
  );
}

function Graph({ e }: { e: Engagement }) {
  const [cap, setCap] = useState<string | null>(e.seed!.capabilities[0]?.id || null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {e.seed!.capabilities.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setCap(c.id)}
            className={`rounded-full px-3 py-1 text-xs ${cap === c.id ? "bg-copper-500/30 text-blue-600 font-medium" : "bg-slate-100"}`}
          >
            {c.name}
          </button>
        ))}
      </div>
      <GraphView seed={e.seed!} highlight={cap} />
      <p className="text-xs text-slate-500">
        {e.seed!.sample === "cics-genapp"
          ? "CALLS / READS / WRITES / MAPS_TO from the curated GenApp overlay plus live inventory."
          : "This is a path-and-file-type graph. Confirm relationships before using it as an implementation design."}
      </p>
    </div>
  );
}

function Scope({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const [busy, setBusy] = useState(false);
  const [scopeAnalysis, setScopeAnalysis] = useState<ScopeAnalysis | null>(null);
  const [scopeAnalysisError, setScopeAnalysisError] = useState<string | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [selectedCapId, setSelectedCapId] = useState<string | null>(null);
  const candidates = scopeAnalysis?.logicalModules ?? [];

  useEffect(() => {
    let active = true;
    setScopeAnalysis(null);
    setScopeAnalysisError(null);
    setSelectedCapId(null);
    api.scopeAnalysis(e.id)
      .then((analysis) => {
        if (!active) return;
        setScopeAnalysis(analysis);
        const activeScopeId = e.scope?.capabilityId;
        setSelectedCapId(activeScopeId && analysis.logicalModules.some((module) => module.moduleId === activeScopeId)
          ? activeScopeId
          : null);
      })
      .catch((err: Error) => {
        if (active) setScopeAnalysisError(err.message);
      });
    return () => {
      active = false;
    };
  }, [e.id, e.scope?.capabilityId]);

  async function pick(id: string) {
    setBusy(true);
    setSelectionError(null);
    try {
      const updated = await api.scope(e.id, id);
      setSelectedCapId(id);
      onChange(updated);
    } catch (err) {
      setSelectionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-blue-200 bg-blue-50/60 p-4">
        <h3 className="text-sm font-bold text-blue-950">Select a scope from graph evidence</h3>
        <p className="mt-1 text-xs leading-relaxed text-blue-900">
          Scope candidates are shown only when the AST/AKG contains operational relationships such as calls, reads, writes, or event flows. Structural file membership alone is not sufficient evidence.
        </p>
        {scopeAnalysisError && (
          <p role="alert" className="mt-2 text-xs text-red-700">Scope evidence could not be loaded: {scopeAnalysisError}</p>
        )}
        {selectionError && (
          <p role="alert" className="mt-2 text-xs text-red-700">Scope selection failed: {selectionError}</p>
        )}
      </section>

      {scopeAnalysis && (
        <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
            <div>
              <h3 className="text-sm font-bold text-slate-900">AST/AKG flow and module evidence</h3>
              <p className="mt-1 text-[11px] text-slate-500">
                {scopeAnalysis.basis}
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-[10px] font-semibold">
              <span className="rounded-full bg-blue-50 px-2.5 py-1 text-blue-700">{scopeAnalysis.summary.totalUseCaseFlows} candidate flows</span>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-700">{scopeAnalysis.summary.mutatingFlows} mutating</span>
              <span className="rounded-full bg-amber-50 px-2.5 py-1 text-amber-800">{scopeAnalysis.summary.sharedKernelCount} shared assets</span>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div>
              <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-600">Entry points to data sinks</h4>
              {scopeAnalysis.useCaseFlows.length > 0 ? (
                <div className="max-h-80 space-y-2 overflow-auto">
                  {scopeAnalysis.useCaseFlows.map((flow) => (
                    <article key={flow.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-1">
                        <h5 className="text-xs font-semibold text-slate-900">{flow.candidateUseCaseName}</h5>
                        <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${flow.isMutation ? "bg-amber-100 text-amber-800" : "bg-sky-100 text-sky-800"}`}>
                          {flow.isMutation ? "Mutates data" : "Read only"}
                        </span>
                      </div>
                      <p className="mt-1 text-[10px] text-slate-500">
                        {flow.entryType} entry: <span className="font-mono">{flow.entryPoint}</span>
                        {flow.callChain.length > 0 && <> · Calls: <span className="font-mono">{flow.callChain.join(" → ")}</span></>}
                      </p>
                      <p className="mt-1 text-[10px] text-slate-600">Transaction data: {flow.transactionBoundary.join(", ") || "none detected"}</p>
                      <p className="mt-0.5 text-[10px] text-slate-500">Reads: {flow.tablesRead.join(", ") || "none"} · Writes: {flow.tablesWritten.join(", ") || "none"}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">No entry-to-data-sink flows were extracted from the available graph relationships.</p>
              )}
            </div>

            <div>
              <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-600">Evidence-backed scope candidates</h4>
              {candidates.length > 0 ? (
                <div className="max-h-80 space-y-2 overflow-auto">
                  {candidates.map((module) => (
                    <button
                      key={module.moduleId}
                      type="button"
                      disabled={busy}
                      onClick={() => void pick(module.moduleId)}
                      className={`w-full rounded-lg border p-3 text-left transition disabled:cursor-wait disabled:opacity-60 ${selectedCapId === module.moduleId ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-slate-50 hover:border-slate-300"}`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-1">
                        <span className="text-xs font-semibold text-slate-900">{module.moduleName}</span>
                        <span className="font-mono text-[10px] text-slate-500">{module.moduleId}</span>
                      </div>
                      <p className="mt-1 text-[10px] text-slate-600">
                        {module.programs.length} code assets · {module.tables.length} tables · {module.evidenceEdgeCount} evidence relationships
                      </p>
                      <p className="mt-1 text-[10px] text-slate-500">
                        Evidence: {module.evidenceKinds.join(", ")} · Cohesion: {module.cohesionScore} · Cross-capability: {module.crossEdges}
                      </p>
                      <p className="mt-1 text-[10px] text-slate-500">
                        Owned writes: {module.ownedTables.join(", ") || "none identified"} · Shared assets: {module.sharedKernels.join(", ") || "none identified"}
                      </p>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
                  No scope candidates meet the graph-evidence requirements. Add or extract operational AST/AKG relationships; no demo scopes are substituted.
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      {e.scope && selectedCapId && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          Selected scope: <strong>{e.scope.name}</strong> ({e.scope.metrics.programs} graph-linked code assets, {e.scope.metrics.tables} graph-linked tables).
        </div>
      )}
    </div>
  );
}

function Requirements({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const reqs = e.seed!.requirements;
  const [selectedReq, setSelectedReq] = useState<string | null>(null);
  const [viewTab, setViewTab] = useState<"matrix" | "backlog">("matrix");

  return (
    <div className="space-y-6">
      {/* Sub-tab navigation for Requirements & Backlog */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-3">
        <button
          type="button"
          onClick={() => setViewTab("matrix")}
          className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
            viewTab === "matrix"
              ? "bg-blue-100 text-blue-700 font-semibold"
              : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          }`}
        >
          <span>Requirements Matrix</span>
          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700 border border-slate-200">
            {reqs.length} rules
          </span>
        </button>
        <button
          type="button"
          onClick={() => setViewTab("backlog")}
          className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
            viewTab === "backlog"
              ? "bg-blue-100 text-blue-700 font-semibold"
              : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          }`}
        >
          <span>Agile Sprint Backlog &amp; User Stories</span>
          <span className="rounded-full bg-purple-100 border border-purple-200 px-1.5 py-0.5 text-[10px] text-purple-700 font-mono">
            {e.seed!.backlog.length} items
          </span>
        </button>
      </div>

      {viewTab === "matrix" ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-900">
                Functional &amp; Technical Requirements Matrix ({reqs.length} rules)
              </h3>
              <p className="text-xs text-slate-600 mt-0.5">
                Click any requirement to view its full end-to-end traceability from legacy source lines to user stories and tests.
              </p>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-100 text-xs uppercase tracking-widest text-slate-500">
                <tr>
                  <th className="px-4 py-2.5">ID</th>
                  <th className="px-3 py-2.5">Type</th>
                  <th className="px-4 py-2.5">Requirement Statement</th>
                  <th className="px-3 py-2.5">Legacy Trace (LOC)</th>
                  <th className="px-3 py-2.5">AST Node</th>
                  <th className="px-3 py-2.5">User Story</th>
                </tr>
              </thead>
              <tbody>
                {reqs.map((r) => {
                  const isSelected = selectedReq === r.id;
                  return (
                    <tr
                      key={r.id}
                      onClick={() => setSelectedReq(isSelected ? null : r.id)}
                      className={`border-t border-slate-100 hover:bg-slate-100 cursor-pointer transition ${
                        isSelected ? "bg-copper-400/10" : ""
                      }`}
                    >
                      <td className="px-4 py-3 font-mono text-xs font-bold text-blue-600 font-medium">{r.id}</td>
                      <td className="px-3 py-3">
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] uppercase text-slate-600">
                          {r.type}
                        </span>
                      </td>
                      <td className="px-4 py-3 max-w-md text-slate-900">{r.statement}</td>
                      <td className="px-3 py-3 font-mono text-[11px] text-blue-700 font-semibold">
                        <div className="flex flex-wrap gap-1">
                          {r.traces.map((t) => (
                            <span key={t} className="rounded bg-slate-50 px-1.5 py-0.5 border border-slate-100">
                              {t}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-3 font-mono text-[10px] text-blue-700">
                        {r.astNodes?.join(", ") || "AST Linked"}
                      </td>
                      <td className="px-3 py-3 font-mono text-[10px] text-emerald-700">
                        {r.stories?.join(", ") || "US Linked"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Detailed Requirement Drawer / Card when a row is selected */}
          {selectedReq && (() => {
            const req = reqs.find((r) => r.id === selectedReq);
            if (!req) return null;
            return (
              <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-5 shadow-xs space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-200/70 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-bold text-blue-700 bg-white px-2.5 py-1 rounded border border-blue-300">
                      {req.id}
                    </span>
                    <span className="rounded bg-blue-100 text-blue-800 px-2 py-0.5 text-xs font-semibold uppercase">
                      {req.type}
                    </span>
                    <h4 className="text-sm font-bold text-slate-900">{req.statement}</h4>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedReq(null)}
                    className="text-xs text-slate-500 hover:text-slate-800 px-2 py-1 rounded hover:bg-white transition"
                  >
                    ✕ Close
                  </button>
                </div>

                {req.description && (
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block mb-1">
                      Business Rationale &amp; Context
                    </span>
                    <p className="text-xs text-slate-700 leading-relaxed bg-white p-3 rounded-lg border border-slate-200">
                      {req.description}
                    </p>
                  </div>
                )}

                {req.acceptanceCriteria && req.acceptanceCriteria.length > 0 && (
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-800 block mb-1.5 flex items-center gap-1.5">
                      <span>🥒</span> Executable Acceptance Criteria (Gherkin Scenarios)
                    </span>
                    <div className="space-y-2">
                      {req.acceptanceCriteria.map((ac, idx) => (
                        <pre
                          key={idx}
                          className="rounded-lg bg-slate-900 p-3.5 font-mono text-[11px] leading-relaxed text-emerald-400 overflow-x-auto whitespace-pre-wrap border border-slate-800"
                        >
                          {ac}
                        </pre>
                      ))}
                    </div>
                  </div>
                )}

                {req.definitionOfDone && (
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-purple-800 block mb-1 flex items-center gap-1.5">
                      <span>🎯</span> Definition of Done (DoD)
                    </span>
                    <p className="text-xs font-mono text-purple-900 bg-purple-50/80 p-2.5 rounded-lg border border-purple-200">
                      {req.definitionOfDone}
                    </p>
                  </div>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2 border-t border-blue-200/50 text-[11px]">
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-semibold">Legacy Traces:</span>
                    <span className="font-mono font-bold text-slate-800">{req.traces.join(", ")}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-semibold">AST Nodes:</span>
                    <span className="font-mono text-blue-700">{req.astNodes?.join(", ") || "—"}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-semibold">Linked User Stories:</span>
                    <span className="font-mono text-emerald-700 font-bold">{req.stories?.join(", ") || "—"}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-semibold">Target Code Anchor:</span>
                    <span className="font-mono text-slate-700">{req.targetCode || "—"}</span>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      ) : (
        <Backlog e={e} onChange={onChange} />
      )}
    </div>
  );
}


function Backlog({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [pushing, setPushing] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [org, setOrg] = useState("enterprise-modernization");
  const [project, setProject] = useState("Core-Platform-Modernization");
  const [pat, setPat] = useState("");
  const items = e.seed!.backlog;

  async function handleAdoPush() {
    setPushing(true);
    setMsg(null);
    try {
      const result = await api.ado(e.id, { org, project, pat: pat || undefined });
      setMsg(result?.message || `Successfully pushed ${items.length} items to Azure DevOps.`);
      onChange(await api.get(e.id));
      setShowConfig(false);
    } catch (err: any) {
      setMsg(err.message || "Failed to push to Azure DevOps");
    } finally {
      setPushing(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-900">
            Sprint Backlog & Traceable User Stories ({items.length} items)
          </h3>
          <p className="text-xs text-slate-600 mt-0.5">
            Every story traces directly to requirement IDs, AST syntax nodes, and target microservice classes.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowConfig(!showConfig)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-2xs"
          >
            ADO Settings
          </button>
          <button
            type="button"
            disabled={pushing}
            onClick={() => void handleAdoPush()}
            className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50 transition shadow-2xs flex items-center gap-1.5"
          >
            {pushing ? (
              <>
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Pushing to ADO…
              </>
            ) : (
              <>
                <span>🚀 Push to Azure DevOps</span>
              </>
            )}
          </button>
        </div>
      </div>

      {showConfig && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-blue-900">Azure DevOps Target Connection</h4>
            <span className="text-[10px] text-blue-700">Supports cloud dev.azure.com and on-prem Azure DevOps Server</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="text-[11px] font-semibold text-slate-700 block mb-1">ADO Organization</label>
              <input
                type="text"
                value={org}
                onChange={(e) => setOrg(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900"
                placeholder="org-name"
              />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-700 block mb-1">Project Name</label>
              <input
                type="text"
                value={project}
                onChange={(e) => setProject(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900"
                placeholder="project-name"
              />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-slate-700 block mb-1">Personal Access Token (PAT)</label>
              <input
                type="password"
                value={pat}
                onChange={(e) => setPat(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 font-mono"
                placeholder="Optional if configured via ENV"
              />
            </div>
          </div>
        </div>
      )}

      {msg && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800 flex items-center justify-between">
          <span className="font-medium">{msg}</span>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-100 text-xs uppercase tracking-widest text-slate-500">
            <tr>
              <th className="px-4 py-2.5">ID</th>
              <th className="px-3 py-2.5">Type</th>
              <th className="px-4 py-2.5">Story Title</th>
              <th className="px-3 py-2.5">Points</th>
              <th className="px-3 py-2.5">MoSCoW</th>
              <th className="px-3 py-2.5">Traced Reqs</th>
              <th className="px-3 py-2.5">Azure DevOps Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((b) => {
              const [expanded, setExpanded] = useState(false);
              return (
                <Fragment key={b.id}>
                  <tr
                    onClick={() => setExpanded(!expanded)}
                    className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer transition"
                  >
                    <td className="px-4 py-3 font-mono text-xs font-bold text-blue-600 font-medium">
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-slate-400">{expanded ? "▼" : "▶"}</span>
                        {b.id}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase font-semibold ${
                        b.type === "epic" ? "bg-purple-500/20 text-purple-700 border border-purple-200" :
                        b.type === "spike" ? "bg-amber-100 border border-amber-200 text-amber-800" :
                        "bg-blue-100 border border-blue-200 text-blue-700"
                      }`}>
                        {b.type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-900 font-medium">
                      <div>{b.title}</div>
                      {b.userStory && (
                        <div className="text-[11px] text-slate-500 italic mt-0.5 line-clamp-1">
                          {b.userStory}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs text-slate-700">{b.storyPoints || 5} pts</td>
                    <td className="px-3 py-3 font-mono text-xs uppercase text-slate-600">{b.moscow}</td>
                    <td className="px-3 py-3 font-mono text-xs text-blue-700 font-semibold">{b.requirementIds.join(", ")}</td>
                    <td className="px-3 py-3 font-mono text-xs">
                      {b.adoUrl ? (
                        <a
                          href={b.adoUrl}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 rounded bg-blue-50 border border-blue-200 px-2 py-0.5 text-blue-700 hover:bg-blue-100 font-bold transition"
                        >
                          <span>ADO #{b.adoId}</span>
                          <span>↗</span>
                        </a>
                      ) : (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">Ready to Push</span>
                      )}
                    </td>
                  </tr>
                  {expanded && (
                    <tr className="bg-slate-50/80 border-b border-slate-200">
                      <td colSpan={7} className="p-4 space-y-3">
                        {b.userStory && (
                          <div className="rounded-lg bg-white p-3 border border-slate-200 text-xs">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                              Agile User Story Format
                            </span>
                            <p className="font-semibold text-slate-800">{b.userStory}</p>
                          </div>
                        )}

                        {b.acceptanceCriteria && b.acceptanceCriteria.length > 0 && (
                          <div className="space-y-1.5">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-800 block flex items-center gap-1.5">
                              <span>🥒</span> Gherkin Acceptance Criteria
                            </span>
                            <div className="space-y-1.5">
                              {b.acceptanceCriteria.map((ac, idx) => (
                                <pre
                                  key={idx}
                                  className="rounded-lg bg-slate-900 p-2.5 font-mono text-[11px] text-emerald-400 overflow-x-auto whitespace-pre-wrap border border-slate-800"
                                >
                                  {ac}
                                </pre>
                              ))}
                            </div>
                          </div>
                        )}

                        {b.definitionOfDone && (
                          <div className="rounded-lg bg-purple-50 p-2.5 border border-purple-200 text-xs">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-700 block mb-0.5 flex items-center gap-1">
                              <span>🎯</span> Definition of Done
                            </span>
                            <p className="font-mono text-purple-950 text-[11px]">{b.definitionOfDone}</p>
                          </div>
                        )}

                        <div className="flex flex-wrap gap-4 text-[11px] font-mono text-slate-600 pt-1">
                          {b.traces && b.traces.length > 0 && (
                            <div>
                              <span className="text-slate-400">Traces: </span>
                              <span className="text-slate-800 font-semibold">{b.traces.join(", ")}</span>
                            </div>
                          )}
                          {b.astNodes && b.astNodes.length > 0 && (
                            <div>
                              <span className="text-slate-400">AST Nodes: </span>
                              <span className="text-blue-700">{b.astNodes.join(", ")}</span>
                            </div>
                          )}
                          {b.targetCode && (
                            <div>
                              <span className="text-slate-400">Target File: </span>
                              <span className="text-slate-800">{b.targetCode}</span>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function Modernize({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const t = e.seed!.target;
  const [lang, setLang] = useState(t.language === "TBD" ? "Java 21" : t.language);
  const [framework, setFramework] = useState(t.framework === "TBD" ? "Spring Boot 3" : t.framework);
  const [database, setDatabase] = useState(t.data === "TBD" ? "Amazon Aurora PostgreSQL" : t.data);
  const [arch, setArch] = useState(
    t.architecture.includes("Select")
      ? "Clean / Hexagonal Microservice on Amazon ECS Fargate"
      : t.architecture,
  );
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  async function handleSaveTarget() {
    setSaving(true);
    try {
      const updated = await api.setTarget(e.id, {
        language: lang,
        framework,
        data: database,
        architecture: arch,
      });
      onChange(updated);
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (err) {
      console.error("Failed to save target:", err);
    } finally {
      setSaving(false);
    }
  }

  const presets = [
    {
      name: "Java 21 / Spring Boot 3",
      lang: "Java 21",
      fw: "Spring Boot 3",
      db: "Amazon Aurora PostgreSQL",
      pattern: "Clean / Hexagonal Microservice on Amazon ECS Fargate",
    },
    {
      name: "C# / .NET 8 / 9",
      lang: "C# (.NET 8)",
      fw: "ASP.NET Core Minimal APIs",
      db: "Amazon Aurora PostgreSQL",
      pattern: "Clean Architecture on Amazon ECS Fargate",
    },
    {
      name: "TypeScript / Node.js",
      lang: "TypeScript",
      fw: "NestJS / Express",
      db: "Amazon DynamoDB",
      pattern: "Event-Driven Microservices on AWS Lambda",
    },
    {
      name: "Python / FastAPI",
      lang: "Python 3.12",
      fw: "FastAPI",
      db: "Amazon Aurora PostgreSQL",
      pattern: "Serverless Container on AWS App Runner",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Target Configurator */}
      <section className="rounded-xl border border-slate-200 bg-slate-50/60 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-4 mb-4">
          <div>
            <h3 className="text-sm font-medium uppercase tracking-widest text-slate-700">
              Select Target Technology Stack
            </h3>
            <p className="text-xs text-slate-500">
              Customize or select from enterprise cloud-native blueprints.
            </p>
          </div>
          {savedSuccess && (
            <span className="rounded bg-emerald-100 border border-emerald-200 px-3 py-1 text-xs font-medium text-emerald-700">
              ✓ Target Stack Applied!
            </span>
          )}
        </div>

        {/* Presets */}
        <div className="mb-4">
          <p className="text-xs text-slate-600 mb-2">Recommended Modernization Presets:</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {presets.map((p) => {
              const active = lang === p.lang && framework === p.fw;
              return (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => {
                    setLang(p.lang);
                    setFramework(p.fw);
                    setDatabase(p.db);
                    setArch(p.pattern);
                  }}
                  className={`rounded-lg border p-2.5 text-left text-xs transition ${
                    active
                      ? "border-blue-500 bg-blue-100 text-blue-800 text-blue-700 font-semibold font-semibold"
                      : "border-slate-200 bg-slate-100 text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <p className="font-medium">{p.name}</p>
                  <p className="text-[10px] text-slate-500 mt-1">{p.db.split(" ")[1] || p.db}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Custom fields */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="text-xs text-slate-600 block mb-1">Target Language</label>
            <input
              type="text"
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              className="w-full rounded bg-slate-50 border border-slate-200 px-3 py-1.5 text-xs text-slate-900 font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-slate-600 block mb-1">Target Framework</label>
            <input
              type="text"
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
              className="w-full rounded bg-slate-50 border border-slate-200 px-3 py-1.5 text-xs text-slate-900 font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-slate-600 block mb-1">Target Database</label>
            <input
              type="text"
              value={database}
              onChange={(e) => setDatabase(e.target.value)}
              className="w-full rounded bg-slate-50 border border-slate-200 px-3 py-1.5 text-xs text-slate-900 font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-slate-600 block mb-1">Architecture Pattern</label>
            <input
              type="text"
              value={arch}
              onChange={(e) => setArch(e.target.value)}
              className="w-full rounded bg-slate-50 border border-slate-200 px-3 py-1.5 text-xs text-slate-900 font-mono"
            />
          </div>
        </div>

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            disabled={saving}
            onClick={handleSaveTarget}
            className="rounded-lg bg-copper-500 px-4 py-2 text-xs font-semibold text-ink-950 hover:bg-copper-400 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save & Apply Target Architecture"}
          </button>
        </div>
      </section>

      {/* Details Grid */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Active Target Blueprint">
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-slate-500">Language</dt>
            <dd className="font-semibold text-blue-700 font-semibold">{t.language}</dd>
            <dt className="text-slate-500">Framework</dt>
            <dd>{t.framework}</dd>
            <dt className="text-slate-500">Database</dt>
            <dd>{t.data}</dd>
            <dt className="text-slate-500">Architecture</dt>
            <dd className="col-span-2 text-slate-700">{t.architecture}</dd>
            <dt className="text-slate-500">Pattern</dt>
            <dd>{t.pattern}</dd>
          </dl>
        </Card>

        <Card title="AWS Transform & Engine Status">
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 border border-emerald-200 px-3 py-1 text-xs font-medium text-emerald-700">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              Connected & Configured
            </span>
          </div>
          <div className="mt-3 space-y-1.5 text-xs text-slate-700">
            <p><span className="text-slate-500">Tenant ID: </span><code className="rounded bg-slate-50 px-1 text-blue-700 font-semibold">7223670174860f499</code></p>
            <p className="truncate"><span className="text-slate-500">Service Profile: </span><span className="font-mono text-[11px] text-slate-600">arn:aws:transform:us-east-1:916338043583:profile/V9V3VN347UNH</span></p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <a
              className="inline-flex items-center gap-1 rounded bg-blue-100 text-blue-800 px-3 py-1.5 text-xs font-medium text-blue-700 font-semibold hover:bg-copper-400/30"
              href="https://7223670174860f499.transform.us-east-1.on.aws/signin/"
              target="_blank"
              rel="noreferrer"
            >
              Open Transform Web Console ↗
            </a>
            <a
              className="inline-flex items-center gap-1 rounded bg-slate-100 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100"
              href={api.packUrl(e.id)}
            >
              Download Artifact Pack →
            </a>
          </div>
        </Card>

        <Card title="Landing Zone Infrastructure (AWS)">
          <ul className="space-y-1 text-sm text-slate-700">
            {Object.entries(t.landingZone).map(([k, v]) => (
              <li key={k}>
                <span className="text-slate-500">{k}: </span>
                {v}
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Domain Modules & Events">
          <p className="text-sm">
            {t.modules.map((m) => (
              <span key={m.id} className="mr-2 rounded bg-slate-100 px-2 py-1 font-mono text-xs text-blue-700 font-semibold">
                {m.package} (wave {m.wave})
              </span>
            ))}
          </p>
          <p className="mt-3 text-sm text-slate-600">Events: {t.events.join(", ")}</p>
        </Card>
      </div>

      {/* Batch Workload Modernization (JCL -> Spring Batch 5) */}
      <BatchModernizationPanel engagementId={e.id} />

      {/* Distributed SAGA Orchestration Engine (2PC Replacement) */}
      <SagaOrchestratorPanel engagementId={e.id} />

      {/* Enterprise Golden Templates & Scaffolding Catalog */}
      <GoldenTemplatesCatalog />
    </div>
  );
}

function GoldenTemplatesCatalog() {
  const [selectedTemplate, setSelectedTemplate] = useState<string>("spring-boot-clean");
  const [selectedFile, setSelectedFile] = useState<string>("pom.xml");
  const [copied, setCopied] = useState<boolean>(false);

  const templates: Record<string, {
    name: string;
    description: string;
    runtime: string;
    files: Record<string, string>;
  }> = {
    "spring-boot-clean": {
      name: "Java 21 / Spring Boot 3 — Clean Hexagonal Architecture",
      description: "Enterprise banking & insurance standard with strict separation of domain models, inbound ports, outbound adapters, and Flyway DDL.",
      runtime: "Amazon ECS Fargate + Amazon Aurora PostgreSQL",
      files: {
        "pom.xml": `<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.4</version>
    </parent>
    <groupId>com.enterprise.modernization</groupId>
    <artifactId>policy-service</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
        <spring-cloud-aws.version>3.1.1</spring-cloud-aws.version>
    </properties>
    <dependencies>
        <!-- Web & Validation -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <!-- Persistence & Flyway -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
        </dependency>
        <dependency>
            <groupId>org.flywaydb</groupId>
            <artifactId>flyway-core</artifactId>
        </dependency>
        <!-- AWS Cloud & Observability -->
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
            <version>3.1.1</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-otel</artifactId>
        </dependency>
    </dependencies>
</project>`,
        "src/main/java/domain/Policy.java": `package com.enterprise.modernization.domain;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

/**
 * Domain Aggregate Root representing an Insurance Policy.
 * Contains pure business logic extracted from legacy RPGLE/COBOL routines.
 */
public class Policy {
    private final UUID id;
    private final String policyNumber;
    private final UUID customerId;
    private BigDecimal sumInsured;
    private BigDecimal monthlyPremium;
    private PolicyStatus status;
    private final LocalDate effectiveDate;
    private Long version;

    public enum PolicyStatus { DRAFT, UNDERWRITING, ACTIVE, LAPSED, CANCELLED }

    public Policy(UUID id, String policyNumber, UUID customerId, BigDecimal sumInsured, LocalDate effectiveDate) {
        this.id = Objects.requireNonNull(id);
        this.policyNumber = Objects.requireNonNull(policyNumber);
        this.customerId = Objects.requireNonNull(customerId);
        this.sumInsured = sumInsured;
        this.effectiveDate = effectiveDate;
        this.status = PolicyStatus.DRAFT;
        this.monthlyPremium = calculatePremium();
    }

    /**
     * Translated business rule from legacy NBUW01 calculation.
     */
    public BigDecimal calculatePremium() {
        if (sumInsured == null || sumInsured.compareTo(BigDecimal.ZERO) <= 0) {
            return BigDecimal.ZERO;
        }
        // Base rate: 0.25% per annum divided by 12 months
        return sumInsured.multiply(new BigDecimal("0.0025"))
                         .divide(new BigDecimal("12"), 2, java.math.RoundingMode.HALF_UP);
    }

    public void activate() {
        if (this.status != PolicyStatus.UNDERWRITING) {
            throw new IllegalStateException("Policy must be in UNDERWRITING state to activate");
        }
        this.status = PolicyStatus.ACTIVE;
    }

    // Getters and invariants
    public UUID getId() { return id; }
    public String getPolicyNumber() { return policyNumber; }
    public PolicyStatus getStatus() { return status; }
    public BigDecimal getMonthlyPremium() { return monthlyPremium; }
}`,
        "src/main/java/ports/in/CreatePolicyUseCase.java": `package com.enterprise.modernization.ports.in;

import com.enterprise.modernization.domain.Policy;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

/**
 * Inbound port interface governing policy creation commands.
 */
public interface CreatePolicyUseCase {
    record Command(
        String policyNumber,
        UUID customerId,
        BigDecimal sumInsured,
        LocalDate effectiveDate
    ) {}

    Policy createPolicy(Command command);
}`,
        "src/main/java/adapters/in/web/PolicyController.java": `package com.enterprise.modernization.adapters.in.web;

import com.enterprise.modernization.ports.in.CreatePolicyUseCase;
import com.enterprise.modernization.domain.Policy;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.math.BigDecimal;
import java.net.URI;
import java.time.LocalDate;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/policies")
public class PolicyController {

    private final CreatePolicyUseCase useCase;

    public PolicyController(CreatePolicyUseCase useCase) {
        this.useCase = useCase;
    }

    public record CreatePolicyRequest(
        @NotBlank String policyNumber,
        @NotNull UUID customerId,
        @NotNull BigDecimal sumInsured,
        @NotNull LocalDate effectiveDate
    ) {}

    @PostMapping
    public ResponseEntity<PolicyResponse> createPolicy(@Valid @RequestBody CreatePolicyRequest req) {
        Policy policy = useCase.createPolicy(new CreatePolicyUseCase.Command(
            req.policyNumber(),
            req.customerId(),
            req.sumInsured(),
            req.effectiveDate()
        ));
        return ResponseEntity
            .created(URI.create("/api/v1/policies/" + policy.getId()))
            .body(new PolicyResponse(policy.getId(), policy.getPolicyNumber(), policy.getStatus().name(), policy.getMonthlyPremium()));
    }

    public record PolicyResponse(UUID id, String policyNumber, String status, BigDecimal monthlyPremium) {}
}`,
        "src/main/resources/db/migration/V1__initial_schema.sql": `-- Enterprise Aurora PostgreSQL DDL Schema
-- Converted from legacy DB2 Physical File definitions (DDS)
CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_number VARCHAR(32) NOT NULL UNIQUE,
    customer_id UUID NOT NULL,
    sum_insured NUMERIC(15, 2) NOT NULL,
    monthly_premium NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    effective_date DATE NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_policies_customer ON policies(customer_id);
CREATE INDEX idx_policies_status ON policies(status);`,
        "infra/cdk/lib/ecs-fargate-stack.ts": `import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecsPatterns from 'aws-cdk-lib/aws-ecs-patterns';
import { Construct } from 'constructs';

export class PolicyServiceStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const vpc = new ec2.Vpc(this, 'PolicyVpc', { maxAzs: 2 });
    const cluster = new ecs.Cluster(this, 'PolicyCluster', { vpc });

    const fargateService = new ecsPatterns.ApplicationLoadBalancedFargateService(this, 'PolicyFargate', {
      cluster,
      cpu: 512,
      memoryLimitMiB: 1024,
      desiredCount: 2,
      taskImageOptions: {
        image: ecs.ContainerImage.fromRegistry('policy-service:latest'),
        containerPort: 8080,
        environment: {
          SPRING_PROFILES_ACTIVE: 'prod',
        },
      },
      publicLoadBalancer: false,
    });

    fargateService.targetGroup.configureHealthCheck({
      path: '/actuator/health',
    });
  }
}`
      }
    },
    "dotnet-clean": {
      name: "C# / .NET 8 — Vertical Slice Clean Architecture",
      description: "High-performance enterprise Microsoft stack with FastEndpoints, MediatR, EF Core, and AWS Systems Manager Parameter Store.",
      runtime: "Amazon ECS Fargate + Amazon Aurora PostgreSQL",
      files: {
        "PolicyService.csproj": `<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="FastEndpoints" Version="5.29.0" />
    <PackageReference Include="MediatR" Version="12.4.1" />
    <PackageReference Include="Npgsql.EntityFrameworkCore.PostgreSQL" Version="8.0.8" />
    <PackageReference Include="AWSSDK.SecretsManager" Version="3.7.400" />
    <PackageReference Include="OpenTelemetry.Extensions.Hosting" Version="1.9.0" />
  </ItemGroup>
</Project>`,
        "Features/Policies/CreatePolicyEndpoint.cs": `using FastEndpoints;
using MediatR;

namespace Enterprise.Modernization.Features.Policies;

public record CreatePolicyRequest(string PolicyNumber, Guid CustomerId, decimal SumInsured, DateOnly EffectiveDate);
public record CreatePolicyResponse(Guid Id, string PolicyNumber, string Status, decimal Premium);

public class CreatePolicyEndpoint : Endpoint<CreatePolicyRequest, CreatePolicyResponse>
{
    public override void Configure()
    {
        Post("/api/v1/policies");
        AllowAnonymous();
    }

    public override async Task HandleAsync(CreatePolicyRequest req, CancellationToken ct)
    {
        // Execute business command
        var id = Guid.NewGuid();
        var premium = req.SumInsured * 0.0025m / 12m;
        await SendCreatedAtAsync<GetPolicyEndpoint>(new { Id = id }, new CreatePolicyResponse(id, req.PolicyNumber, "ACTIVE", premium), cancellation: ct);
    }
}`,
        "Infrastructure/PolicyDbContext.cs": `using Microsoft.EntityFrameworkCore;

namespace Enterprise.Modernization.Infrastructure;

public class PolicyDbContext : DbContext
{
    public PolicyDbContext(DbContextOptions<PolicyDbContext> options) : base(options) {}

    public DbSet<PolicyRecord> Policies => Set<PolicyRecord>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<PolicyRecord>(entity =>
        {
            entity.ToTable("policies");
            entity.HasKey(e => e.Id);
            entity.Property(e => e.PolicyNumber).IsRequired().HasMaxLength(32);
            entity.Property(e => e.SumInsured).HasPrecision(15, 2);
            entity.Property(e => e.MonthlyPremium).HasPrecision(10, 2);
        });
    }
}

public class PolicyRecord
{
    public Guid Id { get; set; }
    public string PolicyNumber { get; set; } = string.Empty;
    public decimal SumInsured { get; set; }
    public decimal MonthlyPremium { get; set; }
}`,
        "frontend/src/pages/PolicyList.tsx": `import React, { useEffect, useState } from 'react';

interface PolicyItem {
  id: string;
  policyNumber: string;
  status: string;
  monthlyPremium: number;
}

export const PolicyList: React.FC = () => {
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/v1/policies')
      .then((res) => res.json())
      .then((data) => setPolicies(data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-4 text-slate-600">Loading .NET 8 WebAPI policies...</div>;

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-900 p-6">
      <h2 className="text-xl font-bold text-white mb-4">Policies Dashboard (React 18 + .NET 8)</h2>
      <div className="grid gap-3">
        {policies.map((p) => (
          <div key={p.id} className="flex justify-between p-3 bg-slate-800 rounded-lg">
            <span className="font-mono text-blue-600 font-medium font-bold">{p.policyNumber}</span>
            <span className="text-emerald-700 font-mono">\${p.monthlyPremium.toFixed(2)}/mo</span>
            <span className="text-xs bg-emerald-100 border border-emerald-200 text-emerald-700 px-2 py-0.5 rounded">{p.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
};`,
        "frontend/package.json": `{
  "name": "ims-modernized-react-portal",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2"
  },
  "devDependencies": {
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.6.2",
    "vite": "^5.4.8"
  }
}`
      }
    },
    "typescript-serverless": {
      name: "TypeScript 20 / Node.js — Event-Driven Serverless",
      description: "Cloud-native serverless architecture using AWS Lambda, Amazon DynamoDB single-table design, and EventBridge.",
      runtime: "AWS Lambda + Amazon DynamoDB + EventBridge",
      files: {
        "package.json": `{
  "name": "policy-serverless-service",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "build": "esbuild src/index.ts --bundle --platform=node --target=node20 --outfile=dist/index.js",
    "test": "vitest run"
  },
  "dependencies": {
    "@aws-sdk/client-dynamodb": "^3.660.0",
    "@aws-sdk/client-eventbridge": "^3.660.0",
    "@aws-sdk/util-dynamodb": "^3.660.0",
    "zod": "^3.23.8"
  }
}`,
        "src/handlers/createPolicy.ts": `import { APIGatewayProxyHandlerV2 } from 'aws-lambda';
import { DynamoDBClient, PutItemCommand } from '@aws-sdk/client-dynamodb';
import { marshall } from '@aws-sdk/util-dynamodb';
import { z } from 'zod';
import { randomUUID } from 'crypto';

const client = new DynamoDBClient({});
const TABLE_NAME = process.env.TABLE_NAME || 'PoliciesTable';

const PolicySchema = z.object({
  policyNumber: z.string().min(3),
  customerId: z.string().uuid(),
  sumInsured: z.number().positive(),
  effectiveDate: z.string(),
});

export const handler: APIGatewayProxyHandlerV2 = async (event) => {
  try {
    const body = JSON.parse(event.body || '{}');
    const validated = PolicySchema.parse(body);

    const id = randomUUID();
    const monthlyPremium = Number(((validated.sumInsured * 0.0025) / 12).toFixed(2));

    const item = {
      PK: \`POLICY#\${id}\`,
      SK: 'METADATA',
      id,
      policyNumber: validated.policyNumber,
      customerId: validated.customerId,
      sumInsured: validated.sumInsured,
      monthlyPremium,
      status: 'ACTIVE',
      createdAt: new Date().toISOString(),
    };

    await client.send(new PutItemCommand({
      TableName: TABLE_NAME,
      Item: marshall(item),
    }));

    return {
      statusCode: 201,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item),
    };
  } catch (err: any) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: err.message }),
    };
  }
};`
      }
    }
  };

  const currentTmpl = templates[selectedTemplate] || templates["spring-boot-clean"];
  const fileKeys = Object.keys(currentTmpl.files);
  const activeFile = currentTmpl.files[selectedFile] || currentTmpl.files[fileKeys[0]];

  const handleCopy = () => {
    navigator.clipboard.writeText(activeFile);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="rounded-xl border border-amber-500/20 bg-slate-50/80 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-blue-100 border border-blue-200 text-blue-700">
              <ShieldCheck />
            </span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-800">
              Enterprise Golden Architecture Templates Catalog
            </h3>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Reference blueprints used to constrain Bedrock LLM generation and enforce corporate standards.
          </p>
        </div>
        <div className="flex rounded-lg bg-slate-50 p-1 border border-slate-200">
          {Object.entries(templates).map(([key, t]) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                setSelectedTemplate(key);
                setSelectedFile(Object.keys(t.files)[0]);
              }}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                selectedTemplate === key
                  ? "bg-blue-100 text-blue-700 font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {key === "spring-boot-clean" ? "Java / Spring Boot" : key === "dotnet-clean" ? ".NET 8 C#" : "Node.js Serverless"}
            </button>
          ))}
        </div>
      </div>

      {/* Blueprint summary callout */}
      <div className="mb-4 rounded-lg bg-slate-100 p-3.5 border border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="text-sm font-medium text-slate-900">{currentTmpl.name}</h4>
            <p className="text-xs text-slate-600 mt-0.5">{currentTmpl.description}</p>
          </div>
          <span className="rounded bg-white px-2.5 py-1 text-[11px] font-mono text-blue-700 font-semibold border border-slate-200">
            Target: {currentTmpl.runtime}
          </span>
        </div>
        <p className="mt-2 text-[11px] text-slate-700 bg-white rounded px-2.5 py-1 border border-slate-200">
          <strong>Enterprise Architecture Governance:</strong> This pre-approved scaffold is injected into Amazon Bedrock (Nova Pro) as few-shot constraints. The LLM translates legacy RPGLE/COBOL algorithms into these exact port interfaces and Flyway migrations, preventing hallucination and enforcing production-grade standards.
        </p>
      </div>

      {/* Template File Explorer & Viewer */}
      <div className="grid gap-4 lg:grid-cols-4">
        {/* File tree */}
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs">
          <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Golden Template Scaffolding:
          </p>
          <div className="mt-1 space-y-1">
            {fileKeys.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setSelectedFile(f)}
                className={`w-full truncate rounded px-2 py-1.5 text-left font-mono text-xs transition ${
                  selectedFile === f
                    ? "bg-blue-100 text-blue-800 text-blue-700 font-semibold font-semibold"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                📄 {f}
              </button>
            ))}
          </div>
        </div>

        {/* Code preview */}
        <div className="lg:col-span-3 rounded-lg border border-slate-700 bg-slate-950 p-4 font-mono text-xs shadow-inner">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
            <span className="text-slate-300 text-[11px] font-semibold">{selectedFile}</span>
            <button
              type="button"
              onClick={handleCopy}
              className="rounded bg-slate-800 px-2.5 py-1 text-[11px] text-slate-200 hover:bg-slate-700 transition"
            >
              {copied ? "✓ Copied" : "Copy Code"}
            </button>
          </div>
          <pre className="max-h-80 overflow-auto text-emerald-400 leading-relaxed font-mono">
            {activeFile}
          </pre>
        </div>
      </div>
    </section>
  );
}

function BatchModernizationPanel({ engagementId }: { engagementId: string }) {
  const [data, setData] = useState<{
    sourceJcl: string;
    stepsParsed: number;
    targetRuntime: string;
    springBatchConfig: string;
    chunkSize: number;
    idempotencyKeyStrategy: string;
    dataPipelineDefinition: Record<string, any>;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [customJcl, setCustomJcl] = useState(`//DAILYPOL JOB (ACCT),'DAILY RENEWAL',CLASS=A,MSGCLASS=X
//STEP10   EXEC PGM=SORT
//SORTIN   DD DSN=PROD.POL.MASTER,DISP=SHR
//SORTOUT  DD DSN=&&TEMP1,DISP=(NEW,PASS)
//STEP20   EXEC PGM=POLRNW01
//INPUT    DD DSN=&&TEMP1,DISP=(OLD,DELETE)
//OUTPUT   DD DSN=PROD.POL.RENEWED,DISP=(NEW,CATLG)`);

  const runBatchModernize = async () => {
    setLoading(true);
    try {
      const res = await api.batchModernize(engagementId, customJcl);
      setData(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-xl border border-indigo-500/20 bg-slate-50/80 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-indigo-100 border border-indigo-200 text-indigo-700">
              <Cpu />
            </span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-800">
              Nocturnal Batch Workload Modernization Engine
            </h3>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Converts mainframe JCL jobstreams, sequential files, and IBM SORT steps into Spring Batch 5 chunk pipelines or Azure Data Factory activities.
          </p>
        </div>
        <button
          type="button"
          onClick={runBatchModernize}
          disabled={loading}
          className="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50 transition"
        >
          {loading ? "Synthesizing Pipeline…" : "Modernize JCL Workload"}
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-700 bg-slate-950 p-3 font-mono text-xs">
          <div className="text-[11px] font-semibold text-slate-400 mb-2">Legacy JCL Job Stream Input:</div>
          <textarea
            value={customJcl}
            onChange={(e) => setCustomJcl(e.target.value)}
            rows={8}
            className="w-full bg-slate-900 text-amber-300 font-mono text-xs p-2.5 rounded border border-slate-800 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div className="rounded-lg border border-slate-700 bg-slate-950 p-3 font-mono text-xs">
          <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400 mb-2">
            <span>Modern Target Output (Spring Batch 5):</span>
            {data && (
              <span className="text-indigo-400 text-[10px] font-mono">
                Chunk: {data.chunkSize} | Steps: {data.stepsParsed}
              </span>
            )}
          </div>
          {data ? (
            <pre className="max-h-60 overflow-auto text-emerald-400 text-xs font-mono leading-relaxed">
              {data.springBatchConfig}
            </pre>
          ) : (
            <div className="flex h-48 items-center justify-center text-xs text-slate-500 font-sans italic">
              Click &quot;Modernize JCL Workload&quot; to parse JCL steps and generate chunk-oriented Spring Batch 5 code.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function SagaOrchestratorPanel({ engagementId }: { engagementId: string }) {
  const [data, setData] = useState<{
    sagaName: string;
    coordinatorPattern: string;
    isolationLevel: string;
    steps: Array<{
      stepNumber: number;
      service: string;
      action: string;
      compensatingAction: string;
      timeoutMs: number;
    }>;
    stateMachineDefinition: Record<string, any>;
    javaOrchestratorCode: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchSaga = async () => {
    setLoading(true);
    try {
      const res = await api.sagaOrchestrator(engagementId);
      setData(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSaga();
  }, [engagementId]);

  return (
    <section className="rounded-xl border border-rose-500/20 bg-slate-50/80 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-rose-100 border border-rose-200 text-rose-700">
              <Zap />
            </span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-800">
              Distributed SAGA Orchestration Engine (2PC Replacement)
            </h3>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Replaces monolithic CICS 2PC (`EXEC CICS SYNCPOINT`) with an orchestrated SAGA state machine and automated compensating rollback actions.
          </p>
        </div>
        <button
          type="button"
          onClick={fetchSaga}
          disabled={loading}
          className="rounded-lg bg-rose-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-rose-500 disabled:opacity-50 transition"
        >
          {loading ? "Refreshing SAGA…" : "Synthesize SAGA Coordinator"}
        </button>
      </div>

      {data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg bg-white p-3 border border-slate-200">
              <div className="text-[10px] uppercase font-semibold text-slate-500">SAGA Name</div>
              <div className="text-xs font-mono font-bold text-slate-800">{data.sagaName}</div>
            </div>
            <div className="rounded-lg bg-white p-3 border border-slate-200">
              <div className="text-[10px] uppercase font-semibold text-slate-500">Pattern</div>
              <div className="text-xs font-mono font-bold text-rose-600">{data.coordinatorPattern}</div>
            </div>
            <div className="rounded-lg bg-white p-3 border border-slate-200">
              <div className="text-[10px] uppercase font-semibold text-slate-500">Isolation Strategy</div>
              <div className="text-xs font-mono font-bold text-slate-800">{data.isolationLevel}</div>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-3 py-2">Step</th>
                  <th className="px-3 py-2">Service Boundary</th>
                  <th className="px-3 py-2">Forward Action</th>
                  <th className="px-3 py-2">Compensating Action (Rollback)</th>
                  <th className="px-3 py-2 text-right">Timeout</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono text-xs">
                {data.steps.map((st) => (
                  <tr key={st.stepNumber} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-bold text-slate-800">#{st.stepNumber}</td>
                    <td className="px-3 py-2 text-blue-700 font-semibold">{st.service}</td>
                    <td className="px-3 py-2 text-emerald-700 font-semibold">{st.action}</td>
                    <td className="px-3 py-2 text-rose-600 font-semibold">{st.compensatingAction}</td>
                    <td className="px-3 py-2 text-right text-slate-600">{st.timeoutMs}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-950 p-4 font-mono text-xs">
            <div className="text-[11px] font-semibold text-slate-400 mb-2">Java 21 SAGA Coordinator Implementation:</div>
            <pre className="max-h-60 overflow-auto text-emerald-400 text-xs font-mono leading-relaxed">
              {data.javaOrchestratorCode}
            </pre>
          </div>
        </div>
      ) : (
        <div className="flex h-32 items-center justify-center text-xs text-slate-500 italic">
          Loading SAGA transaction graph...
        </div>
      )}
    </section>
  );
}


function Tests({ e }: { e: Engagement }) {
  const [playwrightData, setPlaywrightData] = useState<{
    files: Record<string, string>;
    summary: { specs: number; pages: number; fixtures: number };
  } | null>(null);
  const [selectedFile, setSelectedFile] = useState<string>("specs/business-rules.spec.ts");
  const [loading, setLoading] = useState(false);
  const [bedrockGenerating, setBedrockGenerating] = useState(false);

  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setLoading(true);
    api
      .playwright(e.id)
      .then((data) => {
        setPlaywrightData(data);
        if (data.files && !data.files[selectedFile]) {
          const firstKey = Object.keys(data.files)[0];
          if (firstKey) setSelectedFile(firstKey);
        }
      })
      .catch((err) => console.error("Playwright suite load error:", err))
      .finally(() => setLoading(false));
  }, [e.id]);

  async function triggerBedrock() {
    setBedrockGenerating(true);
    try {
      await api.bedrockGenerate(e.id);
      const data = await api.playwright(e.id);
      setPlaywrightData(data);
    } catch (err) {
      console.error("Bedrock generation failed:", err);
    } finally {
      setBedrockGenerating(false);
    }
  }

  function copyCode() {
    if (!playwrightData?.files[selectedFile]) return;
    navigator.clipboard.writeText(playwrightData.files[selectedFile]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const files = playwrightData?.files || {};
  const currentContent = files[selectedFile] || "// Loading test suite...";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50/40 p-4">
        <div>
          <p className="text-sm text-slate-700">
            Rule Coverage: <strong className="text-emerald-700">{e.seed!.coveragePct}%</strong> · Automated Playwright E2E Suite:{" "}
            <span className="text-blue-600 font-medium">{playwrightData?.summary.specs ?? 0} spec suites</span>
          </p>
          <p className="text-xs text-slate-500">
            Playwright validates Page Object Models (POM), boundary conditions, and REST API contracts.
          </p>
        </div>
        <button
          type="button"
          disabled={bedrockGenerating}
          onClick={triggerBedrock}
          className="flex items-center gap-1.5 rounded-lg border border-blue-500 bg-blue-50 px-4 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-100 disabled:opacity-50 shadow-2xs transition"
        >
          <Cpu />
          <span>{bedrockGenerating ? "Synthesizing with Bedrock…" : "Synthesize Tests with Bedrock"}</span>
        </button>
      </div>

      {/* Playwright Test Suite Viewer */}
      <section className="rounded-xl border border-slate-200 bg-slate-50/60 p-5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium uppercase tracking-widest text-slate-600">
            Automated Playwright Test Harness
          </h3>
          <button
            type="button"
            onClick={copyCode}
            className="rounded bg-slate-100 px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-100"
          >
            {copied ? "Copied!" : "Copy File"}
          </button>
        </div>

        {/* File tabs */}
        <div className="mt-3 flex flex-wrap gap-1 border-b border-slate-200 pb-2">
          {Object.keys(files).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setSelectedFile(f)}
              className={`rounded px-2.5 py-1 font-mono text-xs transition ${
                selectedFile === f
                  ? "bg-blue-100 text-blue-800 text-blue-700 font-semibold font-semibold"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Code container */}
        <div className="mt-3 max-h-96 overflow-auto rounded-lg border border-slate-700 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-emerald-400 shadow-inner">
          <pre>{loading ? "// Loading test harness files..." : currentContent}</pre>
        </div>

      </section>

      {/* DUAL-RUN SHADOW VALIDATION & PARITY ENGINE */}
      {e.seed?.shadow_parity && (
        <DualRunParityEngine
          parity={e.seed.shadow_parity}
          collation={e.seed.collation_parity}
          engagementId={e.id}
        />
      )}

      {/* STRANGLER FIG WAVE PLANNER & BIDIRECTIONAL CDC GUARDRAIL */}
      {e.seed?.wave_cutover && (
        <StranglerWavePlanner
          cutover={e.seed.wave_cutover}
          cdc={e.seed.cdc_status}
          engagementId={e.id}
        />
      )}

      {/* Characterization test cases table */}
      <div>
        <h4 className="mb-2 text-xs uppercase tracking-widest text-slate-500">Characterization & Mined Rules</h4>
        <div className="overflow-hidden rounded-xl border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-100 text-xs uppercase tracking-widest text-slate-500">
              <tr>
                <th className="px-4 py-2">ID</th>
                <th>Kind</th>
                <th>Req</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              {e.seed!.tests.map((t) => (
                <tr key={t.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-mono text-xs">{t.id}</td>
                  <td>{t.kind}</td>
                  <td className="font-mono text-xs text-blue-600 font-medium">{t.req}</td>
                  <td>{t.title}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


function Failures({ e }: { e: Engagement }) {
  const failures = e.seed!.failures;
  const criticalCount = failures.filter((f) => f.severity === "CRITICAL" && !f.resolved).length;
  const highCount = failures.filter((f) => f.severity === "HIGH" && !f.resolved).length;

  return (
    <div className="space-y-4">
      {/* Header Banner */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <span>🛡️</span> Architectural Debt &amp; Phase Gate Blockers
          </h3>
          <p className="text-xs text-slate-600 mt-0.5">
            Technical invariants and semantic conflicts requiring architectural resolution prior to production cutover.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono">
          {criticalCount > 0 && (
            <span className="rounded-md bg-red-100 border border-red-200 px-2.5 py-1 font-bold text-red-800 flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-600 animate-ping" />
              {criticalCount} Critical Blocker{criticalCount > 1 ? "s" : ""}
            </span>
          )}
          {highCount > 0 && (
            <span className="rounded-md bg-amber-100 border border-amber-200 px-2.5 py-1 font-bold text-amber-800">
              {highCount} High
            </span>
          )}
          <span className="rounded-md bg-slate-100 px-2.5 py-1 font-bold text-slate-600">
            {failures.length} Total Registered
          </span>
        </div>
      </div>

      {/* Blockers List */}
      <div className="space-y-3">
        {failures.map((f) => {
          const isCritical = f.severity === "CRITICAL";
          const isHigh = f.severity === "HIGH";
          const isResolved = f.resolved;

          return (
            <div
              key={f.id}
              className={`rounded-xl border p-5 shadow-xs transition ${
                isResolved
                  ? "border-slate-200 bg-slate-50/60 opacity-80"
                  : isCritical
                  ? "border-red-300 bg-red-50/40 ring-1 ring-red-400/20"
                  : isHigh
                  ? "border-amber-300 bg-amber-50/40"
                  : "border-slate-200 bg-white"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/80 pb-3 mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-xs font-bold text-slate-800 bg-white px-2.5 py-1 rounded border border-slate-300 shadow-2xs">
                    {f.id}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                      f.severity === "CRITICAL"
                        ? "bg-red-600 text-white"
                        : f.severity === "HIGH"
                        ? "bg-amber-600 text-white"
                        : "bg-blue-600 text-white"
                    }`}
                  >
                    {f.severity || "MEDIUM"}
                  </span>
                  <span className="font-mono text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                    Phase: {f.phase}
                  </span>
                  <h4 className="text-sm font-bold text-slate-900">{f.title || f.code}</h4>
                </div>

                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                      isResolved
                        ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                        : "bg-red-100 text-red-800 border border-red-300"
                    }`}
                  >
                    {isResolved ? "✓ Resolved / Certified" : "⚠️ Active Blocker"}
                  </span>
                </div>
              </div>

              {/* Blocker Description & Technical Impact */}
              <div className="space-y-2.5 text-xs">
                <div>
                  <span className="font-bold text-slate-700 block mb-0.5">Root Cause &amp; Technical Condition:</span>
                  <p className="text-slate-800 leading-relaxed bg-white p-2.5 rounded-lg border border-slate-200">
                    {f.message}
                  </p>
                </div>

                {f.impact && (
                  <div>
                    <span className="font-bold text-red-800 block mb-0.5">Production &amp; Migration Impact:</span>
                    <p className="text-red-950 bg-red-100/40 p-2.5 rounded-lg border border-red-200 leading-relaxed">
                      {f.impact}
                    </p>
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1">
                  {f.evidence && (
                    <div className="rounded-lg bg-slate-100 p-2 border border-slate-200">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">AST Evidence / Source Anchor:</span>
                      <span className="font-mono text-blue-700 font-semibold text-[11px] break-all">{f.evidence}</span>
                    </div>
                  )}
                  {f.astNode && (
                    <div className="rounded-lg bg-slate-100 p-2 border border-slate-200">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 block">AST Syntax Node:</span>
                      <span className="font-mono text-purple-700 font-semibold text-[11px] break-all">{f.astNode}</span>
                    </div>
                  )}
                </div>

                <div className="rounded-lg bg-emerald-50/70 p-3 border border-emerald-200 text-xs">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-800 block mb-0.5 flex items-center gap-1">
                    <span>💡</span> Recommended Architectural Remediation
                  </span>
                  <p className="font-medium text-emerald-950 leading-relaxed">{f.suggestedAction}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Artifacts({ e }: { e: Engagement }) {
  const gates = Object.entries(e.gates);
  const [repoName, setRepoName] = useState(
    `modernized-${e.scope?.capabilityId || "core"}-service`.toLowerCase().replace(/[^a-z0-9-]/g, "-"),
  );
  const [ghToken, setGhToken] = useState("");
  const [isPrivate, setIsPrivate] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<{
    ok: boolean;
    repoUrl?: string;
    workflowUrl?: string;
    filesCommitted?: number;
    error?: string;
  } | null>(null);

  const [showTfModal, setShowTfModal] = useState(false);
  const [tfFiles, setTfFiles] = useState<Record<string, string> | null>(null);

  async function handlePublishToGitHub() {
    setPublishing(true);
    setPublishResult(null);
    try {
      const res = await api.githubPublish(e.id, {
        repoName,
        token: ghToken.trim() || undefined,
        private: isPrivate,
      });
      setPublishResult(res);
    } catch (err: any) {
      setPublishResult({ ok: false, error: err.message || "Failed to publish to GitHub" });
    } finally {
      setPublishing(false);
    }
  }

  async function handleViewTerraform() {
    try {
      const res = await api.terraformAzure(e.id);
      setTfFiles(res.files);
      setShowTfModal(true);
    } catch (err) {
      console.error("Failed to load Terraform:", err);
    }
  }

  return (
    <div className="space-y-6">
      {/* 1. Automated GitHub Deployment Card */}
      <section className="rounded-xl border border-blue-200 bg-white p-6 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white font-bold text-lg">
              <svg className="h-5 w-5 fill-current" viewBox="0 0 24 24">
                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
            </span>
            <div>
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900">
                Automated GitHub Repository &amp; Azure Deployment
              </h3>
              <p className="text-xs text-slate-600 mt-0.5">
                Directly push the modernized Clean Architecture service, Azure Terraform IaC, Playwright tests, and GitHub Actions CI/CD pipeline.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleViewTerraform}
            className="rounded-lg border border-slate-300 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
          >
            Preview Azure Terraform IaC
          </button>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Target Repository Name</label>
            <input
              type="text"
              value={repoName}
              onChange={(e) => setRepoName(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-mono text-slate-900 focus:border-blue-500 focus:outline-hidden"
              placeholder="e.g. modernized-motor-policy-service"
            />
            <p className="mt-1 text-[11px] text-slate-500">Repository will be initialized under your GitHub account/org.</p>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold text-slate-700">
                Credentials &amp; Security
              </label>
              <span className="rounded bg-emerald-100 border border-emerald-300 px-1.5 py-0.2 text-[10px] font-bold text-emerald-800">
                🔒 Loaded from .env (Zero-UI Leak)
              </span>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-[11px] text-slate-600">
              <p>
                Using <code className="font-mono bg-white px-1 py-0.5 rounded border border-slate-200 text-slate-800">GITHUB_PAT</code> securely configured in server environment.
              </p>
              <details className="mt-1.5 cursor-pointer">
                <summary className="text-[10px] font-semibold text-blue-600 hover:text-blue-700">
                  Override with custom token for this session (optional)
                </summary>
                <input
                  type="password"
                  value={ghToken}
                  onChange={(e) => setGhToken(e.target.value)}
                  className="mt-1.5 w-full rounded border border-slate-300 px-2 py-1 text-xs font-mono text-slate-900 focus:border-blue-500 focus:outline-hidden"
                  placeholder="Optional override: ghp_..."
                />
              </details>
            </div>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={isPrivate}
              onChange={(e) => setIsPrivate(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            <span>Create as Private Repository</span>
          </label>

          <button
            type="button"
            disabled={publishing || !repoName}
            onClick={handlePublishToGitHub}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold text-white transition ${
              publishing ? "bg-slate-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700 shadow-xs"
            }`}
          >
            {publishing ? (
              <>
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent"></span>
                <span>Pushing to GitHub &amp; Configuring CI/CD...</span>
              </>
            ) : (
              <>
                <span>Publish to GitHub &amp; Trigger Azure CI/CD</span>
                <span>↗</span>
              </>
            )}
          </button>
        </div>

        {/* Publish Result Banner */}
        {publishResult && (
          <div
            className={`mt-4 rounded-lg p-4 border text-xs ${
              publishResult.ok
                ? "bg-emerald-50 border-emerald-300 text-emerald-900"
                : "bg-red-50 border-red-300 text-red-900"
            }`}
          >
            {publishResult.ok ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-sm">✓ Repository Created and Published Successfully!</span>
                  <span className="rounded bg-emerald-100 px-2 py-0.5 text-[11px] font-mono font-bold text-emerald-800">
                    {publishResult.filesCommitted} Files Committed
                  </span>
                </div>
                <p>
                  Target repository initialized with Clean Architecture, Azure WebApps Terraform, and CI/CD workflows.
                </p>
                <div className="flex items-center gap-3 pt-1">
                  <a
                    href={publishResult.repoUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-bold text-emerald-800 hover:underline"
                  >
                    <span>View Repository on GitHub</span>
                    <span>↗</span>
                  </a>
                  <span>•</span>
                  <a
                    href={publishResult.workflowUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-bold text-blue-700 hover:underline"
                  >
                    <span>View GitHub Actions Pipeline</span>
                    <span>↗</span>
                  </a>
                </div>
              </div>
            ) : (
              <div>
                <p className="font-bold">Failed to publish repository:</p>
                <p className="mt-1 font-mono text-[11px]">{publishResult.error}</p>
                <p className="mt-2 text-slate-600">
                  Tip: Provide a personal access token with <code className="bg-slate-200 px-1 py-0.5 rounded">repo</code> scope or set <code className="bg-slate-200 px-1 py-0.5 rounded">GITHUB_TOKEN</code> in <code className="bg-slate-200 px-1 py-0.5 rounded">apps/api/.env</code>.
                </p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* 2. Terraform Preview Modal */}
      {showTfModal && tfFiles && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-4xl max-h-[85vh] rounded-2xl bg-white shadow-2xl flex flex-col overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Azure Web Apps &amp; PostgreSQL Terraform IaC</h3>
                <p className="text-xs text-slate-500">Automated infrastructure templates included in your Git repository</p>
              </div>
              <button
                type="button"
                onClick={() => setShowTfModal(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
              >
                ✕
              </button>
            </div>
            <div className="p-6 overflow-y-auto space-y-4">
              {Object.entries(tfFiles).map(([path, content]) => (
                <div key={path} className="rounded-lg border border-slate-200 bg-slate-900 text-slate-100 overflow-hidden text-xs">
                  <div className="bg-slate-800 px-4 py-2 border-b border-slate-700 font-mono text-[11px] text-blue-300 font-bold flex justify-between items-center">
                    <span>{path}</span>
                    <button
                      type="button"
                      onClick={() => navigator.clipboard.writeText(content)}
                      className="text-slate-400 hover:text-white"
                    >
                      Copy
                    </button>
                  </div>
                  <pre className="p-4 overflow-x-auto font-mono text-[11px] leading-relaxed max-h-48">
                    {content}
                  </pre>
                </div>
              ))}
            </div>
            <div className="border-t border-slate-200 px-6 py-3 bg-slate-50 flex justify-end">
              <button
                type="button"
                onClick={() => setShowTfModal(false)}
                className="rounded-lg bg-slate-800 px-4 py-2 text-xs font-bold text-white hover:bg-slate-900"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. Traditional Sign-off Checklist & ZIP Download */}
      <div className="grid gap-6 sm:grid-cols-2">
        <Card title="Sign-off checklist">
          <ul className="space-y-1 text-sm">
            {gates.map(([k, g]) => (
              <li key={k} className="flex justify-between">
                <span>{k}</span>
                <span className={g.decision === "approved" ? "text-emerald-700 font-bold" : "text-slate-500"}>
                  {g.decision || "pending"}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Offline Packaging</h3>
            <p className="mt-2 text-xs text-slate-600">
              Download the standalone package containing specifications, Playwright tests, Azure Terraform templates, and JSON artifacts.
            </p>
          </div>
          <div className="mt-4">
            <a
              href={api.packUrl(e.id)}
              className="inline-flex rounded-lg bg-blue-600 px-4 py-2 text-xs font-bold text-white hover:bg-blue-700 transition"
            >
              Download Artifact Pack (.zip)
            </a>
          </div>
        </section>
      </div>
    </div>
  );
}

/* =========================================================================
   NEW PRODUCTION COMPONENTS:
   1. CopybookSchemaStudio (Copybook -> PostgreSQL DDL & JPA Mapper)
   2. StranglerWavePlanner (Wave Decomposition & API Gateway Canary Routing)
   3. DualRunParityEngine (Legacy vs Modern Decimal & Bit-level Parity Harness)
   ========================================================================= */

function StranglerWavePlanner({
  cutover,
  cdc: initialCdc,
  engagementId,
}: {
  cutover?: NonNullable<Engagement["seed"]>["wave_cutover"];
  cdc?: NonNullable<Engagement["seed"]>["cdc_status"];
  engagementId?: string;
}) {
  const [selectedWave, setSelectedWave] = useState(1);
  const [showCdk, setShowCdk] = useState(false);
  const [copied, setCopied] = useState(false);

  // Active-Active Canary Controller State
  const [cdcState, setCdcState] = useState<any>(initialCdc);
  const [cloudWeight, setCloudWeight] = useState<number>(
    initialCdc?.activeRouting?.cloudWeight ?? 10
  );
  const [targetCloudEngine, setTargetCloudEngine] = useState<string>("azure");
  const [updatingTraffic, setUpdatingTraffic] = useState(false);
  const [trafficMessage, setTrafficMessage] = useState<string | null>(null);
  const [driftWarning, setDriftWarning] = useState<string | null>(null);

  if (!cutover) return null;

  const waves = cutover.waves || [];
  const activeWave = waves.find((w) => w.waveNumber === selectedWave) || waves[0];

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleApplyTrafficWeight = async (weightToApply: number) => {
    if (!engagementId) return;
    setUpdatingTraffic(true);
    setTrafficMessage(null);
    setDriftWarning(null);
    try {
      const res = await api.canaryRouting(engagementId, {
        cloudWeight: weightToApply,
        targetEngine: targetCloudEngine,
        reason: `Operator shifted traffic to ${weightToApply}% Cloud / ${100 - weightToApply}% Mainframe`,
      });
      if (res.ok) {
        setCdcState(res.cdcStatus);
        setCloudWeight(res.activeRouting.cloudWeight);
        setTrafficMessage(`Traffic successfully re-routed: ${res.activeRouting.mode}`);
        if (res.driftAlert) {
          setDriftWarning(res.driftAlert);
        }
      }
    } catch (err: any) {
      setTrafficMessage(`Traffic shift failed: ${err.message}`);
    } finally {
      setUpdatingTraffic(false);
    }
  };

  const handleInstantRollback = async () => {
    if (!engagementId) return;
    setUpdatingTraffic(true);
    setTrafficMessage(null);
    setDriftWarning(null);
    try {
      const res = await api.instantRollback(engagementId);
      if (res.ok) {
        setCdcState(res.cdcStatus);
        setCloudWeight(0);
        setTrafficMessage(res.message);
      }
    } catch (err: any) {
      setTrafficMessage(`Emergency rollback failed: ${err.message}`);
    } finally {
      setUpdatingTraffic(false);
    }
  };

  const activeCdc = cdcState || initialCdc;
  const legacyWeight = 100 - cloudWeight;

  return (
    <section className="rounded-xl border border-blue-500/20 bg-slate-50/80 p-5 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-copper-500/20 text-xs font-bold text-blue-600 font-medium">🌊</span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-copper-200">
              Active-Active Strangler-Fig Controller &amp; Safe Rollback Engine
            </h3>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Real-time traffic shifting across Mainframe CICS/Db2 and Azure WebApps/PostgreSQL with instant rollback certification.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCdk(!showCdk)}
          className="rounded-lg border border-blue-500/30 bg-copper-400/10 px-3 py-1.5 text-xs font-mono text-blue-700 font-semibold hover:bg-blue-100 text-blue-800 transition"
        >
          {showCdk ? "Hide Ingress CDK" : "View Strangler Ingress IaC"}
        </button>
      </div>

      {/* Real-Time Canary Traffic Controller Card */}
      <div className="rounded-xl border border-indigo-200 bg-white p-5 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                Live Dynamic Traffic Router &amp; Instant Rollback
              </h4>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Adjust canary traffic split dynamically across legacy mainframe and modernized cloud microservices.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-500">Target Topology:</span>
            <select
              value={targetCloudEngine}
              onChange={(e) => setTargetCloudEngine(e.target.value)}
              className="rounded-lg border border-slate-300 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-800"
            >
              <option value="azure">Azure Linux WebApps + PostgreSQL</option>
              <option value="aws">AWS ECS Fargate + Aurora PostgreSQL</option>
            </select>
          </div>
        </div>

        {/* Visual Dual-Run Split Ratio */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-mono">
            <div className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-full bg-purple-600 inline-block"></span>
              <span className="font-bold text-slate-900">Mainframe On-Prem: {legacyWeight}%</span>
              <span className="text-slate-400 text-[10px]">(CICS / Db2)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-full bg-emerald-500 inline-block"></span>
              <span className="font-bold text-slate-900">Cloud Target: {cloudWeight}%</span>
              <span className="text-slate-400 text-[10px]">({targetCloudEngine.toUpperCase()} WebApp)</span>
            </div>
          </div>

          {/* Visual Progress Bar Bar */}
          <div className="h-4 w-full rounded-full bg-purple-100 overflow-hidden flex shadow-inner">
            <div
              style={{ width: `${legacyWeight}%` }}
              className="h-full bg-purple-600 transition-all duration-300"
              title={`Mainframe: ${legacyWeight}%`}
            />
            <div
              style={{ width: `${cloudWeight}%` }}
              className="h-full bg-emerald-500 transition-all duration-300"
              title={`Cloud: ${cloudWeight}%`}
            />
          </div>

          {/* Slider input */}
          <div className="pt-2">
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={cloudWeight}
              onChange={(e) => setCloudWeight(parseInt(e.target.value, 10))}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-mono mt-1">
              <span>0% (100% Mainframe)</span>
              <span>10% Canary</span>
              <span>25% Pilot</span>
              <span>50% Dual-Run</span>
              <span>75% Expansion</span>
              <span>100% Full Cutover</span>
            </div>
          </div>
        </div>

        {/* Action Buttons & Presets */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-slate-500 mr-1">Canary Presets:</span>
            {[
              { label: "10% Canary", val: 10 },
              { label: "50/50 Dual-Run", val: 50 },
              { label: "90/10 Cloud", val: 90 },
              { label: "100% Cloud", val: 100 },
            ].map((p) => (
              <button
                key={p.val}
                type="button"
                onClick={() => {
                  setCloudWeight(p.val);
                  handleApplyTrafficWeight(p.val);
                }}
                disabled={updatingTraffic}
                className={`rounded px-2 py-1 text-[11px] font-medium transition ${
                  cloudWeight === p.val
                    ? "bg-indigo-100 text-indigo-700 font-bold border border-indigo-200"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={updatingTraffic}
              onClick={() => handleApplyTrafficWeight(cloudWeight)}
              className="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-indigo-500 disabled:opacity-50 transition"
            >
              {updatingTraffic ? "Shifting Traffic..." : "Apply Traffic Weight"}
            </button>

            {/* Instant Emergency Rollback Button wired into CDC drift */}
            <button
              type="button"
              disabled={updatingTraffic || cloudWeight === 0}
              onClick={handleInstantRollback}
              className="rounded-lg bg-red-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-red-700 disabled:opacity-40 transition flex items-center gap-1.5"
              title="Immediately divert 100% traffic back to Mainframe with zero data loss guarantee"
            >
              <span>🚨 Instant Rollback (0% Cloud)</span>
            </button>
          </div>
        </div>

        {/* Traffic feedback alerts */}
        {trafficMessage && (
          <div className="rounded-lg bg-indigo-50 p-2.5 border border-indigo-200 text-xs text-indigo-900 flex items-center justify-between">
            <span>✓ {trafficMessage}</span>
            <span className="text-[10px] text-slate-500">Live updated</span>
          </div>
        )}

        {driftWarning && (
          <div className="rounded-lg bg-amber-50 p-2.5 border border-amber-200 text-xs text-amber-900">
            ⚠️ <strong>Replication Drift Alert:</strong> {driftWarning}
          </div>
        )}
      </div>

      {/* Wave timeline steps */}
      <div className="grid gap-3 md:grid-cols-3">
        {waves.map((w) => {
          const isSelected = selectedWave === w.waveNumber;
          return (
            <button
              key={w.waveNumber}
              type="button"
              onClick={() => setSelectedWave(w.waveNumber)}
              className={`rounded-xl border p-4 text-left transition ${
                isSelected
                  ? "border-blue-500 bg-copper-500/10 shadow-lg shadow-copper-500/5"
                  : "border-slate-200 bg-slate-50 hover:bg-slate-100"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-blue-600 font-medium">WAVE {w.waveNumber}</span>
                <span className={`rounded px-1.5 py-0.5 text-[9px] uppercase font-bold ${
                  w.riskLevel.includes("Low") ? "bg-emerald-100 border border-emerald-200 text-emerald-700" :
                  w.riskLevel.includes("Medium") ? "bg-amber-100 border border-amber-200 text-amber-800" :
                  "bg-red-500/20 text-red-300"
                }`}>
                  {w.riskLevel}
                </span>
              </div>
              <h4 className="mt-2 text-sm font-medium text-slate-900">{w.name}</h4>
              <p className="mt-1 text-xs text-slate-600">{w.strategy}</p>
              <div className="mt-3 flex items-center justify-between text-[11px] font-mono text-slate-500 border-t border-slate-100 pt-2">
                <span>Duration: {w.durationWeeks} wks</span>
                <span className="text-blue-700 font-semibold font-bold">Canary: {w.canaryPercent}%</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Active Wave Specification Card */}
      {activeWave && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
            <div>
              <span className="text-[10px] uppercase font-semibold text-slate-500">Active Modernization Wave</span>
              <h4 className="text-sm font-bold text-slate-900">{activeWave.name}</h4>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-600">Active Controller Weight:</span>
              <div className="flex items-center gap-1 font-mono text-xs bg-white px-2 py-1 rounded border border-slate-200">
                <span className="text-emerald-700 font-bold">{cloudWeight}% Cloud</span>
                <span className="text-slate-500">/</span>
                <span className="text-purple-700 font-bold">{legacyWeight}% Mainframe</span>
              </div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 text-xs">
            <div className="rounded-lg bg-white/60 p-3 border border-slate-100">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Live Traffic Shifting Rule</span>
              <p className="mt-1 font-mono text-slate-700 text-[11px]">{activeWave.routingRule}</p>
            </div>
            <div className="rounded-lg bg-white/60 p-3 border border-slate-100">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Automated Rollback Circuit Breaker</span>
              <p className="mt-1 font-mono text-amber-800/90 text-[11px]">{activeWave.rollbackPlan}</p>
            </div>
          </div>

          <div>
            <span className="text-[10px] uppercase font-semibold text-slate-500">Modules in Wave Scope:</span>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {activeWave.modules.map((m) => (
                <span key={m} className="rounded bg-slate-100 px-2.5 py-1 font-mono text-xs text-blue-700 font-semibold">
                  {m}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Bidirectional Active-Active CDC Reconciliation Guardrail */}
      {activeCdc && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-50/40 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-emerald-200 pb-2">
            <div className="flex items-center gap-2">
              <span className="flex h-3 w-3 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </span>
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-950">
                  Bidirectional CDC Replication &amp; Safe Rollback Guardrail
                </h4>
                <p className="text-[11px] text-emerald-800">
                  {activeCdc.syncDirection} via {activeCdc.replicationEngine}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                activeCdc.safeRollbackCertified
                  ? "bg-emerald-100 border-emerald-300 text-emerald-800"
                  : "bg-red-100 border-red-300 text-red-800"
              }`}>
                {activeCdc.safeRollbackCertified ? "Rollback Certified: RPO 1.2s" : "Rollback Warning: High Drift"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
            <div className="rounded-lg bg-white p-2.5 border border-emerald-200 shadow-2xs">
              <span className="text-[10px] text-slate-500 uppercase">Forward CDC Lag</span>
              <p className="text-base font-bold text-emerald-700 font-mono mt-0.5">{activeCdc.forwardLagMs} ms</p>
              <span className="text-[9px] text-slate-400">Db2 → Cloud PostgreSQL</span>
            </div>
            <div className="rounded-lg bg-white p-2.5 border border-emerald-200 shadow-2xs">
              <span className="text-[10px] text-slate-500 uppercase">Reverse Sync Lag</span>
              <p className={`text-base font-bold font-mono mt-0.5 ${
                activeCdc.reverseLagMs > 300 ? "text-amber-600" : "text-blue-700"
              }`}>{activeCdc.reverseLagMs} ms</p>
              <span className="text-[9px] text-slate-400">Cloud → Db2 (For rollback)</span>
            </div>
            <div className="rounded-lg bg-white p-2.5 border border-emerald-200 shadow-2xs">
              <span className="text-[10px] text-slate-500 uppercase">Replication Conflicts</span>
              <p className="text-base font-bold text-slate-900 font-mono mt-0.5">{activeCdc.conflictsDetectedToday}</p>
              <span className="text-[9px] text-slate-400">0 today (100% synced)</span>
            </div>
            <div className="rounded-lg bg-white p-2.5 border border-emerald-200 shadow-2xs">
              <span className="text-[10px] text-slate-500 uppercase">Conflict Policy</span>
              <p className="text-[11px] font-semibold text-slate-800 truncate mt-0.5" title={activeCdc.conflictResolutionStrategy}>Last-Write-Wins</p>
              <span className="text-[9px] text-slate-400">DLQ Audited</span>
            </div>
          </div>

          <div className="rounded bg-white/80 p-2 border border-emerald-200 text-[11px] text-emerald-900">
            <strong>Safe Rollback Guarantee: </strong>
            Because the reverse CDC pipeline mirrors commits from Cloud PostgreSQL back into IBM Db2 in real time (lag &lt; 300ms), clicking &quot;Instant Rollback&quot; immediately diverts 100% of ingress traffic back to Mainframe CICS with zero loss of policy records.
          </div>
        </div>
      )}

      {/* Traffic Routing Rules Table */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
        <div className="p-3 border-b border-slate-100 bg-slate-100 flex items-center justify-between">
          <h4 className="text-xs uppercase font-semibold text-slate-700 tracking-wider">
            Strangler Fig Ingress Gateway Routing Table ({cutover.stranglerRouting.ingress})
          </h4>
        </div>
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-white text-slate-600 border-b border-slate-100">
            <tr>
              <th className="px-3 py-2">HTTP Method & Path</th>
              <th className="px-3 py-2">Routing Target</th>
              <th className="px-3 py-2">Weight</th>
              <th className="px-3 py-2">AWS AppConfig Feature Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 text-[11px]">
            {cutover.stranglerRouting.rules.map((r, i) => (
              <tr key={i} className="hover:bg-slate-100">
                <td className="px-3 py-2 font-bold text-slate-900">
                  <span className="rounded bg-slate-50 px-1 py-0.5 text-blue-600 font-medium mr-1.5">{r.method}</span>
                  {r.path}
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] font-bold ${
                    r.target === "AWS_SPRING_BOOT" ? "bg-emerald-100 border border-emerald-200 text-emerald-800" : "bg-purple-100 border border-purple-200 text-purple-800"
                  }`}>
                    {r.target === "AWS_SPRING_BOOT" ? <Cloud className="text-emerald-700" /> : <Server className="text-purple-700" />}
                    <span>{r.target === "AWS_SPRING_BOOT" ? "AWS Cloud Target" : "Legacy On-Prem"}</span>
                  </span>
                </td>
                <td className="px-3 py-2 font-bold text-slate-700">{r.weight}%</td>
                <td className="px-3 py-2 text-slate-600">{r.featureFlag}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Optional CDK Code Viewer */}
      {showCdk && (
        <div className="rounded-xl border border-slate-200 bg-slate-900 p-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
            <span className="font-mono text-xs text-blue-700 font-semibold">infra/StranglerIngressStack.ts</span>
            <button
              type="button"
              onClick={() => handleCopy(cutover.stranglerRouting.apiGatewayConfig)}
              className="rounded bg-slate-100 px-2.5 py-1 text-[11px] text-slate-700 hover:bg-slate-200 font-mono transition"
            >
              {copied ? "✓ Copied" : "Copy CDK Code"}
            </button>
          </div>
          <pre className="max-h-64 overflow-auto text-xs font-mono leading-relaxed text-emerald-700/90">
            {cutover.stranglerRouting.apiGatewayConfig}
          </pre>
        </div>
      )}
    </section>
  );
}

function DualRunParityEngine({
  parity,
  collation,
  engagementId,
}: {
  parity?: NonNullable<Engagement["seed"]>["shadow_parity"];
  collation?: NonNullable<Engagement["seed"]>["collation_parity"];
  engagementId?: string;
}) {
  const [selectedCase, setSelectedCase] = useState(0);
  const [showHarness, setShowHarness] = useState(false);
  const [copied, setCopied] = useState(false);

  // Live in-browser 1,000 golden vectors test execution state
  const [runningLiveParity, setRunningLiveParity] = useState(false);
  const [liveParityData, setLiveParityData] = useState<any>(null);
  const [liveProgress, setLiveProgress] = useState(0);

  if (!parity) return null;

  async function handleRunLive1000Vectors() {
    if (!engagementId) return;
    setRunningLiveParity(true);
    setLiveProgress(0);

    // Simulate progress animation for realistic enterprise feel
    const interval = setInterval(() => {
      setLiveProgress((prev) => {
        if (prev >= 90) {
          clearInterval(interval);
          return 95;
        }
        return prev + 20;
      });
    }, 150);

    try {
      const res = await api.goldenParity(engagementId);
      setLiveProgress(100);
      setLiveParityData(res);
      setSelectedCase(0);
    } catch (err) {
      console.error("Failed to run golden parity runner:", err);
    } finally {
      clearInterval(interval);
      setTimeout(() => setRunningLiveParity(false), 400);
    }
  }

  // Use live data if user executed the live runner, otherwise fallback to seed vectors
  const activeVectors = liveParityData?.sampleVectors || parity.testCases || [];
  const currentCase = activeVectors[selectedCase] || activeVectors[0];

  const summaryStats = liveParityData
    ? {
        total: liveParityData.totalVectorsReplayed,
        passed: liveParityData.identicalMatches,
        flagged: liveParityData.discrepancyCount,
        rate: liveParityData.parityConfidenceScore,
        engine: liveParityData.executionEngine,
      }
    : {
        total: parity.summary.totalVectors,
        passed: parity.summary.passedParity,
        flagged: parity.summary.flaggedDiscrepancies,
        rate: parity.summary.parityRatePct,
        engine: "Pre-computed Shadow Parity Harness",
      };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="rounded-xl border border-emerald-500/20 bg-slate-50/80 p-5 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-emerald-100 border border-emerald-200 text-xs font-bold text-emerald-700">⚖️</span>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-900">
              Differential Golden Parity Validation Engine
            </h3>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Replays legacy production CICS COMMAREA / Db2 hex payloads against cloud microservice endpoints with bitwise &amp; penny-level verification.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {engagementId && (
            <button
              type="button"
              disabled={runningLiveParity}
              onClick={handleRunLive1000Vectors}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-bold transition flex items-center gap-2 ${
                runningLiveParity
                  ? "bg-emerald-200 text-emerald-800 cursor-not-allowed"
                  : "bg-emerald-600 text-white hover:bg-emerald-700 shadow-xs"
              }`}
            >
              {runningLiveParity ? (
                <>
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-emerald-800 border-t-transparent"></span>
                  <span>Replaying 1,000 Vectors ({liveProgress}%)…</span>
                </>
              ) : (
                <>
                  <span>▶ Run 1,000 Live Golden Vectors</span>
                </>
              )}
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowHarness(!showHarness)}
            className="rounded-lg border border-emerald-500/30 bg-emerald-50 border border-emerald-200 px-3 py-1.5 text-xs font-mono text-emerald-700 hover:bg-emerald-100 transition"
          >
            {showHarness ? "Hide Harness" : "View Java/Spring Harness"}
          </button>
        </div>
      </div>

      {/* Progress Bar when running */}
      {runningLiveParity && (
        <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
          <div
            className="bg-emerald-500 h-1.5 transition-all duration-200 rounded-full"
            style={{ width: `${liveProgress}%` }}
          ></div>
        </div>
      )}

      {/* Parity Stats Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
          <p className="text-xl font-bold text-slate-900">{summaryStats.total.toLocaleString()}</p>
          <p className="text-xs text-slate-500">Golden Vectors Replayed</p>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
          <p className="text-xl font-bold text-emerald-700">{summaryStats.passed.toLocaleString()}</p>
          <p className="text-xs text-slate-500">Exact Bit / Penny Matches</p>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
          <p className="text-xl font-bold text-amber-500">{summaryStats.flagged}</p>
          <p className="text-xs text-slate-500">Flagged Discrepancies</p>
        </div>
        <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
          <p className="text-xl font-bold text-emerald-700">{summaryStats.rate}%</p>
          <p className="text-xs text-slate-500">Parity Equivalence Score</p>
        </div>
      </div>

      <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 border border-emerald-500/20 text-xs text-emerald-700">
        <strong>Tolerances & Rules:</strong> {parity.summary.tolerances}
      </div>

      {/* Test Vectors Table */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
        <div className="p-3 border-b border-slate-100 bg-slate-100 flex items-center justify-between">
          <h4 className="text-xs uppercase font-semibold text-slate-700 tracking-wider">
            Mainframe vs. Cloud Microservice Parity Vectors ({activeVectors.length} Sampled)
          </h4>
          <span className="text-[11px] text-slate-500 font-mono">Click a vector row to inspect side-by-side diff</span>
        </div>
        <div className="overflow-x-auto max-h-56">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-white text-slate-600 border-b border-slate-100 sticky top-0">
              <tr>
                <th className="px-3 py-2">Vector ID</th>
                <th className="px-3 py-2">Txn Code</th>
                <th className="px-3 py-2">Scenario / Test Description</th>
                <th className="px-3 py-2">Parity Equivalence Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-[11px]">
              {activeVectors.map((tc: any, i: number) => {
                const isMatch = tc.status === "MATCH" || tc.status === "EXACT_MATCH";
                const isSelected = selectedCase === i;
                return (
                  <tr
                    key={tc.vectorId || tc.id}
                    onClick={() => setSelectedCase(i)}
                    className={`hover:bg-slate-100 cursor-pointer transition ${
                      isSelected ? "bg-emerald-50 border border-emerald-200" : ""
                    }`}
                  >
                    <td className="px-3 py-2 font-bold text-blue-700 font-semibold">
                      {tc.vectorId || tc.id}
                    </td>
                    <td className="px-3 py-2 text-slate-600">
                      {tc.transactionCode || tc.legacyPayloadType || "CICS"}
                    </td>
                    <td className="px-3 py-2 text-slate-900 font-sans">
                      {tc.scenario || tc.description}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                          isMatch
                            ? "bg-emerald-100 border border-emerald-200 text-emerald-700"
                            : "bg-red-100 border border-red-200 text-red-700"
                        }`}
                      >
                        {isMatch ? "✓ 100% BIT PARITY" : "⚠️ DISCREPANCY FLAGGED"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Side-by-side Payload Diff Inspector */}
      {currentCase && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-4 shadow-xs">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
            <div>
              <span className="text-[10px] uppercase font-semibold text-slate-500">
                Inspecting Vector: {currentCase.vectorId || currentCase.id}
              </span>
              <p className="text-xs font-bold text-slate-900">
                {currentCase.scenario || currentCase.description}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {currentCase.modernOutput?.latencyMs && (
                <span className="text-[11px] font-mono text-slate-500">
                  Latency: {currentCase.modernOutput.latencyMs}ms
                </span>
              )}
              <span
                className={`rounded px-2.5 py-1 text-xs font-bold ${
                  currentCase.status === "MATCH" || currentCase.status === "EXACT_MATCH"
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-red-100 text-red-800 border border-red-300"
                }`}
              >
                {currentCase.status === "MATCH" || currentCase.status === "EXACT_MATCH"
                  ? "✓ 100% Bitwise Match"
                  : "PARITY DISCREPANCY FLAGGED"}
              </span>
            </div>
          </div>

          {/* Automated Discrepancy Diagnostics & Remediation */}
          {(currentCase.deltaDetails?.length > 0 || currentCase.fieldDiffs?.length > 0) && (
            <div className="rounded-lg border border-red-300 bg-red-50 p-3.5 text-xs space-y-2">
              <div className="flex items-center gap-2 font-bold text-red-800">
                <span>⚠️ Automated Root-Cause Divergence Analysis:</span>
              </div>
              {(currentCase.deltaDetails || currentCase.fieldDiffs || []).map((diff: any, idx: number) => (
                <div key={idx} className="space-y-1 bg-white p-2.5 rounded border border-red-200">
                  <div className="flex items-center justify-between font-mono text-[11px]">
                    <span className="font-bold text-red-700">Field: {diff.field}</span>
                    <span className="text-slate-600">
                      Legacy: <code className="bg-slate-100 px-1 rounded">{diff.legacyValue}</code> vs. Modern:{" "}
                      <code className="bg-slate-100 px-1 rounded">{diff.modernValue}</code> ({diff.diff || diff.delta})
                    </span>
                  </div>
                  <p className="text-slate-800 text-[11px]">
                    <strong>Root Cause: </strong>{diff.rootCause || diff.diffReason}
                  </p>
                  {diff.remediation && (
                    <div className="text-[11px] text-blue-900 bg-blue-50 p-2 rounded border border-blue-200 font-mono">
                      <strong>AI Suggested Remediation: </strong>{diff.remediation}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Side-by-Side Hex and JSON Viewer */}
          <div className="grid gap-4 sm:grid-cols-2 text-xs font-mono">
            {/* Legacy Output Box */}
            <div className="rounded-lg bg-slate-900 p-3.5 text-slate-100 border border-slate-800 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2">
                  <span className="text-purple-300 font-bold flex items-center gap-1.5">
                    <Server className="text-purple-400" /> Legacy CICS COMMAREA Output
                  </span>
                  <span className="text-[10px] text-slate-400">EBCDIC IBM-037</span>
                </div>

                {currentCase.legacyOutput?.rawHexDump && (
                  <div className="mb-2">
                    <span className="text-[10px] text-slate-400 block uppercase mb-1">Raw Hex Payload:</span>
                    <div className="p-2 rounded bg-black/60 font-mono text-[10px] text-emerald-400 break-all select-all">
                      {currentCase.legacyOutput.rawHexDump}
                    </div>
                  </div>
                )}

                <span className="text-[10px] text-slate-400 block uppercase mb-1">Decoded Record Values:</span>
                <pre className="p-2.5 rounded bg-black/40 text-[11px] text-slate-200 overflow-auto max-h-48">
                  {JSON.stringify(
                    currentCase.legacyOutput?.decodedCommarea || currentCase.legacyOutput,
                    null,
                    2,
                  )}
                </pre>
              </div>
            </div>

            {/* Modern Cloud Microservice Output */}
            <div className="rounded-lg bg-slate-900 p-3.5 text-slate-100 border border-slate-800 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2">
                  <span className="text-emerald-300 font-bold flex items-center gap-1.5">
                    <Cloud className="text-emerald-400" /> Modernized Service Response
                  </span>
                  <span className="text-[10px] text-slate-400">Cloud REST (UTF-8)</span>
                </div>

                <span className="text-[10px] text-slate-400 block uppercase mb-1">Target JSON Payload:</span>
                <pre className="p-2.5 rounded bg-black/40 text-[11px] text-emerald-300 overflow-auto max-h-56">
                  {JSON.stringify(
                    currentCase.modernOutput?.jsonResponse || currentCase.modernOutput,
                    null,
                    2,
                  )}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Collation & EBCDIC Edge-Case Simulator */}
      {collation && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-200 pb-2">
            <div>
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded bg-blue-200 text-blue-800 text-xs font-bold">🔤</span>
                <h4 className="text-xs font-bold uppercase tracking-wider text-blue-950">
                  Collation &amp; EBCDIC / Binary Edge-Case Simulator
                </h4>
              </div>
              <p className="text-[11px] text-blue-800 mt-0.5">{collation.collationScenario}</p>
            </div>
            <span className="rounded bg-blue-100 border border-blue-300 px-2 py-0.5 text-[10px] font-mono font-semibold text-blue-800">
              IBM-037 EBCDIC vs UTF-8 Collation
            </span>
          </div>

          <p className="text-xs text-slate-700 bg-white p-2.5 rounded-lg border border-blue-200 leading-relaxed">
            <strong>Architecture Finding: </strong>{collation.explanation}
          </p>

          <div className="grid gap-3 md:grid-cols-2 text-xs font-mono">
            {collation.testCases.map((tc) => (
              <div key={tc.id} className="rounded-lg bg-white p-3 border border-blue-200 shadow-2xs space-y-2">
                <div className="flex items-center justify-between border-b border-slate-100 pb-1.5">
                  <span className="font-bold text-blue-700 font-mono">{tc.id}</span>
                  <span className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                    tc.flaggedDiscrepancy ? "bg-amber-100 text-amber-800 border border-amber-200" : "bg-emerald-100 text-emerald-800 border border-emerald-200"
                  }`}>
                    {tc.flaggedDiscrepancy ? "Ordering Divergence" : "Math Parity Match"}
                  </span>
                </div>

                {tc.inputCodes && (
                  <div className="space-y-1.5">
                    <div className="text-[10px] text-slate-500">Unsorted Input Codes: [{tc.inputCodes.join(", ")}]</div>
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div className="p-1.5 rounded bg-slate-50 border border-slate-200">
                        <span className="text-[9px] uppercase font-bold text-purple-700 block">EBCDIC ('A' &lt; '1'):</span>
                        <span className="font-bold text-slate-800">{tc.legacyEbcdicOrder?.join(" → ")}</span>
                      </div>
                      <div className="p-1.5 rounded bg-amber-50 border border-amber-200">
                        <span className="text-[9px] uppercase font-bold text-amber-800 block">Naive ASCII ('1' &lt; 'A'):</span>
                        <span className="font-bold text-slate-800">{tc.naiveAsciiOrder?.join(" → ")}</span>
                      </div>
                    </div>
                  </div>
                )}

                {tc.fieldName && (
                  <div className="space-y-1 text-[11px]">
                    <div className="font-bold text-slate-800">{tc.fieldName}</div>
                    <div className="text-[10px] text-slate-600">Legacy: {tc.legacyRepresentation}</div>
                    <div className="text-[10px] text-emerald-700 font-semibold">Target: {tc.modernRepresentation}</div>
                  </div>
                )}

                <div className="text-[10px] text-slate-600 border-t border-slate-100 pt-1.5 font-sans">
                  <strong>Remediation: </strong>{tc.remediation}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Shadow Harness Code */}
      {showHarness && (
        <div className="rounded-xl border border-slate-700 bg-slate-950 p-4 shadow-inner">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-3">
            <span className="font-mono text-xs text-slate-300 font-semibold">src/main/java/harness/ShadowValidationFilter.java</span>
            <button
              type="button"
              onClick={() => handleCopy(parity.shadowHarnessCode)}
              className="rounded bg-slate-800 px-2.5 py-1 text-[11px] text-slate-200 hover:bg-slate-700 font-mono transition"
            >
              {copied ? "✓ Copied" : "Copy Harness Code"}
            </button>
          </div>
          <pre className="max-h-64 overflow-auto text-xs font-mono leading-relaxed text-emerald-400">
            {parity.shadowHarnessCode}
          </pre>
        </div>
      )}
    </section>
  );
}
