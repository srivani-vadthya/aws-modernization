import { useMemo } from "react";
import ReactFlow, { Background, Controls, Edge, Node } from "reactflow";
import "reactflow/dist/style.css";
import type { Seed } from "../api";

const COLORS: Record<string, { bg: string; text: string; border: string }> = {
  program: { bg: "#eff6ff", text: "#1d4ed8", border: "#93c5fd" },
  table: { bg: "#f0fdf4", text: "#15803d", border: "#86efac" },
  job: { bg: "#fefce8", text: "#a16207", border: "#fde047" },
  screen: { bg: "#fdf2f8", text: "#be185d", border: "#f472b6" },
  capability: { bg: "#fff7ed", text: "#c2410c", border: "#fdba74" },
};

export function GraphView({ seed, highlight }: { seed: Seed; highlight?: string | null }) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = seed.graph.nodes.map((n) => {
      const palette = COLORS[n.type] || { bg: "#ffffff", text: "#334155", border: "#cbd5e1" };
      const isHighlighted = highlight && n.capability === highlight;

      return {
        id: n.id,
        position: n.position,
        data: { label: n.label.replace("\n", " · ") },
        style: {
          background: isHighlighted ? "#dbeafe" : palette.bg,
          color: palette.text,
          border: `1.5px solid ${isHighlighted ? "#2563eb" : palette.border}`,
          borderRadius: 8,
          fontSize: 11,
          fontWeight: 600,
          width: n.type === "capability" ? 170 : 145,
          padding: "8px 10px",
          boxShadow: isHighlighted ? "0 4px 6px -1px rgba(37, 99, 235, 0.2)" : "0 1px 3px rgba(0, 0, 0, 0.05)",
          opacity: highlight && n.capability !== highlight && n.type !== "capability" ? 0.35 : 1,
        },
      };
    });

    const edges: Edge[] = seed.graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.kind,
      animated: e.kind === "CALLS",
      style: { stroke: "#94a3b8", strokeWidth: 1.5 },
      labelStyle: { fill: "#64748b", fontSize: 10, fontWeight: 500 },
    }));
    return { nodes, edges };
  }, [seed, highlight]);

  return (
    <div className="h-[500px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        minZoom={0.4}
        nodesConnectable={false}
        nodesDraggable
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e2e8f0" gap={18} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
