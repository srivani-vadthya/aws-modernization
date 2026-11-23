"""Edge extraction from C# bodies, one detection rule per edge type.

Every edge is recorded with {file, line, rule_id}. `EdgeSink.add` refuses an edge
without a source location, so nothing reaches the graph unless code put it there.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import tree_sitter as ts

from . import catalog
from .csharp import BType, Member, SourceFile, SymbolTable, TExpr, TypeSym, line, text, texpr


# ---------------------------------------------------------------------------
# Edge sink
# ---------------------------------------------------------------------------

@dataclass
class Fact:
    """Method-level fact used for workflow tracing."""
    caller: tuple[str, str]           # (type fqn, member)
    kind: str                         # CALLS | LOCAL | ACCESSES_DATA | INVOKES_EXTERNAL | EMITS_EVENT
    target: str                       # node id
    member: str | None
    operation: str | None
    file: str
    line: int


class EdgeSink:
    def __init__(self) -> None:
        self.edges: dict[tuple[str, str, str], dict] = {}
        self.rejected: list[dict] = []

    def add(self, kind: str, source: str, target: str, file: str | None, ln: int | None, rule: str,
            **attrs) -> None:
        if not file or not ln:
            self.rejected.append({"kind": kind, "source": source, "target": target, "rule": rule,
                                  "reason": "no source location"})
            return
        if source == target:
            return
        key = (kind, source, target)
        e = self.edges.get(key)
        if e is None:
            e = self.edges[key] = {"id": f"{kind}:{source}->{target}", "source": source, "target": target,
                                   "kind": kind, "file": file, "line": ln, "rule_id": rule, "evidence": []}
        ev = {"file": file, "line": ln, "rule_id": rule}
        if attrs.get("member"):
            ev["member"] = attrs["member"]
        if ev not in e["evidence"]:
            e["evidence"].append(ev)
        for k, v in attrs.items():
            if v is None or k == "member":
                continue
            if k in {"operations", "methods", "actions", "verbs", "urls", "via"}:
                vals = v if isinstance(v, (list, set, tuple)) else [v]
                e[k] = sorted(set(e.get(k, [])) | set(vals))
            else:
                e.setdefault(k, v)

    def all(self) -> list[dict]:
        return list(self.edges.values())


# ---------------------------------------------------------------------------
# Roles: entities, repositories, contexts, controllers
# ---------------------------------------------------------------------------

def _unwrap_collection(bt: BType | None) -> BType | None:
    if bt is not None and bt.sym is None and bt.name in catalog.COLLECTION_TYPES and bt.args:
        return bt.args[0]
    return bt


def assign_roles(tab: SymbolTable) -> dict[str, TypeSym]:
    """Mark entities, repositories, contexts, controllers. Returns entities by fqn."""
    entities: dict[str, TypeSym] = {}
    entity_sources: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

    def mark_entity(bt: BType | None, src: TypeSym, ln: int, rule: str) -> None:
        if bt is not None and bt.sym is not None and bt.sym.kind in {"class", "record"}:
            entities[bt.sym.fqn] = bt.sym
            entity_sources[bt.sym.fqn].append((src.file, ln, rule))

    # Repository base = generic solution type holding a DbSet<T> of its own type parameter.
    for sym in tab.by_fqn.values():
        if not sym.type_params:
            continue
        for ms in sym.members.values():
            for m in ms:
                if m.kind in {"field", "property"} and m.type and m.type.name in catalog.DBSET_TYPES \
                        and m.type.args and m.type.args[0].name in sym.type_params:
                    sym.role = "repository-base"

    for sym in tab.by_fqn.values():
        if sym.kind == "interface":
            sym.role = "interface"
            continue
        if sym.kind == "enum":
            sym.role = "enum"
            continue
        ext = tab.external_bases(sym)
        names = {b.name.rsplit(".", 1)[-1] for b in ext}
        if names & catalog.DBCONTEXT_BASES:
            sym.role = "dbcontext"
            for b in ext:
                if b.name.rsplit(".", 1)[-1] in catalog.DBCONTEXT_BASES:
                    for a in b.args:
                        mark_entity(a, sym, sym.line, "dbcontext-generic-arg")
            for ms in sym.members.values():
                for m in ms:
                    if m.kind == "property" and m.type and m.type.name in catalog.DBSET_TYPES and m.type.args:
                        mark_entity(tab.bind(m.type.args[0], sym), sym, m.line, "dbset-property")
        elif names & catalog.EF_CONFIG_BASES:
            sym.role = "ef-configuration"
            for b in ext:
                if b.name.rsplit(".", 1)[-1] in catalog.EF_CONFIG_BASES and b.args:
                    mark_entity(b.args[0], sym, sym.line, "ef-configuration")
        elif names & catalog.API_CONTROLLER_BASES:
            sym.role = "api-controller"
        elif names & catalog.MVC_CONTROLLER_BASES:
            sym.role = "mvc-controller"
        elif names & catalog.HTTP_APPLICATION_BASES:
            sym.role = "http-application"
        elif names & catalog.AUTOMAPPER_PROFILE_BASES and any("AutoMapper" in u for u in sym.usings):
            sym.role = "automapper-profile"
        if sym.role == "class":
            for base, sub in tab.base_chain(BType(sym.name, sym))[1:]:
                if base.role == "repository-base" and base.type_params:
                    ent = sub.get(base.type_params[0])
                    if ent is not None and ent.sym is not None:
                        sym.role = "repository"
                        sym.entity = ent.sym
                        mark_entity(ent, sym, sym.line, "repository-generic-arg")
                    break
    for fqn, sym in entities.items():
        sym.role = "entity"
    for sym in tab.by_fqn.values():
        sym.entity_evidence = entity_sources.get(sym.fqn, [])  # type: ignore[attr-defined]
    return entities


# ---------------------------------------------------------------------------
# Repository method classification (read / write / none) from method bodies
# ---------------------------------------------------------------------------

_WRITE_STATES = {"Added", "Modified", "Deleted"}
_DBSET_WRITES = {"Add", "AddRange", "Remove", "RemoveRange", "Attach"}


def classify_repository_methods(tab: SymbolTable) -> dict[tuple[str, str], str | None]:
    ops: dict[tuple[str, str], str | None] = {}
    pending: dict[tuple[str, str], set[str]] = {}
    for sym in tab.by_fqn.values():
        if sym.role not in {"repository-base", "repository"}:
            continue
        dbset_members = {n for n, ms in sym.members.items() for m in ms
                         if m.kind in {"field", "property"} and m.type and m.type.name in catalog.DBSET_TYPES}
        for name, ms in sym.members.items():
            for m in ms:
                if m.kind != "method":
                    continue
                write = detached = False
                calls: set[str] = set()
                for n in _walk(m.node):
                    if n.type == "member_access_expression":
                        nm = text(n.child_by_field_name("name"))
                        ex = text(n.child_by_field_name("expression"))
                        if ex.endswith("EntityState") and nm in _WRITE_STATES:
                            write = True
                        if ex.endswith("EntityState") and nm == "Detached":
                            detached = True
                    if n.type == "invocation_expression":
                        f = n.child_by_field_name("function")
                        if f is not None and f.type == "member_access_expression":
                            nm = text(f.child_by_field_name("name"))
                            ex = text(f.child_by_field_name("expression")).replace("this.", "")
                            if nm in _DBSET_WRITES and ex in dbset_members:
                                write = True
                            if ex in {"this", ""}:
                                calls.add(nm)
                        elif f is not None and f.type == "identifier":
                            calls.add(text(f))
                key = (sym.fqn, name)
                if write:
                    op = "write"
                elif detached:
                    op = None
                elif m.type is not None and m.type.name != "void":
                    op = "read"
                else:
                    op = None
                # Overloads share a name (Delete(T) / Delete(int)): strongest classification wins.
                rank = {"write": 2, "read": 1, None: 0}
                if rank[op] >= rank[ops.get(key)]:
                    ops[key] = op
                pending.setdefault(key, set()).update(calls)
    changed = True
    while changed:  # propagate writes through sibling calls, e.g. Delete(id) -> Delete(entity)
        changed = False
        for (fqn, name), calls in pending.items():
            if ops.get((fqn, name)) == "write":
                continue
            if any(ops.get((fqn, c)) == "write" for c in calls):
                ops[(fqn, name)] = "write"
                changed = True
    return ops


def _walk(node: ts.Node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.named_children))


# ---------------------------------------------------------------------------
# Body walker
# ---------------------------------------------------------------------------

def _external_ref(name: str, sym: TypeSym) -> tuple[str, str] | None:
    """Resolve an external type name to (namespace, type) via the file's usings."""
    if "." in name:
        ns, _, t = name.rpartition(".")
        return (ns, t) if (ns, t) in catalog.EXTERNAL_TYPES else None
    hits = [(u, name) for u in sym.usings if (u, name) in catalog.EXTERNAL_TYPES]
    return hits[0] if len(hits) == 1 else None


def _publisher_ref(name: str, method: str, sym: TypeSym) -> tuple[str, str, str] | None:
    for u in sym.usings:
        if (u, name, method) in catalog.EVENT_PUBLISHERS:
            return (u, name, method)
    return None


@dataclass
class MapDecl:
    source: TypeSym
    dest: TypeSym
    file: str
    line: int
    reverse: bool
    members: list[tuple[str, str, int]] = field(default_factory=list)   # (dest prop, src path, line)
    ignored: list[str] = field(default_factory=list)


class Extractor:
    def __init__(self, tab: SymbolTable, entities: dict[str, TypeSym],
                 repo_ops: dict[tuple[str, str], str | None], sink: EdgeSink):
        self.tab, self.entities, self.repo_ops, self.sink = tab, entities, repo_ops, sink
        self.facts: list[Fact] = []
        self.maps: list[MapDecl] = []
        self.config_reads: list[tuple[str, str, str, int]] = []   # (type fqn, key, file, line)

    # -- declarations -------------------------------------------------------
    def declarations(self) -> None:
        tab, sink = self.tab, self.sink
        for sym in tab.by_fqn.values():
            for b in sym.bases:
                bt = tab.bind(b, sym)
                if bt is None or bt.sym is None:
                    continue
                kind = "IMPLEMENTS" if bt.sym.kind == "interface" and sym.kind != "interface" else "INHERITS"
                sink.add(kind, sym.fqn, bt.sym.fqn, sym.file, sym.line, f"base-list.{kind.lower()}",
                         via=[str(b)])
            if sym.role == "entity":
                for name, ms in sym.members.items():
                    for m in ms:
                        if m.kind != "property":
                            continue
                        raw = tab.bind(m.type, sym)
                        tgt = _unwrap_collection(raw)
                        if tgt is not None and tgt.sym is not None and tgt.sym.fqn in self.entities:
                            card = "many" if raw is not tgt else "one"
                            sink.add("REFERENCES", sym.fqn, tgt.sym.fqn, sym.file, m.line,
                                     "entity.navigation-property", via=[name], cardinality=card)
            if sym.role == "ef-configuration":
                self._ef_config(sym)

    def _ef_config(self, sym: TypeSym) -> None:
        tab = self.tab
        ent = next((b.args[0] for b in tab.external_bases(sym)
                    if b.name.rsplit(".", 1)[-1] in catalog.EF_CONFIG_BASES and b.args), None)
        if ent is None or ent.sym is None:
            return
        for n in _walk(sym.node):
            if n.type != "invocation_expression":
                continue
            f = n.child_by_field_name("function")
            if f is None or f.type != "member_access_expression":
                continue
            meth = text(f.child_by_field_name("name"))
            if meth not in catalog.EF_RELATION_METHODS:
                continue
            prop = _lambda_member(n)
            if not prop:
                continue
            raw = tab.member_type(ent, prop, {"property"})
            tgt = _unwrap_collection(raw)
            if tgt is None or tgt.sym is None:
                continue
            self.sink.add("REFERENCES", ent.sym.fqn, tgt.sym.fqn, sym.file, line(n), "ef.fluent-relationship",
                          via=[f"{meth}({prop})"], cardinality=catalog.EF_RELATION_METHODS[meth])
            # chained inverse: .HasMany(p => p.Particulars).WithRequired(q => q.Invoice)
            parent = n.parent
            if parent is not None and parent.type == "member_access_expression" \
                    and text(parent.child_by_field_name("name")) in catalog.EF_INVERSE_METHODS \
                    and parent.parent is not None and parent.parent.type == "invocation_expression":
                inv = parent.parent
                back = _lambda_member(inv)
                if back:
                    bt = _unwrap_collection(tab.member_type(tgt, back, {"property"}))
                    if bt is not None and bt.sym is not None:
                        self.sink.add("REFERENCES", tgt.sym.fqn, bt.sym.fqn, sym.file, line(inv),
                                      "ef.fluent-relationship",
                                      via=[f"{text(parent.child_by_field_name('name'))}({back})"],
                                      cardinality="inverse")

    # -- bodies -------------------------------------------------------------
    def bodies(self) -> None:
        for sym in self.tab.by_fqn.values():
            if sym.kind == "interface":
                continue
            for name, ms in sym.members.items():
                for m in ms:
                    _Body(self, sym, m).run()


def _lambda_member(inv: ts.Node) -> str | None:
    """`x => x.Prop` as the first argument of an invocation -> 'Prop'."""
    args = inv.child_by_field_name("arguments")
    if args is None or not args.named_children:
        return None
    lam = args.named_children[0].named_children[0] if args.named_children[0].named_children else None
    if lam is None or lam.type != "lambda_expression":
        return None
    body = lam.child_by_field_name("body")
    if body is not None and body.type == "member_access_expression":
        return text(body.child_by_field_name("name"))
    return None


def _ident_name(node: ts.Node | None) -> str:
    if node is None:
        return ""
    if node.type == "generic_name":
        return text(next((c for c in node.named_children if c.type == "identifier"), node))
    return text(node)


def _generic_args(node: ts.Node | None) -> list[TExpr]:
    if node is None or node.type != "generic_name":
        return []
    tal = next((c for c in node.named_children if c.type == "type_argument_list"), None)
    return [t for t in (texpr(c) for c in (tal.named_children if tal else [])) if t]


class _Body:
    def __init__(self, ex: Extractor, sym: TypeSym, member: Member):
        self.ex, self.tab, self.sym, self.m = ex, ex.tab, sym, member
        self.self_type = BType(sym.name, sym, tuple(BType(t, tparam=True) for t in sym.type_params))
        self.locals: dict[str, tuple[TExpr | None, ts.Node | None]] = {}
        self.params = {n: t for n, t in member.params}
        self._memo: dict[int, BType | None] = {}
        self._busy: set[int] = set()

    def run(self) -> None:
        node = self.m.node
        self._collect_locals(node)
        for n in _walk(node):
            t = n.type
            if t == "invocation_expression":
                self._invocation(n)
            elif t == "object_creation_expression":
                self._creation(n)
            elif t == "element_access_expression":
                self._config_read(n)

    # -- locals -------------------------------------------------------------
    def _collect_locals(self, node: ts.Node) -> None:
        for n in _walk(node):
            if n.type == "variable_declaration" and n.parent is not None and n.parent.type != "field_declaration":
                ty = texpr(n.child_by_field_name("type"))
                for d in (c for c in n.named_children if c.type == "variable_declarator"):
                    name_node = d.child_by_field_name("name")
                    init = next((c for c in d.named_children if c is not name_node and c.type != "bracketed_argument_list"),
                                None)
                    if init is not None and init.type == "equals_value_clause":
                        init = init.named_children[0] if init.named_children else None
                    self.locals[text(name_node)] = (ty, init)
            elif n.type == "foreach_statement":
                ty = texpr(n.child_by_field_name("type"))
                left = n.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    self.locals[text(left)] = (ty, None)
            elif n.type in {"lambda_expression", "anonymous_method_expression"}:
                ps = n.child_by_field_name("parameters")
                for p in _walk(ps) if ps is not None else []:
                    if p.type in {"implicit_parameter", "identifier"} and (p.parent is ps or p.parent.type == "parameter"):
                        self.locals.setdefault(text(p), (None, None))
            elif n.type == "catch_declaration":
                nm = n.child_by_field_name("name")
                if nm is not None:
                    self.locals[text(nm)] = (texpr(n.child_by_field_name("type")), None)
            elif n.type == "declaration_expression":  # out var x
                nm = n.child_by_field_name("name")
                if nm is not None:
                    self.locals[text(nm)] = (texpr(n.child_by_field_name("type")), None)

    # -- type inference -------------------------------------------------------
    def infer(self, n: ts.Node | None) -> BType | None:
        if n is None:
            return None
        key = n.id
        if key in self._memo:
            return self._memo[key]
        if key in self._busy:
            return None
        self._busy.add(key)
        try:
            out = self._infer(n)
        finally:
            self._busy.discard(key)
        self._memo[key] = out
        return out

    def _infer(self, n: ts.Node) -> BType | None:
        tab, t = self.tab, n.type
        if t == "identifier":
            name = text(n)
            if name in self.locals:
                ty, init = self.locals[name]
                if ty is not None and ty.name != "var":
                    return tab.bind(ty, self.sym)
                return self.infer(init)
            if name in self.params:
                return tab.bind(self.params[name], self.sym)
            mt = tab.member_type(self.self_type, name, {"field", "property"})
            if mt is not None:
                return mt
            sym = tab.resolve_name(name, self.sym)
            if sym is not None:
                return BType(sym.name, sym)
            ext = _external_ref(name, self.sym)
            if ext is not None:
                return BType(f"{ext[0]}.{ext[1]}")
            return None
        if t == "this_expression" or (t == "this" ):
            return self.self_type
        if t == "base_expression":
            chain = tab.base_chain(self.self_type)
            return BType(chain[1][0].name, chain[1][0]) if len(chain) > 1 else None
        if t == "member_access_expression":
            whole = tab.resolve_name(text(n), self.sym)
            if whole is not None:
                return BType(whole.name, whole)
            recv = self.infer(n.child_by_field_name("expression"))
            name = _ident_name(n.child_by_field_name("name"))
            if recv is not None and recv.sym is not None:
                return tab.member_type(recv, name, {"field", "property"})
            if recv is None:
                ext = _external_ref(text(n), self.sym)
                if ext is not None:
                    return BType(f"{ext[0]}.{ext[1]}")
            return None
        if t == "invocation_expression":
            f = n.child_by_field_name("function")
            if f is None:
                return None
            if f.type == "member_access_expression":
                recv = self.infer(f.child_by_field_name("expression"))
                name = _ident_name(f.child_by_field_name("name"))
                if recv is not None and recv.sym is not None:
                    return tab.member_type(recv, name, {"method"})
                return None
            if f.type in {"identifier", "generic_name"}:
                return tab.member_type(self.self_type, _ident_name(f), {"method"})
            return None
        if t == "object_creation_expression":
            return tab.bind(texpr(n.child_by_field_name("type")), self.sym)
        if t in {"cast_expression"}:
            return tab.bind(texpr(n.child_by_field_name("type")), self.sym)
        if t == "as_expression":
            return tab.bind(texpr(n.child_by_field_name("right")), self.sym)
        if t in {"parenthesized_expression", "await_expression"}:
            inner = self.infer(n.named_children[0]) if n.named_children else None
            if t == "await_expression" and inner is not None and inner.sym is None and inner.name == "Task" and inner.args:
                return inner.args[0]
            return inner
        return None

    # -- edge rules -----------------------------------------------------------
    def _fact(self, kind: str, target: str, member: str | None, op: str | None, n: ts.Node) -> None:
        self.ex.facts.append(Fact((self.sym.fqn, self.m.name), kind, target, member, op, self.sym.file, line(n)))

    def _invocation(self, n: ts.Node) -> None:
        f = n.child_by_field_name("function")
        if f is None:
            return
        if f.type == "member_access_expression":
            name_node = f.child_by_field_name("name")
            mname = _ident_name(name_node)
            if mname == "CreateMap":
                self._create_map(n, name_node)
                return
            recv_node = f.child_by_field_name("expression")
            recv = self.infer(recv_node)
            if recv is None:
                return
            self._target(recv, mname, n)
        elif f.type in {"identifier", "generic_name"}:
            mname = _ident_name(f)
            if mname == "CreateMap":
                self._create_map(n, f)
                return
            hit = self.tab.lookup(self.self_type, mname, {"method"})
            if hit is None:
                return
            owner = hit[0].owner
            if owner is not None and owner.fqn != self.sym.fqn:
                self.ex.sink.add("CALLS", self.sym.fqn, owner.fqn, self.sym.file, line(n), "call.inherited-member",
                                 member=self.m.name, methods=[mname])
                self._fact("CALLS", owner.fqn, mname, None, n)
            else:
                self._fact("LOCAL", self.sym.fqn, mname, None, n)
        elif f.type == "conditional_access_expression":
            recv = self.infer(f.child_by_field_name("condition"))
            binding = next((c for c in f.named_children if c.type == "member_binding_expression"), None)
            if recv is not None and binding is not None:
                self._target(recv, _ident_name(binding.child_by_field_name("name")), n)

    def _target(self, recv: BType, mname: str, n: ts.Node) -> None:
        ex, sink, sym = self.ex, self.ex.sink, self.sym
        if recv.sym is not None:
            tsym = recv.sym
            # Data access through a repository: Uow.Invoices.GetAll() -> Invoice (read)
            for base, sub in self.tab.base_chain(recv):
                if base.role == "repository-base" and base.type_params:
                    ent = sub.get(base.type_params[0])
                    if ent is None or ent.sym is None:
                        break
                    hit = self.tab.lookup(recv, mname, {"method"})
                    if hit is None:
                        return
                    op = ex.repo_ops.get((hit[0].owner.fqn, mname))
                    if op is None:
                        return
                    sink.add("ACCESSES_DATA", sym.fqn, ent.sym.fqn, sym.file, line(n), "data.repository-call",
                             member=self.m.name, operations=[op], methods=[mname], via=[tsym.name])
                    self._fact("ACCESSES_DATA", ent.sym.fqn, mname, op, n)
                    return
            if tsym.fqn == sym.fqn:
                self._fact("LOCAL", sym.fqn, mname, None, n)
                return
            sink.add("CALLS", sym.fqn, tsym.fqn, sym.file, line(n), "call.invocation",
                     member=self.m.name, methods=[mname])
            self._fact("CALLS", tsym.fqn, mname, None, n)
            return
        # External receiver
        short = recv.name.rsplit(".", 1)[-1]
        if short in catalog.DBSET_TYPES and recv.args and recv.args[0].sym is not None \
                and recv.args[0].sym.fqn in ex.entities:
            ent = recv.args[0].sym
            op = "write" if mname in _DBSET_WRITES else "read"
            sink.add("ACCESSES_DATA", sym.fqn, ent.fqn, sym.file, line(n), "data.dbset-call",
                     member=self.m.name, operations=[op], methods=[mname])
            self._fact("ACCESSES_DATA", ent.fqn, mname, op, n)
            return
        pub = _publisher_ref(short, mname, sym)
        if pub is not None:
            tid = f"event:{pub[0]}.{pub[1]}.{pub[2]}"
            sink.add("EMITS_EVENT", sym.fqn, tid, sym.file, line(n), "event.publisher-call",
                     member=self.m.name, methods=[mname])
            self._fact("EMITS_EVENT", tid, mname, None, n)
            return
        ext = _external_ref(recv.name, sym)
        if ext is not None:
            tid = f"external:{ext[0]}.{ext[1]}"
            sink.add("INVOKES_EXTERNAL", sym.fqn, tid, sym.file, line(n), "external.member-call",
                     member=self.m.name, methods=[mname], category=catalog.EXTERNAL_TYPES[ext])
            self._fact("INVOKES_EXTERNAL", tid, mname, None, n)

    def _creation(self, n: ts.Node) -> None:
        te = texpr(n.child_by_field_name("type"))
        if te is None:
            return
        bt = self.tab.bind(te, self.sym)
        if bt is None:
            return
        if bt.sym is not None:
            if bt.sym.fqn != self.sym.fqn:
                self.ex.sink.add("CALLS", self.sym.fqn, bt.sym.fqn, self.sym.file, line(n), "call.object-creation",
                                 member=self.m.name, methods=[".ctor"])
                self._fact("CALLS", bt.sym.fqn, ".ctor", None, n)
            return
        ext = _external_ref(te.name, self.sym)
        if ext is not None:
            tid = f"external:{ext[0]}.{ext[1]}"
            self.ex.sink.add("INVOKES_EXTERNAL", self.sym.fqn, tid, self.sym.file, line(n), "external.object-creation",
                             member=self.m.name, methods=[".ctor"], category=catalog.EXTERNAL_TYPES[ext])
            self._fact("INVOKES_EXTERNAL", tid, ".ctor", None, n)

    def _config_read(self, n: ts.Node) -> None:
        expr = text(n.child_by_field_name("expression"))
        if not (expr.endswith("AppSettings") or expr.endswith("ConnectionStrings")):
            return
        if "ConfigurationManager" not in expr:
            return
        sub = n.child_by_field_name("subscript")
        lit = next((c for c in _walk(sub) if c.type == "string_literal"), None) if sub is not None else None
        if lit is None:
            return
        key = "".join(text(c) for c in lit.named_children) or text(lit).strip('"')
        self.ex.config_reads.append((self.sym.fqn, key, self.sym.file, line(n)))

    def _create_map(self, inv: ts.Node, name_node: ts.Node) -> None:
        args = _generic_args(name_node)
        if len(args) != 2:
            return
        src, dst = self.tab.bind(args[0], self.sym), self.tab.bind(args[1], self.sym)
        if src is None or dst is None or src.sym is None or dst.sym is None:
            return
        decl = MapDecl(src.sym, dst.sym, self.sym.file, line(inv), reverse=False)
        # Walk the fluent chain: CreateMap<S,D>().ForMember(...).ReverseMap()
        cur = inv
        while cur.parent is not None and cur.parent.type == "member_access_expression" \
                and cur.parent.parent is not None and cur.parent.parent.type == "invocation_expression":
            meth = _ident_name(cur.parent.child_by_field_name("name"))
            call = cur.parent.parent
            if meth == "ReverseMap":
                decl.reverse = True
            elif meth == "ForMember":
                dest_prop = _lambda_member(call)
                src_path = _map_from_path(call)
                if dest_prop and src_path:
                    decl.members.append((dest_prop, src_path, line(call)))
                elif dest_prop and "Ignore" in text(call):
                    decl.ignored.append(dest_prop)
            cur = call
        self.ex.maps.append(decl)
        self.ex.sink.add("MAPS_TO", src.sym.fqn, dst.sym.fqn, self.sym.file, line(inv), "automapper.create-map",
                         via=[self.sym.name])
        if decl.reverse:
            self.ex.sink.add("MAPS_TO", dst.sym.fqn, src.sym.fqn, self.sym.file, line(inv),
                             "automapper.reverse-map", via=[self.sym.name])


def _map_from_path(for_member: ts.Node) -> str | None:
    """ForMember(d => d.X, o => o.MapFrom(s => s.A.B)) -> 'A.B' (first member path only)."""
    for n in _walk(for_member):
        if n.type == "invocation_expression":
            f = n.child_by_field_name("function")
            if f is not None and f.type == "member_access_expression" and \
                    _ident_name(f.child_by_field_name("name")) in {"MapFrom", "ResolveUsing"}:
                lam = next((c for c in _walk(n) if c.type == "lambda_expression"), None)
                if lam is None:
                    return None
                param = text(lam.child_by_field_name("parameters")).strip("()")
                body = lam.child_by_field_name("body")
                # first member access chain rooted at the lambda parameter
                for m in _walk(body):
                    if m.type == "member_access_expression":
                        parts = text(m).split(".")
                        if parts and parts[0] == param and all(p.isidentifier() for p in parts):
                            return ".".join(parts[1:])
                return None
    return None
