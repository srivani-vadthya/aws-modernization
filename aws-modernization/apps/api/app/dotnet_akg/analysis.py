"""Derived layers: capabilities, lineage, workflows, shared kernels.

All of these are computed from the evidence-backed edges; none introduces a
relationship that the edge layer does not already hold.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .csharp import BType, SymbolTable, TypeSym
from .extract import EdgeSink, Fact, MapDecl, _unwrap_collection

PLATFORM = "platform"
WRITE_WEIGHT, READ_WEIGHT, MAP_WEIGHT, GENERIC_BASE_WEIGHT = 3, 1, 2, 1


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "shared"


# ---------------------------------------------------------------------------
# 1. Aggregates from the EF model
# ---------------------------------------------------------------------------

def aggregates(entities: dict[str, TypeSym], edges: list[dict],
               workflows: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """entity fqn -> aggregate-root fqn (or PLATFORM for shared reference data), plus a reason per entity.

    EF maps most 1:N relationships in both directions, so structure alone cannot tell an
    owned child (Invoice -> Particulars) from a back-reference (InsuranceProvider -> Forms).
    Membership is therefore behavioural: E belongs to P's aggregate when E and P form a
    1:N pair and every workflow that writes E also writes P. Entities no workflow writes
    are reference data.
    """
    out_refs: dict[str, dict[str, str]] = defaultdict(dict)   # src -> tgt -> cardinality
    explicit_owned: set[tuple[str, str]] = set()             # (parent, child) from HasMany(..).WithRequired(..)
    for e in edges:
        if e["kind"] == "REFERENCES" and e["source"] in entities and e["target"] in entities:
            card = e.get("cardinality", "one")
            prev = out_refs[e["source"]].get(e["target"])
            if prev != "many":
                out_refs[e["source"]][e["target"]] = "many" if card in {"many", "one-to-many"} else "one"
            if card == "one-to-many":
                explicit_owned.add((e["source"], e["target"]))
    incoming: dict[str, set[str]] = defaultdict(set)
    for s, tg in out_refs.items():
        for t in tg:
            incoming[t].add(s)
    # Hub entities (audit logs) reference most of the model; they never own anything.
    hubs = {f for f in entities if len(set(out_refs.get(f, {})) - {f}) >= max(5, len(entities) // 2)}

    writes_by_wf = [set(w["writes"]) for w in workflows if w["writes"]]
    written = set().union(*writes_by_wf) if writes_by_wf else set()

    reason: dict[str, str] = {}
    owner: dict[str, str] = {}
    for f in entities:
        if f in hubs:
            continue
        parents = [p for p in entities if p != f and p not in hubs
                   and out_refs.get(p, {}).get(f) == "many" and out_refs.get(f, {}).get(p) == "one"]
        if len(parents) != 1:
            continue
        p = parents[0]
        wf = [w for w in writes_by_wf if f in w]
        together = sum(1 for w in wf if p in w)
        # Majority, not all: removing a single child row (DeleteAttachment) is normal for an owned child.
        if wf and together * 2 >= len(wf) and together > 0:
            owner[f] = p
            reason[f] = f"written together with {p.rsplit('.', 1)[-1]} in {together}/{len(wf)} workflows"
        elif not wf and (p, f) in explicit_owned:
            owner[f] = p
            reason[f] = f"EF HasMany/WithRequired from {p.rsplit('.', 1)[-1]}"
    reference = {f for f in entities if f not in written and f not in owner and f not in hubs and incoming.get(f)}
    roots = {f for f in entities if f not in owner and f not in reference}

    def root_of(f: str, depth: int = 0) -> str | None:
        if f in roots:
            return f
        if depth > 10 or f not in owner:
            return None
        return root_of(owner[f], depth + 1)

    result: dict[str, str] = {}
    for f in entities:
        r = root_of(f)
        if r is not None:
            result[f] = r
            reason.setdefault(f, "aggregate root" if r == f else f"part of {r.rsplit('.', 1)[-1]}")
    for f in reference:
        refs = {result.get(p) for p in incoming.get(f, set()) if p not in hubs} - {None}
        result[f] = refs.pop() if len(refs) == 1 else PLATFORM
        reason[f] = ("reference data used only by " + result[f].rsplit(".", 1)[-1]) if result[f] != PLATFORM \
            else "reference data shared by several aggregates"
    return result, reason


def _cap_name(root: TypeSym) -> str:
    rules = {r for _, _, r in getattr(root, "entity_evidence", [])}
    if "dbcontext-generic-arg" in rules and root.name.lower().endswith("user"):
        return "Identity"
    return root.name


# ---------------------------------------------------------------------------
# 2. Capability assignment from dependencies
# ---------------------------------------------------------------------------

def assign_capabilities(tab: SymbolTable, entities: dict[str, TypeSym], sink: EdgeSink, facts: list[Fact],
                        extra_nodes: list[dict], workflows: list[dict],
                        overrides: dict | None = None) -> tuple[dict[str, str], dict[str, dict]]:
    edges = sink.all()
    agg, why = aggregates(entities, edges, workflows)
    cap_of: dict[str, str] = {}
    basis: dict[str, dict] = {}
    names: dict[str, str] = {PLATFORM: "Shared Platform"}
    for f, root in agg.items():
        if root == PLATFORM:
            cap_of[f] = PLATFORM
            basis[f] = {"rule": "capability.shared-reference-data", "detail": why.get(f, "")}
        else:
            cid = _slug(_cap_name(tab.by_fqn[root]))
            names[cid] = _cap_name(tab.by_fqn[root])
            cap_of[f] = cid
            basis[f] = {"rule": "capability.aggregate-root" if f == root else "capability.aggregate-member",
                        "detail": why.get(f, "")}
    for f in entities:  # entities outside any aggregate (should not happen) fall to platform below
        if f not in cap_of:
            cap_of[f] = PLATFORM
            basis[f] = {"rule": "capability.unassigned-platform", "detail": "no aggregate"}

    scores: dict[str, Counter] = defaultdict(Counter)
    detail: dict[str, Counter] = defaultdict(Counter)
    for fact in facts:
        if fact.kind == "ACCESSES_DATA" and fact.target in cap_of and cap_of[fact.target] != PLATFORM:
            w = WRITE_WEIGHT if fact.operation == "write" else READ_WEIGHT
            scores[fact.caller[0]][cap_of[fact.target]] += w
            detail[fact.caller[0]][f"{fact.operation}s {tab.by_fqn[fact.target].name}"] += 1
    for sym in tab.by_fqn.values():
        if sym.fqn in cap_of:
            continue
        if sym.role == "repository" and sym.entity is not None and sym.entity.fqn in cap_of:
            scores[sym.fqn][cap_of[sym.entity.fqn]] += WRITE_WEIGHT
            detail[sym.fqn][f"persists {sym.entity.name}"] += 1
        for b in tab.external_bases(sym):
            for a in b.args:
                if a.sym is not None and a.sym.fqn in cap_of and cap_of[a.sym.fqn] != PLATFORM:
                    scores[sym.fqn][cap_of[a.sym.fqn]] += GENERIC_BASE_WEIGHT
                    detail[sym.fqn][f"{b.name}<{a.sym.name}>"] += 1
    for e in edges:
        if e["kind"] == "MAPS_TO":
            for a, b in ((e["source"], e["target"]), (e["target"], e["source"])):
                if b in cap_of and a not in entities and cap_of[b] != PLATFORM:
                    scores[a][cap_of[b]] += MAP_WEIGHT
                    detail[a][f"maps {tab.by_fqn[b].name}"] += 1

    # cap -> root entity, for upstream tie-breaks
    cap_root = {cap_of[f]: f for f, r in agg.items() if f == r}
    root_refs = {(e["source"], e["target"]) for e in edges if e["kind"] == "REFERENCES"}

    def decide(node: str, sc: Counter) -> str | None:
        if not sc:
            return None
        total = sum(sc.values())
        ranked = sc.most_common()
        top, val = ranked[0]
        tied = sorted(c for c, v in ranked if v == val)
        if len(tied) > 1:
            # Prefer the upstream aggregate: the one the other tied roots reference.
            upstream = [c for c in tied if all(o == c or (cap_root.get(o), cap_root.get(c)) in root_refs
                                               for o in tied)]
            if len(upstream) == 1:
                return upstream[0]
            return PLATFORM if len(sc) >= 3 else None
        if len(sc) >= 3 and val / total < 0.4:
            return PLATFORM
        return top

    platform_roles = {"repository-base", "dbcontext", "http-application"}
    for sym in tab.by_fqn.values():
        if sym.fqn in cap_of:
            continue
        if sym.role in platform_roles:
            cap_of[sym.fqn] = PLATFORM
            basis[sym.fqn] = {"rule": "capability.platform-role", "detail": sym.role}
            continue
        c = decide(sym.fqn, scores.get(sym.fqn, Counter()))
        if c is not None:
            cap_of[sym.fqn] = c
            top = ", ".join(f"{k} ×{v}" for k, v in detail[sym.fqn].most_common(3))
            basis[sym.fqn] = {"rule": "capability.data-affinity" if c != PLATFORM else "capability.spread",
                              "detail": top}

    # Used by >= 3 capabilities (base controllers, unit of work, lookup services) -> platform
    users: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        if e["kind"] in {"CALLS", "INHERITS", "IMPLEMENTS"} and e["source"] in cap_of:
            users[e["target"]].add(cap_of[e["source"]])
    for _ in range(3):
        for e in edges:
            if e["kind"] in {"CALLS", "INHERITS", "IMPLEMENTS"} and e["source"] in cap_of:
                users[e["target"]].add(cap_of[e["source"]])
        for tgt, cs in users.items():
            real = cs - {PLATFORM}
            if len(real) >= 3 and tgt in tab.by_fqn and tgt not in entities:
                if cap_of.get(tgt) != PLATFORM:
                    cap_of[tgt] = PLATFORM
                    basis[tgt] = {"rule": "capability.shared-by-many", "detail": f"used by {len(real)} capabilities"}

    # Propagate along outgoing dependencies for types with no direct data affinity
    neighbours: dict[str, Counter] = defaultdict(Counter)
    for e in edges:
        if e["kind"] in {"CALLS", "MAPS_TO", "HTTP_CALLS", "BINDS_MODEL", "RENDERS"}:
            neighbours[e["source"]][e["target"]] += len(e["evidence"])
    for e in edges:
        # A view belongs with the controller that renders it; a model a view binds, or a type
        # only one capability constructs/calls, belongs with its users.
        if e["kind"] in {"RENDERS", "CALLS", "BINDS_MODEL"}:
            neighbours[e["target"]][e["source"]] += 1
    all_nodes = list(tab.by_fqn) + [n["id"] for n in extra_nodes]
    for _ in range(4):
        changed = False
        for nid in all_nodes:
            if nid in cap_of:
                continue
            sc = Counter()
            for nb, w in neighbours.get(nid, {}).items():
                c = cap_of.get(nb)
                if c and c != PLATFORM:
                    sc[c] += w
            c = decide(nid, sc)
            if c is not None:
                cap_of[nid] = c
                basis[nid] = {"rule": "capability.dependency-propagation",
                              "detail": ", ".join(f"{names.get(k, k)} ×{v}" for k, v in sc.most_common(3))}
                changed = True
        if not changed:
            break
    for nid in all_nodes:
        if nid not in cap_of:
            cap_of[nid] = PLATFORM
            basis[nid] = {"rule": "capability.unassigned-platform", "detail": "no data or dependency affinity"}

    # Satellite roots: an aggregate whose entity is written only from one other capability
    # (DocumentType created only by FormController) is part of that capability.
    writer_caps: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        if fact.kind == "ACCESSES_DATA" and fact.operation == "write":
            writer_caps[fact.target].add(cap_of.get(fact.caller[0], PLATFORM))
    for _ in range(3):
        folded = False
        for cid, root in list(cap_root.items()):
            ws = writer_caps.get(root, set()) - {PLATFORM}
            if len(ws) == 1 and cid not in ws:
                target = ws.pop()
                for nid, c in list(cap_of.items()):
                    if c == cid:
                        cap_of[nid] = target
                        basis[nid] = {**basis.get(nid, {}),
                                      "folded": f"{names.get(cid, cid)} is written only from {names.get(target, target)}"}
                del cap_root[cid]
                for f in list(writer_caps):
                    writer_caps[f] = {target if c == cid else c for c in writer_caps[f]}
                folded = True
        if not folded:
            break

    # Human overrides beat every rule
    ov = overrides or {}
    merge = {_slug(k): _slug(v) for k, v in (ov.get("merge") or {}).items()}
    for nid, c in list(cap_of.items()):
        if c in merge:
            cap_of[nid] = merge[c]
            basis[nid] = {**basis.get(nid, {}), "merged": f"{c} -> {merge[c]}"}
    for key, c in (ov.get("assign") or {}).items():
        for nid in [n for n in cap_of if n == key or n.rsplit(".", 1)[-1] == key or n.endswith(":" + key)]:
            cap_of[nid] = _slug(c)
            basis[nid] = {"rule": "capability.override", "detail": "akg-overrides.json"}
            names.setdefault(_slug(c), c)
    for cid, label in (ov.get("rename") or {}).items():
        names[_slug(cid)] = label
    capability_meta = {cid: {"id": cid, "name": names.get(cid, cid.replace("-", " ").title())}
                       for cid in set(cap_of.values())}
    return cap_of, {"basis": basis, "capabilities": capability_meta}


# ---------------------------------------------------------------------------
# 3. Lineage: view-model property -> entity property -> column
# ---------------------------------------------------------------------------

def _props(tab: SymbolTable, sym: TypeSym) -> dict[str, tuple[BType | None, int, TypeSym]]:
    out = {}
    for s, sub in reversed(tab.base_chain(BType(sym.name, sym))):
        for name, ms in s.members.items():
            for m in ms:
                if m.kind == "property":
                    out[name] = (tab.bind(m.type, s, sub), m.line, s)
    return out


def _split_pascal(name: str) -> list[str]:
    return re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", name)


def _resolve_path(tab: SymbolTable, sym: TypeSym, path: list[str]) -> tuple[TypeSym, str] | None:
    cur = sym
    for i, seg in enumerate(path):
        props = _props(tab, cur)
        if seg not in props:
            return None
        if i == len(path) - 1:
            return cur, seg
        nxt = _unwrap_collection(props[seg][0])
        if nxt is None or nxt.sym is None:
            return None
        cur = nxt.sym
    return None


def _flatten(tab: SymbolTable, sym: TypeSym, dest: str) -> list[str] | None:
    """AutoMapper flattening: ClientName -> Client.Name."""
    parts = _split_pascal(dest)
    for i in range(1, len(parts)):
        head, rest = "".join(parts[:i]), "".join(parts[i:])
        props = _props(tab, sym)
        if head in props:
            nxt = _unwrap_collection(props[head][0])
            if nxt is not None and nxt.sym is not None:
                tail = [rest] if rest in _props(tab, nxt.sym) else _flatten(tab, nxt.sym, rest)
                if tail:
                    return [head] + tail
    return None


_NUMERIC_CLR = {"Decimal": "decimal", "Double": "double", "Single": "float", "Int32": "int", "Int64": "long"}


def build_lineage(tab: SymbolTable, entities: dict[str, TypeSym], maps: list[MapDecl], ef: dict) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    ef_entities = ef.get("entities", {})
    for md in maps:
        pairs = [(md.source, md.dest, "read")] + ([(md.dest, md.source, "write")] if md.reverse else [])
        for src, dst, _ in pairs:
            src_is_entity, dst_is_entity = src.fqn in entities, dst.fqn in entities
            if src_is_entity == dst_is_entity:
                continue
            vm, ent = (dst, src) if src_is_entity else (src, dst)
            direction = "entity->view-model" if src_is_entity else "view-model->entity"
            explicit = {d: (p, ln) for d, p, ln in md.members} if src is md.source else {}
            vm_props = _props(tab, vm)
            for vprop, (vtype, vline, _) in vm_props.items():
                if src_is_entity:
                    if vprop in md.ignored:
                        continue
                    if vprop in explicit:
                        path, ln, rule = explicit[vprop][0].split("."), explicit[vprop][1], "lineage.automapper-formember"
                    elif vprop in _props(tab, ent):
                        path, ln, rule = [vprop], md.line, "lineage.automapper-name-match"
                    else:
                        flat = _flatten(tab, ent, vprop)
                        if not flat:
                            continue
                        path, ln, rule = flat, md.line, "lineage.automapper-flattening"
                else:
                    if vprop not in _props(tab, ent):
                        continue
                    path, ln, rule = [vprop], md.line, "lineage.automapper-name-match"
                hit = _resolve_path(tab, ent, path)
                if hit is None:
                    continue
                owner, prop = hit
                col = ef_entities.get(owner.fqn, {}).get("columns", {}).get(prop)
                table = ef_entities.get(owner.fqn, {}).get("table")
                if owner.fqn not in entities:
                    continue
                rid = f"LINEAGE:{vm.name}.{vprop}->{owner.name}.{prop}"
                if rid in seen:
                    continue
                seen.add(rid)
                vt = str(vtype) if vtype else ""
                note, risk = "", "low"
                if col:
                    clr = col.get("clrType", "")
                    vshort = vt.rsplit(".", 1)[-1].rstrip("?")
                    if clr in _NUMERIC_CLR and vshort and _NUMERIC_CLR.get(vshort, vshort.lower()) != _NUMERIC_CLR[clr]:
                        note, risk = f"Numeric type changes {vshort} -> {col['storeType']}", "high"
                    elif not col.get("nullable", True) and vshort and not vt.endswith("?") and vshort == "String":
                        note, risk = "Column is NOT NULL; view model allows null", "medium"
                else:
                    note = "No column in EF model snapshot (computed/navigation property)"
                rows.append({
                    "id": rid,
                    "kind": "FIELD_LINEAGE",
                    "direction": direction,
                    "source": vm.fqn,
                    "sourceField": f"{vm.name}.{vprop}",
                    "sourceType": vt,
                    "entity": owner.fqn,
                    "entityProperty": f"{owner.name}.{prop}",
                    "path": ".".join(path),
                    "target": table or owner.name,
                    "targetColumn": f"{table}.{col['column']}" if col and table else "",
                    "targetType": col["storeType"] if col else "",
                    "nullable": col.get("nullable") if col else None,
                    "conversionNote": note,
                    "semanticType": "view-model-to-column-lineage",
                    "migrationRisk": risk,
                    "file": md.file,
                    "line": ln,
                    "rule_id": rule,
                    "columnEvidence": ef.get("source"),
                })
    return rows


# ---------------------------------------------------------------------------
# 4. Workflows from entry points
# ---------------------------------------------------------------------------

def build_workflows(tab: SymbolTable, facts: list[Fact], entry_points: list[dict], max_depth: int = 6) -> list[dict]:
    by_caller: dict[tuple[str, str], list[Fact]] = defaultdict(list)
    for f in facts:
        by_caller[f.caller].append(f)

    def resolve_member(fqn: str, member: str) -> tuple[str, str]:
        sym = tab.by_fqn.get(fqn)
        if sym is None:
            return fqn, member
        hit = tab.lookup(BType(sym.name, sym), member, {"method", "constructor", "property"})
        return (hit[0].owner.fqn, member) if hit and hit[0].owner else (fqn, member)

    flows = []
    for ep in entry_points:
        start = (ep["type"], ep["member"])
        steps: list[dict] = []
        reads, writes, externals, events = set(), set(), set(), set()
        seen = {start}
        frontier = [(start, 0)]
        while frontier:
            (fqn, member), depth = frontier.pop(0)
            for f in by_caller.get((fqn, member), []):
                step = {"from": f"{fqn}.{member}", "kind": f.kind if f.kind != "LOCAL" else "CALLS",
                        "to": f.target if f.kind not in {"CALLS", "LOCAL"} else f"{f.target}.{f.member}",
                        "file": f.file, "line": f.line, "depth": depth + 1}
                if f.operation:
                    step["operation"] = f.operation
                if f.kind == "ACCESSES_DATA":
                    (writes if f.operation == "write" else reads).add(f.target)
                elif f.kind == "INVOKES_EXTERNAL":
                    externals.add(f.target)
                elif f.kind == "EMITS_EVENT":
                    events.add(f.target)
                elif depth + 1 < max_depth:
                    nxt = resolve_member(f.target, f.member or "")
                    if nxt not in seen:
                        seen.add(nxt)
                        frontier.append((nxt, depth + 1))
                if step not in steps:
                    steps.append(step)
        if not steps:
            continue
        flows.append({
            "id": f"WF:{ep['id']}",
            "entryPoint": f"{ep['type']}.{ep['member']}",
            "entryKind": ep["kind"],
            "trigger": ep.get("trigger"),
            "steps": steps,
            "reads": sorted(reads),
            "writes": sorted(writes),
            "externals": sorted(externals),
            "events": sorted(events),
            "depth": max(s["depth"] for s in steps),
            "fullyTraced": bool(writes or externals or events),
            "file": ep["file"],
            "line": ep["line"],
            "rule_id": f"workflow.{ep['kind']}",
        })
    return flows


# ---------------------------------------------------------------------------
# 5. Shared kernels
# ---------------------------------------------------------------------------

_COUPLING_KINDS = {"CALLS", "ACCESSES_DATA", "REFERENCES", "MAPS_TO", "HTTP_CALLS", "INHERITS", "IMPLEMENTS",
                   "BINDS_MODEL", "RENDERS", "INCLUDES", "HOSTS_SCRIPT", "READS_CONFIG"}


def shared_kernels(edges: list[dict], cap_of: dict[str, str], node_types: dict[str, str]) -> list[dict]:
    pair_edges: dict[tuple[str, str], list[dict]] = defaultdict(list)
    users: dict[str, set[str]] = defaultdict(set)
    use_count: Counter = Counter()
    for e in edges:
        if e["kind"] not in _COUPLING_KINDS:
            continue
        a, b = cap_of.get(e["source"]), cap_of.get(e["target"])
        if a and b and a != b and PLATFORM not in {a, b}:
            pair_edges[(a, b)].append(e)
        if a:
            users[e["target"]].add(a)
            use_count[e["target"]] += 1
    out: list[dict] = []
    done = set()
    for (a, b), es in pair_edges.items():
        if (b, a) not in pair_edges or (b, a) in done:
            continue
        done.add((a, b))
        back = pair_edges[(b, a)]
        weight = len(es) + len(back)
        out.append({
            "id": f"SK:{a}<->{b}",
            "nodeId": f"{a}<->{b}",
            "nodeType": "capability-pair",
            "consumingCapabilities": sorted({a, b}),
            "couplingDegree": weight,
            "edgeCount": weight,
            "edges": [x["id"] for x in es + back][:25],
            "recommendation": "Bidirectional dependency: define one owner per entity and replace the reverse calls "
                              "with an Anti-Corruption Layer or published read model",
            "migrationRisk": "critical" if weight >= 10 else "high",
            "rule_id": "kernel.bidirectional-capabilities",
        })
    for nid, caps in users.items():
        real = caps - {PLATFORM} if cap_of.get(nid) != PLATFORM else caps - {PLATFORM}
        if len(real) < 3:
            continue
        ntype = node_types.get(nid, "program")
        out.append({
            "id": f"SK:{nid}",
            "nodeId": nid,
            "nodeType": "table" if ntype == "entity" else "program",
            "consumingCapabilities": sorted(real),
            "couplingDegree": len(real),
            "edgeCount": use_count[nid],
            "recommendation": (
                "Shared entity: assign a single owning capability; others read through its API or a CDC-fed replica"
                if ntype == "entity" else
                "Shared code: extract into a platform library or service behind an Anti-Corruption Layer facade"),
            "migrationRisk": "critical" if len(real) >= 4 else "high",
            "rule_id": "kernel.used-by-3-plus",
        })
    return sorted(out, key=lambda k: (-k["couplingDegree"], -k["edgeCount"]))
