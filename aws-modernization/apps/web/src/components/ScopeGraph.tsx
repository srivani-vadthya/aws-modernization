import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, Controls, Position, useReactFlow, type Edge, type Node } from "reactflow";
import "reactflow/dist/style.css";
import { api, type AppliedGraph, type AppliedGraphNode } from "../api";

// ─── tree model ──────────────────────────────────────────────────────────────
// The scoped module is the root. Its children are groups (classes, entities, views, …), whose children are the
// individual graph nodes. Nodes that belong to other modules but touch this one hang under "Other modules".
// Nothing is drawn until the user expands it, so the picture stays readable at any module size.

type TNode = {
  id: string;
  label: string;
  sub?: string;
  type: string;
  children: TNode[];
  ref?: AppliedGraphNode;
};

const GROUP_LABEL: Record<string, string> = {
  program: "Classes & services",
  entity: "Entities / tables",
  view: "Views",
  frontend: "Frontend controllers",
  config: "Configuration",
  external: "External systems",
  project: "Projects",
};
const GROUP_ORDER = ["program", "entity", "view", "frontend", "external", "config", "project"];

const PALETTE: Record<string, { bg: string; text: string; border: string }> = {
  capability: { bg: "#eef2ff", text: "#3730a3", border: "#6366f1" },
  program: { bg: "#eff6ff", text: "#1d4ed8", border: "#93c5fd" },
  entity: { bg: "#f0fdf4", text: "#15803d", border: "#86efac" },
  view: { bg: "#fdf2f8", text: "#be185d", border: "#f9a8d4" },
  frontend: { bg: "#fdf2f8", text: "#9d174d", border: "#f472b6" },
  external: { bg: "#fff7ed", text: "#c2410c", border: "#fdba74" },
  config: { bg: "#f8fafc", text: "#475569", border: "#cbd5e1" },
  other: { bg: "#f5f3ff", text: "#6d28d9", border: "#c4b5fd" },
  more: { bg: "#ffffff", text: "#475569", border: "#94a3b8" },
};

function nodeSub(n: AppliedGraphNode): string | undefined {
  return (n.semanticRole ?? n.role ?? "").replace(/-/g, " ") || undefined;
}

export function buildTree(graph: AppliedGraph, capId: string, scopeName?: string): TNode | null {
  const capNode = graph.nodes.find((n) => n.type === "capability" && n.capability === capId);
  const members = graph.nodes.filter((n) => n.capability === capId && n.type !== "capability");
  if (!capNode && members.length === 0) return null;

  const inScope = new Set(members.map((n) => n.id));
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const capLabel = new Map(graph.nodes.filter((n) => n.type === "capability").map((n) => [n.capability, n.label]));

  // direct neighbours that live outside the module
  const outside = new Set<string>();
  for (const e of graph.edges) {
    if (e.kind === "CONTAINS") continue;
    if (inScope.has(e.source) && !inScope.has(e.target)) outside.add(e.target);
    else if (inScope.has(e.target) && !inScope.has(e.source)) outside.add(e.source);
  }
  const neighbours = [...outside].map((id) => byId.get(id)).filter((n): n is AppliedGraphNode => !!n && n.type !== "capability");

  const leaf = (n: AppliedGraphNode): TNode => ({ id: n.id, label: n.label.replace("\n", " · "), sub: nodeSub(n), type: n.type, children: [], ref: n });
  const sortLeaves = (xs: TNode[]) => xs.sort((a, b) => a.label.localeCompare(b.label));

  const groups = new Map<string, TNode[]>();
  for (const n of members) groups.set(n.type, [...(groups.get(n.type) ?? []), leaf(n)]);
  // external systems reached by neighbours are listed with the module's own external systems
  const otherModules = new Map<string, TNode[]>();
  for (const n of neighbours) {
    if (n.type === "external") groups.set("external", [...(groups.get("external") ?? []), leaf(n)]);
    else otherModules.set(n.capability || "other", [...(otherModules.get(n.capability || "other") ?? []), leaf(n)]);
  }

  const children: TNode[] = [];
  const types = [...groups.keys()].sort((a, b) => (GROUP_ORDER.indexOf(a) + 1 || 99) - (GROUP_ORDER.indexOf(b) + 1 || 99));
  for (const t of types) {
    const kids = sortLeaves(groups.get(t)!);
    children.push({ id: `g:${t}`, label: GROUP_LABEL[t] ?? t, sub: `${kids.length}`, type: t, children: kids });
  }
  if (otherModules.size) {
    const subs = [...otherModules.entries()]
      .map(([cap, kids]): TNode => ({
        id: `g:other:${cap}`, label: capLabel.get(cap) ?? cap, sub: `${kids.length}`, type: "other", children: sortLeaves(kids),
      }))
      .sort((a, b) => b.children.length - a.children.length || a.label.localeCompare(b.label));
    children.push({
      id: "g:other", label: "Connected modules",
      sub: `${subs.length} modules · ${subs.reduce((s, m) => s + m.children.length, 0)} nodes`,
      type: "other", children: subs,
    });
  }
  return { id: capNode?.id ?? `cap:${capId}`, label: scopeName ?? capNode?.label ?? capId, sub: `${members.length} nodes`, type: "capability", children, ref: capNode };
}

// ─── layout ──────────────────────────────────────────────────────────────────

const COL_W = 300;
const ROW_H = 62;
const NODE_W = 230;

const PAGE = 10;

/** The children of an open node that are drawn: long lists of leaves are shown a page at a time. */
function visibleKids(t: TNode, shown: Record<string, number>): { kids: TNode[]; hidden: number } {
  const limit = shown[t.id] ?? PAGE;
  const leaves = t.children.every((c) => c.children.length === 0);
  if (!leaves || t.children.length <= limit) return { kids: t.children, hidden: 0 };
  return { kids: t.children.slice(0, limit), hidden: t.children.length - limit };
}

function layout(root: TNode, expanded: Set<string>, shown: Record<string, number>) {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let row = 0;

  const place = (t: TNode, depth: number, parent?: TNode): number => {
    const open = expanded.has(t.id) && t.children.length > 0;
    let y: number;
    if (open) {
      const { kids, hidden } = visibleKids(t, shown);
      const ys = kids.map((c) => place(c, depth + 1, t));
      if (hidden > 0) ys.push(place({ id: `more:${t.id}`, label: `+ ${hidden} more`, sub: "click to show more", type: "more", children: [] }, depth + 1, t));
      y = (ys[0] + ys[ys.length - 1]) / 2;
    } else {
      y = row++ * ROW_H;
    }
    const pal = PALETTE[t.type] ?? PALETTE.config;
    const expandable = t.children.length > 0;
    nodes.push({
      id: t.id,
      position: { x: depth * COL_W, y },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      draggable: false,
      data: {
        label: (
          <div style={{ lineHeight: 1.25, textAlign: "left" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: 12 }}>
              {expandable && <span aria-hidden style={{ fontSize: 10 }}>{open ? "▾" : "▸"}</span>}
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.label}</span>
            </div>
            {(t.sub || expandable) && (
              <div style={{ marginTop: 2, fontSize: 10, opacity: 0.75, textTransform: expandable ? undefined : "uppercase" }}>
                {expandable && !open ? `${t.children.length} ${t.children.length === 1 ? "child" : "children"} · click to expand` : t.sub}
              </div>
            )}
          </div>
        ),
      },
      style: {
        width: NODE_W,
        padding: "8px 10px",
        borderRadius: depth === 0 ? 12 : 8,
        background: pal.bg,
        color: pal.text,
        border: `${depth === 0 ? 2 : 1.5}px solid ${pal.border}`,
        cursor: "pointer",
        boxShadow: depth === 0 ? "0 2px 8px rgba(99,102,241,0.2)" : "0 1px 3px rgba(0,0,0,0.06)",
      },
    });
    if (parent) {
      edges.push({ id: `${parent.id}>${t.id}`, source: parent.id, target: t.id, type: "smoothstep", style: { stroke: "#94a3b8", strokeWidth: 1.5 } });
    }
    return y;
  };
  place(root, 0);
  return { nodes, edges };
}

/** Re-frames the canvas after each click: on the clicked node and its children (readable zoom), or on everything. */
function Fitter({ signature, focus }: { signature: string; focus: string[] }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const t = setTimeout(
      () => fitView({ padding: 0.25, duration: 300, minZoom: 0.7, maxZoom: 1.1, ...(focus.length ? { nodes: focus.map((id) => ({ id })) } : {}) }),
      40,
    );
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, fitView]);
  return null;
}

// ─── component ───────────────────────────────────────────────────────────────

export function ScopeGraph({ engagementId, capabilityId, scopeName }: { engagementId: string; capabilityId: string; scopeName?: string }) {
  const [graph, setGraph] = useState<AppliedGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<AppliedGraphNode | null>(null);
  const [shown, setShown] = useState<Record<string, number>>({});
  const [focus, setFocus] = useState<string[]>([]);

  useEffect(() => {
    let live = true;
    setGraph(null);
    setError(null);
    api.knowledgeGraph(engagementId)
      .then((g) => live && setGraph(g))
      .catch((e: Error) => live && setError(e.message));
    return () => { live = false; };
  }, [engagementId]);

  const tree = useMemo(() => (graph ? buildTree(graph, capabilityId, scopeName) : null), [graph, capabilityId, scopeName]);
  useEffect(() => { setExpanded(new Set()); setSelected(null); setShown({}); setFocus([]); }, [capabilityId, tree]);

  const byId = useMemo(() => {
    const m = new Map<string, TNode>();
    const walk = (t: TNode) => { m.set(t.id, t); t.children.forEach(walk); };
    if (tree) walk(tree);
    return m;
  }, [tree]);

  const { nodes, edges } = useMemo(() => (tree ? layout(tree, expanded, shown) : { nodes: [], edges: [] }), [tree, expanded, shown]);

  function toggle(id: string) {
    if (id.startsWith("more:")) {
      const gid = id.slice(5);
      const g = byId.get(gid);
      if (!g) return;
      const next = (shown[gid] ?? PAGE) + PAGE;
      setShown({ ...shown, [gid]: next });
      setFocus([gid, ...g.children.slice(0, next).map((c) => c.id)]);
      return;
    }
    const t = byId.get(id);
    if (!t) return;
    if (t.children.length === 0) { setSelected(t.ref ?? null); return; }
    if (expanded.has(id)) {
      // collapsing a parent also closes everything beneath it
      const next = new Set(expanded);
      const drop = (x: TNode) => { next.delete(x.id); x.children.forEach(drop); };
      drop(t);
      setExpanded(next);
      setFocus([]);
    } else {
      setExpanded(new Set(expanded).add(id));
      setFocus([id, ...visibleKids(t, shown).kids.map((c) => c.id)]);
    }
  }

  const relations = useMemo(() => {
    if (!graph || !selected) return [];
    const label = new Map(graph.nodes.map((n) => [n.id, n.label.replace("\n", " · ")]));
    return graph.edges
      .filter((e) => e.kind !== "CONTAINS" && (e.source === selected.id || e.target === selected.id))
      .map((e) => ({ id: e.id, kind: e.kind, out: e.source === selected.id, other: label.get(e.source === selected.id ? e.target : e.source) ?? "", at: e.file ? `${e.file}${e.line ? `#L${e.line}` : ""}` : "" }));
  }, [graph, selected]);

  const total = tree ? byId.size - 1 : 0;

  return (
    <section className="rounded-xl border border-indigo-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left"
      >
        <span className="flex items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-[10px] font-bold text-white">AKG</span>
          <span>
            <span className="block text-xs font-bold uppercase tracking-wider text-slate-900">
              Knowledge graph{scopeName ? ` · ${scopeName}` : ""}
            </span>
            <span className="block text-[11px] text-slate-500">
              Click the module to reveal its parts, then click a group to see its members
            </span>
          </span>
        </span>
        <span className="flex items-center gap-2 font-mono text-[10px] text-slate-500">
          {tree && <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5">{total} items · {nodes.length} visible</span>}
          <span aria-hidden>{open ? "▲" : "▼"}</span>
        </span>
      </button>
      {open && (
        <div className="border-t border-indigo-100 p-3">
          {error && <p role="alert" className="p-3 text-xs text-red-700">Could not load the knowledge graph: {error}</p>}
          {!error && !graph && <p className="p-3 text-xs text-slate-500">Loading the knowledge graph…</p>}
          {graph && !tree && <p className="p-3 text-xs text-slate-500">The knowledge graph has no nodes for this module.</p>}
          {tree && (
            <div className="grid gap-3 lg:grid-cols-[1fr_280px]">
              <div className="flex items-center gap-2 lg:col-span-2">
                <button
                  type="button"
                  onClick={() => { setExpanded(new Set()); setSelected(null); setShown({}); setFocus([]); }}
                  className="rounded border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Collapse all
                </button>
                <span className="text-[11px] text-slate-500">Click ▸ nodes to expand or collapse. Click a leaf for its relationships.</span>
              </div>
              <div className="h-[520px] overflow-hidden rounded-xl border border-slate-200 bg-slate-50/40">
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodeClick={(_, n) => toggle(n.id)}
                  fitView
                  minZoom={0.3}
                  maxZoom={1.5}
                  nodesConnectable={false}
                  nodesDraggable={false}
                  proOptions={{ hideAttribution: true }}
                >
                  <Background color="#e2e8f0" gap={20} />
                  <Controls showInteractive={false} position="top-right" />
                  <Fitter signature={`${nodes.length}:${[...expanded].join("|")}`} focus={focus} />
                </ReactFlow>
              </div>
              <aside className="h-[520px] overflow-auto rounded-xl border border-slate-200 bg-white p-3 text-xs">
                {!selected ? (
                  <p className="text-slate-500">Select a leaf node (a class, entity, view…) to see its details and relationships here.</p>
                ) : (
                  <div className="space-y-2">
                    <div>
                      <p className="font-bold text-slate-900">{selected.label.replace("\n", " · ")}</p>
                      <p className="font-mono text-[10px] text-slate-500">{selected.type}{nodeSub(selected) ? ` · ${nodeSub(selected)}` : ""}</p>
                      {selected.file && <p className="mt-1 break-all font-mono text-[10px] text-slate-600">{selected.file}{selected.line ? `#L${selected.line}` : ""}</p>}
                    </div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Relationships ({relations.length})</p>
                    {relations.length === 0 && <p className="text-slate-500">No relationships other than containment.</p>}
                    <ul className="space-y-1">
                      {relations.map((r) => (
                        <li key={r.id} className="rounded border border-slate-100 bg-slate-50 px-2 py-1">
                          <span className="font-mono text-[10px] font-semibold text-indigo-700">{r.out ? "→" : "←"} {r.kind}</span>
                          <span className="ml-1 text-slate-800">{r.other}</span>
                          {r.at && <span className="block break-all font-mono text-[9px] text-slate-400">{r.at}</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </aside>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
