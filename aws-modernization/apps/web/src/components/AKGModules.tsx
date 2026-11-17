import { useMemo } from "react";
import type { Engagement, AppliedGraph, AppliedGraphNode } from "../api";

// ─── colour maps ────────────────────────────────────────────────────────────

const ROLE_ICON: Record<string, string> = {
  "orchestrator":        "🎯",
  "data-access-gateway": "🗄️",
  "screen-boundary":     "🖥️",
  "batch-entry-point":   "⚙️",
  "event-publisher":     "📡",
  "business-logic":      "💼",
  "domain-event":        "⚡",
};

const RISK_CLS: Record<string, string> = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high:     "bg-amber-100 text-amber-700 border-amber-200",
  medium:   "bg-yellow-50 text-yellow-700 border-yellow-200",
  low:      "bg-emerald-50 text-emerald-700 border-emerald-200",
};

// ─── types ──────────────────────────────────────────────────────────────────

type AKGModule = {
  capabilityId: string;
  capabilityLabel: string;
  programs: AppliedGraphNode[];
  tables: AppliedGraphNode[];
  events: AppliedGraphNode[];
  edgeCounts: Record<string, number>;
  sharedKernelIds: string[];
  dominantRole: string;
  migrationRisk: string;
};

// ─── derivation ─────────────────────────────────────────────────────────────

function deriveModules(graph: AppliedGraph): AKGModule[] {
  const sharedKernelNodeIds = new Set(graph.sharedKernels.map((sk) => sk.nodeId));

  const capNodes = graph.nodes.filter(
    (n) => n.type === "capability" && n.capability !== "external" && n.id !== "CAP-external",
  );

  return capNodes
    .map((cap) => {
      const capId = cap.capability || cap.id.replace("CAP-", "");
      const members = graph.nodes.filter(
        (n) => n.capability === capId && n.type !== "capability",
      );

      const programs = members.filter((n) => n.type === "program");
      const tables   = members.filter((n) => n.type === "table");
      const events   = members.filter((n) => n.type === "event");

      // Edge kind counts for nodes in this capability
      const memberIds = new Set(members.map((n) => n.id));
      const edgeCounts: Record<string, number> = {};
      for (const edge of graph.edges) {
        if (memberIds.has(edge.source) || memberIds.has(edge.target)) {
          edgeCounts[edge.kind] = (edgeCounts[edge.kind] ?? 0) + 1;
        }
      }

      // Dominant semantic role by frequency
      const roleCounts: Record<string, number> = {};
      for (const n of members) {
        if (n.semanticRole) roleCounts[n.semanticRole] = (roleCounts[n.semanticRole] ?? 0) + 1;
      }
      const dominantRole =
        Object.entries(roleCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "business-logic";

      // Shared kernels belonging to this capability
      const sharedKernelIds = members
        .filter((n) => sharedKernelNodeIds.has(n.id))
        .map((n) => n.id);

      // Migration risk — escalate based on shared kernel severity
      const kernelRisks = graph.sharedKernels
        .filter((sk) => sharedKernelIds.includes(sk.nodeId))
        .map((sk) => sk.migrationRisk);
      const migrationRisk =
        kernelRisks.includes("critical") ? "critical" :
        kernelRisks.includes("high")     ? "high" :
        sharedKernelIds.length > 0       ? "medium" : "low";

      return {
        capabilityId: capId,
        capabilityLabel: cap.label,
        programs,
        tables,
        events,
        edgeCounts,
        sharedKernelIds,
        dominantRole,
        migrationRisk,
      };
    })
    .filter((m) => m.programs.length + m.tables.length > 0);
}

// ─── component ──────────────────────────────────────────────────────────────

export function AKGModules({
  e,
  onSelectCapability,
}: {
  e: Engagement;
  onSelectCapability: (capId: string) => void;
}) {
  const graph = e.seed?.applied_graph as AppliedGraph | undefined;

  const modules = useMemo(
    () => (graph ? deriveModules(graph) : []),
    [graph],
  );

  if (!graph || modules.length === 0) return null;

  const activeCapId = e.scope?.capabilityId;

  return (
    <div className="rounded-xl border border-indigo-200 bg-gradient-to-b from-indigo-50/60 to-white p-5 space-y-4">

      {/* Header */}
      <div className="flex items-center gap-3 border-b border-indigo-100 pb-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-white text-[11px] font-bold shadow-sm">
          AKG
        </span>
        <div>
          <h4 className="text-sm font-bold text-slate-900">
            AKG-Derived Business Modules
          </h4>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Modules identified from graph roles, relationships, and shared-data coupling
          </p>
        </div>
        <span className="ml-auto rounded-full bg-indigo-100 border border-indigo-200 px-2.5 py-0.5 text-[11px] font-bold text-indigo-700">
          {modules.length} modules
        </span>
      </div>

      {/* Module cards */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {modules.map((mod) => {
          const isActive = activeCapId === mod.capabilityId;
          return (
            <button
              key={mod.capabilityId}
              type="button"
              onClick={() => onSelectCapability(mod.capabilityId)}
              className={`rounded-xl border-2 p-4 text-left transition cursor-pointer ${
                isActive
                  ? "border-indigo-500 bg-indigo-50 shadow-md ring-2 ring-indigo-400/20"
                  : "border-slate-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/40"
              }`}
            >
              {/* Title row */}
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-base shrink-0">{ROLE_ICON[mod.dominantRole] ?? "💼"}</span>
                  <span className={`text-sm font-bold truncate ${isActive ? "text-indigo-900" : "text-slate-900"}`}>
                    {mod.capabilityLabel}
                  </span>
                </div>
                <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase shrink-0 ${RISK_CLS[mod.migrationRisk] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
                  {mod.migrationRisk}
                </span>
              </div>

              {/* Dominant role pill */}
              <span className="inline-block rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 mb-2">
                {mod.dominantRole.replace(/-/g, " ")}
              </span>

              {/* Asset counts */}
              <div className="flex flex-wrap gap-1.5 text-[10px] font-mono mb-2">
                {mod.programs.length > 0 && (
                  <span className="rounded bg-blue-50 border border-blue-200 px-1.5 py-0.5 text-blue-700">
                    {mod.programs.length} programs
                  </span>
                )}
                {mod.tables.length > 0 && (
                  <span className="rounded bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-emerald-700">
                    {mod.tables.length} tables
                  </span>
                )}
                {mod.events.length > 0 && (
                  <span className="rounded bg-teal-50 border border-teal-200 px-1.5 py-0.5 text-teal-700">
                    {mod.events.length} events
                  </span>
                )}
                {mod.sharedKernelIds.length > 0 && (
                  <span className="rounded bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-amber-700">
                    ⇄ {mod.sharedKernelIds.length} shared
                  </span>
                )}
              </div>

              {/* Top edge kinds */}
              {Object.keys(mod.edgeCounts).length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {Object.entries(mod.edgeCounts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 4)
                    .map(([kind, count]) => (
                      <span key={kind} className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-mono text-slate-600">
                        {kind}·{count}
                      </span>
                    ))}
                </div>
              )}

              {isActive && (
                <p className="mt-2 text-[10px] font-bold text-indigo-700 text-right">✓ Active Scope</p>
              )}
            </button>
          );
        })}
      </div>

      {/* Shared kernel warning banner */}
      {graph.sharedKernels.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-2.5 text-xs text-amber-800 flex items-center gap-2">
          <span className="text-base shrink-0">⇄</span>
          <span>
            <strong>{graph.sharedKernels.length} shared kernel{graph.sharedKernels.length !== 1 ? "s" : ""}</strong> detected across module boundaries.
            Selecting a module with shared kernels requires an Anti-Corruption Layer or CDC dual-write strategy.
          </span>
        </div>
      )}
    </div>
  );
}
