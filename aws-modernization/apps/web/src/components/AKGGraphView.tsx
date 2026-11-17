import { useMemo } from "react";
import ReactFlow, { Background, Controls, MiniMap, Edge, Node } from "reactflow";
import "reactflow/dist/style.css";
import type { AppliedGraph } from "../api";

// ─── visual palette ─────────────────────────────────────────────────────────

const TYPE_PALETTE: Record<string, { bg: string; text: string; border: string }> = {
  capability: { bg: "#eef2ff", text: "#3730a3", border: "#818cf8" },
  program:    { bg: "#eff6ff", text: "#1d4ed8", border: "#93c5fd" },
  table:      { bg: "#f0fdf4", text: "#15803d", border: "#86efac" },
  event:      { bg: "#f0fdfa", text: "#0f766e", border: "#5eead4" },
};

const ROLE_BADGE: Record<string, string> = {
  "orchestrator":        "#7c3aed",
  "data-access-gateway": "#1d4ed8",
  "screen-boundary":     "#be185d",
  "batch-entry-point":   "#b45309",
  "event-publisher":     "#0f766e",
  "business-logic":      "#475569",
};

const EDGE_COLOR: Record<string, string> = {
  CALLS:        "#7c3aed",
  READS:        "#1d4ed8",
  WRITES:       "#dc2626",
  MAPS_TO:      "#be185d",
  TRIGGERED_BY: "#b45309",
  OWNS_DATA:    "#15803d",
  EMITS_EVENT:  "#0f766e",
  CONTAINS:     "#94a3b8",
  FIELD_LINEAGE:"#64748b",
};

// ─── component ───────────────────────────────────────────────────────────────

export function AKGGraphView({
  graph,
  highlightCapability,
}: {
  graph: AppliedGraph;
  highlightCapability?: string | null;
}) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = graph.nodes.map((n) => {
      const palette = TYPE_PALETTE[n.type] ?? { bg: "#f8fafc", text: "#334155", border: "#cbd5e1" };
      const isHighlighted = highlightCapability && n.capability === highlightCapability;
      const isCapability = n.type === "capability";
      const dimmed = highlightCapability && !isHighlighted && !isCapability;
      const roleColor = ROLE_BADGE[n.semanticRole ?? ""] ?? "#475569";

      return {
        id: n.id,
        position: n.position,
        data: {
          label: (
            <div style={{ lineHeight: 1.3 }}>
              <div style={{ fontWeight: 700, fontSize: 11 }}>
                {n.label.replace("\n", " · ")}
              </div>
              {n.semanticRole && (
                <div
                  style={{
                    marginTop: 3,
                    fontSize: 9,
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                    color: roleColor,
                  }}
                >
                  {n.semanticRole.replace(/-/g, " ")}
                </div>
              )}
              {n.sirRules && n.sirRules.length > 0 && (
                <div style={{ marginTop: 2, fontSize: 9, color: "#7c3aed" }}>
                  {n.sirRules.slice(0, 2).join(", ")}
                  {n.sirRules.length > 2 ? ` +${n.sirRules.length - 2}` : ""}
                </div>
              )}
            </div>
          ),
        },
        style: {
          background: isHighlighted ? "#dbeafe" : palette.bg,
          color: palette.text,
          border: `${isCapability ? 2 : 1.5}px solid ${isHighlighted ? "#2563eb" : palette.border}`,
          borderRadius: isCapability ? 12 : 8,
          fontSize: 11,
          width: isCapability ? 180 : 155,
          padding: "8px 10px",
          boxShadow: isHighlighted
            ? "0 4px 12px rgba(37,99,235,0.25)"
            : isCapability
            ? "0 2px 8px rgba(99,102,241,0.15)"
            : "0 1px 3px rgba(0,0,0,0.06)",
          opacity: dimmed ? 0.3 : 1,
          transition: "opacity 0.2s",
        },
      };
    });

    const edges: Edge[] = graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.kind,
      animated: e.kind === "CALLS" || e.kind === "EMITS_EVENT",
      style: {
        stroke: EDGE_COLOR[e.kind] ?? "#94a3b8",
        strokeWidth: e.kind === "OWNS_DATA" || e.kind === "CONTAINS" ? 1 : 1.5,
        strokeDasharray: e.kind === "CONTAINS" ? "4 3" : undefined,
      },
      labelStyle: {
        fill: EDGE_COLOR[e.kind] ?? "#64748b",
        fontSize: 9,
        fontWeight: 600,
      },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.85 },
      labelBgPadding: [3, 4] as [number, number],
      labelBgBorderRadius: 3,
    }));

    return { nodes, edges };
  }, [graph, highlightCapability]);

  return (
    <div className="h-[560px] overflow-hidden rounded-xl border border-indigo-200 bg-white shadow-sm">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.25}
        maxZoom={2}
        nodesConnectable={false}
        nodesDraggable
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e2e8f0" gap={20} />
        <Controls />
        <MiniMap
          nodeColor={(n) => {
            const type = (n.style?.background as string) ?? "#f8fafc";
            return type;
          }}
          maskColor="rgba(248,250,252,0.7)"
          style={{ border: "1px solid #e2e8f0", borderRadius: 8 }}
        />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute bottom-10 left-3 flex flex-wrap gap-1.5 rounded-lg border border-slate-200 bg-white/90 px-3 py-2 shadow-sm backdrop-blur-sm text-[10px]">
        {Object.entries(EDGE_COLOR)
          .filter(([k]) => ["CALLS", "READS", "WRITES", "OWNS_DATA", "EMITS_EVENT", "TRIGGERED_BY"].includes(k))
          .map(([kind, color]) => (
            <span key={kind} className="flex items-center gap-1 font-mono font-semibold" style={{ color }}>
              <span style={{ display: "inline-block", width: 16, height: 2, background: color, borderRadius: 1 }} />
              {kind}
            </span>
          ))}
      </div>
    </div>
  );
}
