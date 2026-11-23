import { useEffect, useMemo, useState } from "react";
import { api, type AppliedGraph, type WorkflowChain, type SharedKernel, type CodeWorkflow } from "../api";
import { AKGGraphView } from "./AKGGraphView";

// ─── colour maps ────────────────────────────────────────────────────────────

const RISK_CLS: Record<string, string> = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high:     "bg-amber-100 text-amber-700 border-amber-200",
  medium:   "bg-yellow-50 text-yellow-700 border-yellow-200",
  low:      "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const ROLE_CLS: Record<string, string> = {
  "orchestrator":        "bg-purple-100 text-purple-700",
  "data-access-gateway": "bg-blue-100 text-blue-700",
  "screen-boundary":     "bg-pink-100 text-pink-700",
  "batch-entry-point":   "bg-amber-100 text-amber-700",
  "event-publisher":     "bg-teal-100 text-teal-700",
  "business-logic":      "bg-slate-100 text-slate-600",
  "domain-event":        "bg-emerald-100 text-emerald-700",
  "data-entity":         "bg-emerald-100 text-emerald-700",
  "integration-adapter": "bg-orange-100 text-orange-700",
  "external-system":     "bg-orange-100 text-orange-700",
};

const EDGE_CLS: Record<string, string> = {
  CALLS:        "text-purple-700 bg-purple-50 border-purple-200",
  READS:        "text-blue-700 bg-blue-50 border-blue-200",
  WRITES:       "text-red-700 bg-red-50 border-red-200",
  MAPS_TO:      "text-pink-700 bg-pink-50 border-pink-200",
  TRIGGERED_BY: "text-amber-700 bg-amber-50 border-amber-200",
  OWNS_DATA:    "text-emerald-700 bg-emerald-50 border-emerald-200",
  EMITS_EVENT:  "text-teal-700 bg-teal-50 border-teal-200",
  CONTAINS:     "text-slate-600 bg-slate-50 border-slate-200",
  ACCESSES_DATA:    "text-red-700 bg-red-50 border-red-200",
  HTTP_CALLS:       "text-pink-700 bg-pink-50 border-pink-200",
  INVOKES_EXTERNAL: "text-orange-700 bg-orange-50 border-orange-200",
  REFERENCES:       "text-emerald-700 bg-emerald-50 border-emerald-200",
  INHERITS:         "text-slate-600 bg-slate-50 border-slate-200",
  IMPLEMENTS:       "text-slate-600 bg-slate-50 border-slate-200",
};

function location(file?: string, line?: number) {
  return file ? `${file}:${line ?? 1}` : "—";
}

// ─── helpers ────────────────────────────────────────────────────────────────

function riskBadge(risk: string | undefined) {
  if (!risk) return null;
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${RISK_CLS[risk] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
      {risk}
    </span>
  );
}

function shortId(id: string) {
  const parts = id.split(/[:/]/);
  return parts[parts.length - 1] || id;
}

// ─── types ──────────────────────────────────────────────────────────────────

type Tab = "graph" | "overview" | "nodes" | "edges" | "lineage" | "workflows" | "chains" | "kernels";

const TABS: [Tab, string][] = [
  ["graph",     "Graph View"],
  ["overview",  "Overview"],
  ["nodes",     "Semantic Nodes"],
  ["edges",     "Edge Semantics"],
  ["lineage",   "Data Lineage"],
  ["workflows", "Code Workflows"],
  ["chains",    "Workflow Chains"],
  ["kernels",   "Shared Kernels"],
];

// ─── component ──────────────────────────────────────────────────────────────

export function AppliedKnowledgeGraph({ engagementId }: { engagementId: string }) {
  const [graph, setGraph]         = useState<AppliedGraph | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [tab, setTab]             = useState<Tab>("graph");
  const [search, setSearch]       = useState("");
  const [openChain, setOpenChain] = useState<string | null>(null);
  const [graphCapFilter, setGraphCapFilter] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api.knowledgeGraph(engagementId)
      .then(setGraph)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [engagementId]); // eslint-disable-line react-hooks/exhaustive-deps

  const q = search.toLowerCase();

  const filteredNodes = useMemo(
    () => graph?.nodes.filter(
      (n) => !q || n.id.toLowerCase().includes(q) || n.label.toLowerCase().includes(q) || (n.semanticRole ?? "").includes(q)
    ) ?? [],
    [graph, q],
  );

  const filteredEdges = useMemo(
    () => graph?.edges.filter(
      (e) => !q || e.source.toLowerCase().includes(q) || e.target.toLowerCase().includes(q) || e.kind.toLowerCase().includes(q)
    ) ?? [],
    [graph, q],
  );

  const filteredLineage = useMemo(
    () => graph?.dataLineage.filter(
      (l) => !q || l.sourceField.toLowerCase().includes(q) || l.targetColumn.toLowerCase().includes(q) || l.source.toLowerCase().includes(q)
    ) ?? [],
    [graph, q],
  );

  const filteredChains = useMemo(
    () => graph?.workflowChains.filter(
      (c) => !q || c.sirRule.toLowerCase().includes(q) || c.requirement.toLowerCase().includes(q) || c.backlogItem.toLowerCase().includes(q)
    ) ?? [],
    [graph, q],
  );

  const filteredWorkflows = useMemo(
    () => (graph?.codeWorkflows ?? []).filter(
      (w) => !q || w.entryPoint.toLowerCase().includes(q)
        || (w.trigger?.url ?? "").toLowerCase().includes(q)
        || w.writes.some((x) => x.toLowerCase().includes(q))
    ),
    [graph, q],
  );

  const stats = graph?.statistics;
  const hasCodeWorkflows = (graph?.codeWorkflows?.length ?? 0) > 0;

  return (
    <section className="rounded-xl border border-indigo-200 bg-white shadow-sm overflow-hidden">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-indigo-100 bg-gradient-to-r from-indigo-50 to-slate-50 px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white text-sm font-bold shadow-sm">
            AKG
          </span>
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900">
              Applied Knowledge Graph
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              AST edges enriched with domain semantics, data lineage, workflow trace chains &amp; shared-kernel coupling
            </p>
          </div>
        </div>
        <button
          type="button"
          disabled={loading}
          onClick={load}
          className="rounded-lg border border-indigo-300 bg-white px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 transition"
        >
          {loading ? "Building…" : "Rebuild AKG"}
        </button>
      </div>

      {/* ── Error ── */}
      {error && (
        <p className="m-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</p>
      )}

      {/* ── Loading skeleton ── */}
      {loading && !graph && (
        <div className="flex items-center justify-center gap-2 p-10 text-sm text-slate-500">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
          Building Applied Knowledge Graph…
        </div>
      )}

      {graph && stats && (
        <>
          {/* ── Stat bar ── */}
          <div className="grid grid-cols-3 sm:grid-cols-6 divide-x divide-slate-100 border-b border-slate-100 bg-slate-50 text-center text-xs">
            {([
              ["Nodes",          stats.totalNodes],
              ["Edges",          stats.totalEdges],
              ["Lineage Fields", stats.dataLineageFields],
              ...(hasCodeWorkflows
                ? [["Workflows", stats.codeWorkflows ?? 0],
                   ["Fully Traced", `${stats.fullyTracedCodeWorkflows ?? 0}/${stats.codeWorkflows ?? 0}`]]
                : [["Chains", stats.totalWorkflowChains],
                   ["Traced", `${stats.tracedWorkflowChains}/${stats.totalWorkflowChains}`]]),
              ["Shared Kernels", stats.sharedKernelCount],
            ] as [string, string | number][]).map(([label, val]) => (
              <div key={label} className="py-3 px-2">
                <p className="text-base font-bold text-slate-900">{val}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</p>
              </div>
            ))}
          </div>

          {/* ── Tab bar ── */}
          <div className="flex flex-wrap border-b border-slate-200 bg-white px-4">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => { setTab(id); setSearch(""); }}
                className={`border-b-2 px-4 py-3 text-xs font-medium transition ${
                  tab === id
                    ? "border-indigo-600 text-indigo-700 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="p-5 space-y-4">

            {/* ── GRAPH VIEW ── */}
            {tab === "graph" && (
              <div className="space-y-3">
                {/* Capability filter pills */}
                <div className="flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    onClick={() => setGraphCapFilter(null)}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                      !graphCapFilter ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    All
                  </button>
                  {graph.nodes
                    .filter((n) => n.type === "capability")
                    .map((cap) => {
                      const capKey = cap.capability || cap.id.replace("CAP-", "");
                      return (
                        <button
                          key={cap.id}
                          type="button"
                          onClick={() => setGraphCapFilter(capKey)}
                          className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                            graphCapFilter === capKey
                              ? "bg-indigo-600 text-white"
                              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                          }`}
                        >
                          {cap.label}
                        </button>
                      );
                    })}
                </div>
                <AKGGraphView graph={graph} highlightCapability={graphCapFilter} />
                <p className="text-[11px] text-slate-400 italic">
                  Blue = programs · Green = tables · Teal = events · Indigo = capabilities. Drag to pan, scroll to zoom.
                </p>
              </div>
            )}

            {/* Search — all tabs except overview and graph */}
            {tab !== "overview" && tab !== "graph" && (
              <input
                placeholder="Search…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:outline-none focus:border-indigo-400"
              />
            )}

            {/* ── OVERVIEW ── */}
            {tab === "overview" && (
              <div className="space-y-5">

                {/* Edge kind pills */}
                <div>
                  <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mb-2">
                    Edge Relationship Breakdown
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(stats.edgesByKind).map(([kind, count]) => (
                      <span key={kind} className={`rounded-full border px-3 py-1 text-xs font-semibold ${EDGE_CLS[kind] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
                        {kind} · {count}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Semantic role pills */}
                <div>
                  <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mb-2">
                    Semantic Node Roles
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(graph.semanticIndex.nodesByRole).map(([role, ids]) => (
                      <span key={role} className={`rounded-full px-3 py-1 text-xs font-medium ${ROLE_CLS[role] ?? "bg-slate-100 text-slate-600"}`}>
                        {role.replace(/-/g, " ")} · {ids.length}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Trust boundary grid */}
                <div>
                  <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mb-2">
                    Trust Boundary Distribution
                  </p>
                  {Object.keys(graph.semanticIndex.nodesByTrustBoundary).length === 0 ? (
                    <p className="text-xs text-slate-400 italic">No trust boundaries inferred yet.</p>
                  ) : (
                    <div className="grid gap-2 sm:grid-cols-2">
                      {Object.entries(graph.semanticIndex.nodesByTrustBoundary).map(([boundary, ids]) => (
                        <div key={boundary} className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs">
                          <span className="font-medium text-slate-700 truncate mr-2" title={boundary}>{boundary}</span>
                          <span className="shrink-0 rounded-full bg-white border border-slate-200 px-2 py-0.5 font-mono text-slate-500">{ids.length}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Extraction diagnostics: what could not be resolved, never silently guessed */}
                {graph.diagnostics && Object.keys(graph.diagnostics).length > 0 && (
                  <div>
                    <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mb-2">
                      Extraction Diagnostics
                    </p>
                    <div className="space-y-1.5">
                      {Object.entries(graph.diagnostics).map(([key, rows]) => (
                        <details key={key} className="rounded-lg border border-amber-200 bg-amber-50/50 px-3 py-2 text-xs">
                          <summary className="cursor-pointer font-medium text-amber-800">
                            {key.replace(/([A-Z])/g, " $1").toLowerCase()} · {rows.length}
                          </summary>
                          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[10px] text-slate-600">
                            {rows.slice(0, 50).map((r) => (typeof r === "string" ? r : JSON.stringify(r))).join("\n")}
                          </pre>
                        </details>
                      ))}
                    </div>
                  </div>
                )}

                <p className="text-[11px] text-slate-400 italic">{graph.basis}</p>
                {graph.engine && <p className="text-[10px] text-slate-400 font-mono">engine: {graph.engine}</p>}
              </div>
            )}

            {/* ── SEMANTIC NODES ── */}
            {tab === "nodes" && (
              <div className="overflow-hidden rounded-xl border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-100 text-slate-500 text-[10px] uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-2.5">Label</th>
                      <th className="px-3 py-2.5">Type</th>
                      <th className="px-3 py-2.5">Capability</th>
                      <th className="px-3 py-2.5">Semantic Role</th>
                      <th className="px-3 py-2.5">Trust Boundary</th>
                      <th className="px-3 py-2.5">SIR Rules</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredNodes.map((n) => (
                      <tr key={n.id} className="border-t border-slate-100 hover:bg-slate-50">
                        <td className="px-4 py-2.5 font-mono font-bold text-indigo-700 max-w-[160px] truncate" title={n.id}>
                          {n.label.replace("\n", " · ")}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase font-semibold text-slate-600">
                            {n.type}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[10px] text-slate-500">{n.capability}</td>
                        <td className="px-3 py-2.5">
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${ROLE_CLS[n.semanticRole ?? ""] ?? "bg-slate-100 text-slate-600"}`}>
                            {(n.semanticRole ?? "—").replace(/-/g, " ")}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-[11px] text-slate-600 max-w-[180px] truncate" title={n.trustBoundary}>
                          {n.trustBoundary ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[10px] text-purple-700">
                          {n.sirRules && n.sirRules.length > 0 ? n.sirRules.join(", ") : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredNodes.length === 0 && (
                  <p className="p-5 text-sm text-slate-500">No nodes match.</p>
                )}
              </div>
            )}

            {/* ── EDGE SEMANTICS ── */}
            {tab === "edges" && (
              <div className="overflow-hidden rounded-xl border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-100 text-slate-500 text-[10px] uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-2.5">Source</th>
                      <th className="px-3 py-2.5">Kind</th>
                      <th className="px-3 py-2.5">Target</th>
                      <th className="px-3 py-2.5">Semantic Type</th>
                      <th className="px-3 py-2.5">Evidence</th>
                      <th className="px-3 py-2.5">Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredEdges.map((e) => (
                      <tr key={e.id} className="border-t border-slate-100 hover:bg-slate-50">
                        <td className="px-4 py-2.5 font-mono text-[11px] text-slate-700 max-w-[130px]" title={e.source}>
                          <span className="block truncate">{shortId(e.source)}</span>
                          {e.source !== shortId(e.source) && (
                            <span className="text-[9px] text-slate-400 truncate block">{e.source.split(":")[0]}</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${EDGE_CLS[e.kind] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
                            {e.kind}
                          </span>
                          {e.operations && (
                            <span className="block mt-1 text-[9px] font-mono text-slate-500">{e.operations.join(" + ")}</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-[11px] text-slate-700 max-w-[130px]" title={e.target}>
                          <span className="block truncate">{shortId(e.target)}</span>
                          {e.target !== shortId(e.target) && (
                            <span className="text-[9px] text-slate-400 truncate block">{e.target.split(":")[0]}</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-[11px] text-slate-600" title={e.modernEquivalent}>{e.semanticType ?? "—"}</td>
                        <td
                          className="px-3 py-2.5 font-mono text-[10px] text-slate-600 max-w-[220px]"
                          title={(e.evidence ?? []).map((ev) => `${ev.file}:${ev.line} [${ev.rule_id}]`).join("\n")}
                        >
                          <span className="block truncate">{location(e.file, e.line)}</span>
                          {e.rule_id && (
                            <span className="block truncate text-[9px] text-slate-400">
                              {e.rule_id}{(e.evidence?.length ?? 0) > 1 ? ` · +${e.evidence!.length - 1} sites` : ""}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2.5">{riskBadge(e.migrationRisk)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filteredEdges.length === 0 && (
                  <p className="p-5 text-sm text-slate-500">No edges match.</p>
                )}
              </div>
            )}

            {/* ── DATA LINEAGE ── */}
            {tab === "lineage" && (
              <div className="space-y-2">
                {filteredLineage.length === 0 && (
                  <p className="text-sm text-slate-500">
                    No field lineage available. Lineage is derived from mapping declarations (AutoMapper) and the
                    source&apos;s own data model (EF migration snapshot or copybooks); nothing is synthesised.
                  </p>
                )}
                {filteredLineage.map((l) => (
                  <div key={l.id} className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono font-bold text-slate-700">{l.source}</span>
                      <span className="text-slate-300">·</span>
                      <span className="font-mono text-blue-700 font-semibold">{l.sourceField}</span>
                      <span className="text-slate-400 text-[10px]">({l.sourceType})</span>
                      <span className="text-slate-400 font-bold">→</span>
                      <span className="font-mono font-bold text-slate-700">{l.target}</span>
                      <span className="text-slate-300">·</span>
                      <span className="font-mono text-emerald-700 font-semibold">{l.targetColumn}</span>
                      <span className="text-slate-400 text-[10px]">({l.targetType})</span>
                      <span className="ml-auto">{riskBadge(l.migrationRisk)}</span>
                    </div>
                    {l.conversionNote && (
                      <p className="mt-1.5 text-[11px] text-slate-500 italic">{l.conversionNote}</p>
                    )}
                    {l.file && (
                      <p className="mt-1 font-mono text-[10px] text-slate-400">
                        {l.entityProperty && <>via {l.entityProperty} · </>}{location(l.file, l.line)} · {l.rule_id}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* ── CODE WORKFLOWS ── */}
            {tab === "workflows" && (
              <div className="space-y-2">
                {filteredWorkflows.length === 0 && (
                  <p className="text-sm text-slate-500">
                    No code workflows. Workflows are traced from front-end HTTP calls, public controller actions and
                    Application_Start through calls to data writes and external integrations.
                  </p>
                )}
                {filteredWorkflows.map((w: CodeWorkflow) => {
                  const open = openChain === w.id;
                  return (
                    <div key={w.id} className="rounded-lg border border-slate-200 bg-white overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setOpenChain(open ? null : w.id)}
                        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-50 transition"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="text-[10px] text-slate-400 shrink-0">{open ? "▼" : "▶"}</span>
                          {w.trigger && (
                            <span className="shrink-0 rounded border border-pink-200 bg-pink-50 px-1.5 py-0.5 font-mono text-[10px] font-bold text-pink-700">
                              {w.trigger.verb}
                            </span>
                          )}
                          <span className="font-mono text-xs font-semibold text-slate-800 truncate" title={w.entryPoint}>
                            {w.trigger ? w.trigger.url : w.entryPoint.split(".").slice(-2).join(".")}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          {w.writes.map((x) => (
                            <span key={x} className="rounded border border-red-200 bg-red-50 px-1.5 py-0.5 font-mono text-[10px] text-red-700">
                              ✎ {shortId(x.split(".").pop() ?? x)}
                            </span>
                          ))}
                          {w.externals.map((x) => (
                            <span key={x} className="rounded border border-orange-200 bg-orange-50 px-1.5 py-0.5 font-mono text-[10px] text-orange-700">
                              ⇢ {x.split(".").pop()}
                            </span>
                          ))}
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${w.fullyTraced ? "bg-emerald-100 text-emerald-700 border-emerald-200" : "bg-slate-100 text-slate-500 border-slate-200"}`}>
                            {w.fullyTraced ? "✓ Fully traced" : "read-only / partial"}
                          </span>
                        </div>
                      </button>
                      {open && (
                        <div className="border-t border-slate-100 bg-slate-50 px-4 py-3 text-xs">
                          <p className="mb-2 font-mono text-[10px] text-slate-500">
                            entry {w.entryPoint} · {w.entryKind} · {location(w.file, w.line)}
                          </p>
                          <ol className="space-y-1">
                            {w.steps.map((s, i) => (
                              <li key={i} className="flex flex-wrap items-center gap-2 font-mono text-[10px]" style={{ paddingLeft: (s.depth - 1) * 14 }}>
                                <span className={`rounded border px-1.5 py-0.5 font-bold ${EDGE_CLS[s.kind] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
                                  {s.kind}{s.operation ? ` · ${s.operation}` : ""}
                                </span>
                                <span className="text-slate-500">{s.from.split(".").slice(-2).join(".")}</span>
                                <span className="text-slate-300">→</span>
                                <span className="text-slate-800">{s.to.split(".").slice(-2).join(".")}</span>
                                <span className="text-slate-400">{location(s.file, s.line)}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* ── WORKFLOW CHAINS ── */}
            {tab === "chains" && (
              <div className="space-y-2">
                {filteredChains.length === 0 && (
                  <p className="text-sm text-slate-500">
                    No workflow chains. Chains require semantic_ir, requirements, backlog, and tests.
                  </p>
                )}
                {filteredChains.map((chain: WorkflowChain) => {
                  const open = openChain === chain.id;
                  return (
                    <div key={chain.id} className="rounded-lg border border-slate-200 bg-white overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setOpenChain(open ? null : chain.id)}
                        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50 transition"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="text-[10px] text-slate-400 shrink-0">{open ? "▼" : "▶"}</span>
                          <span className="font-mono text-xs font-bold text-purple-700 shrink-0">{chain.sirRule}</span>
                          <span className="text-xs text-slate-700 truncate">{chain.sirStatement}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0 ml-3">
                          <span className="font-mono text-[10px] text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded">
                            {chain.requirement}
                          </span>
                          <span className="font-mono text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                            {chain.backlogItem}
                          </span>
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${chain.traceComplete ? "bg-emerald-100 text-emerald-700 border-emerald-200" : "bg-amber-100 text-amber-700 border-amber-200"}`}>
                            {chain.traceComplete ? "✓ Traced" : "⚠ No Test"}
                          </span>
                        </div>
                      </button>
                      {open && (
                        <div className="border-t border-slate-100 bg-slate-50 px-4 py-4 space-y-3 text-xs">
                          <div className="grid sm:grid-cols-2 gap-3">
                            {[
                              ["AST Node",        chain.astNode,               "font-mono text-purple-700"],
                              ["Legacy Evidence", chain.legacyEvidence,        "font-mono text-blue-700"],
                              ["Requirement",     chain.requirementStatement,  "text-slate-700"],
                              ["Backlog Item",    chain.backlogTitle,          "text-slate-700"],
                              ["Wave",            `Wave ${chain.wave}`,        "font-mono font-bold text-slate-800"],
                              ["Trust Boundary",  chain.trustBoundary,         "text-slate-600"],
                            ].map(([label, val, cls]) => (
                              <div key={label as string}>
                                <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-0.5">{label}</span>
                                <span className={cls as string}>{val || "—"}</span>
                              </div>
                            ))}
                          </div>
                          {chain.testCases.length > 0 && (
                            <div>
                              <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">Test Cases</span>
                              <div className="flex flex-wrap gap-1.5">
                                {chain.testCases.map((tc) => (
                                  <span key={tc} className="font-mono text-[10px] bg-emerald-50 border border-emerald-200 text-emerald-700 px-2 py-0.5 rounded">
                                    {tc}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* ── SHARED KERNELS ── */}
            {tab === "kernels" && (
              <div className="space-y-3">
                {graph.sharedKernels.length === 0 && (
                  <p className="text-sm text-slate-500">
                    No shared kernels detected — all nodes are owned by a single capability.
                  </p>
                )}
                {graph.sharedKernels.map((sk: SharedKernel) => (
                  <div key={sk.id} className="rounded-xl border border-amber-200 bg-amber-50/40 p-4 space-y-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase ${sk.nodeType === "program" ? "bg-purple-100 text-purple-700 border-purple-200" : "bg-emerald-100 text-emerald-700 border-emerald-200"}`}>
                          {sk.nodeType}
                        </span>
                        <span className="font-mono text-sm font-bold text-slate-900">{sk.nodeId}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500">Coupling:</span>
                        <span className="font-mono font-bold text-amber-700">{sk.couplingDegree}</span>
                        {riskBadge(sk.migrationRisk)}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {sk.consumingCapabilities.map((cap) => (
                        <span key={cap} className="rounded bg-white border border-slate-200 px-2 py-0.5 font-mono text-xs text-slate-700">
                          {cap}
                        </span>
                      ))}
                    </div>
                    <p className="text-xs text-amber-900 bg-white/70 rounded px-2.5 py-1.5 border border-amber-200">
                      <strong>Recommendation:</strong> {sk.recommendation}
                    </p>
                  </div>
                ))}
              </div>
            )}

          </div>
        </>
      )}
    </section>
  );
}
