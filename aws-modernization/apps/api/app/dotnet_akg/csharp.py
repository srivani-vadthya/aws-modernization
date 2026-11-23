"""C# declarations and a solution-wide symbol table built on the tree-sitter C# grammar.

This is the semantic layer the extractor resolves against. It is a deliberately
small subset of what Roslyn's SemanticModel provides:

  * every type declared in the solution, keyed by fully-qualified name
  * namespace + using-directive + alias aware name lookup (two `EmailService`
    classes in different namespaces stay distinct)
  * member lookup through the base-type chain with generic substitution, so
    `InvoiceRepository : GenericRepository<Invoice>` makes `GetById` return `Invoice`

Anything that cannot be resolved returns None; callers never guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter as ts
import tree_sitter_c_sharp as tscs

CS_LANGUAGE = ts.Language(tscs.language())
_TYPE_DECLS = {"class_declaration", "interface_declaration", "struct_declaration",
               "enum_declaration", "record_declaration", "record_struct_declaration"}
_PREDEFINED_ALIASES = {"string": "String", "int": "Int32", "long": "Int64", "bool": "Boolean",
                       "decimal": "Decimal", "double": "Double", "object": "Object"}


def parser() -> ts.Parser:
    return ts.Parser(CS_LANGUAGE)


def text(node: ts.Node | None) -> str:
    return node.text.decode("utf-8", "ignore") if node is not None else ""


def line(node: ts.Node) -> int:
    return node.start_point[0] + 1


# ---------------------------------------------------------------------------
# Type expressions (syntax) and bound types (semantics)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TExpr:
    """A type as written in source: `GenericRepository<Invoice>`, `IList<Particular>`."""
    name: str
    args: tuple["TExpr", ...] = ()

    def __str__(self) -> str:
        return self.name + (f"<{', '.join(map(str, self.args))}>" if self.args else "")


def texpr(node: ts.Node | None) -> TExpr | None:
    if node is None:
        return None
    t = node.type
    if t in {"identifier", "predefined_type"}:
        return TExpr(text(node))
    if t == "qualified_name":
        q, n = texpr(node.child_by_field_name("qualifier")), texpr(node.child_by_field_name("name"))
        if q and n:
            return TExpr(f"{q.name}.{n.name}", n.args)
        return TExpr(text(node))
    if t == "generic_name":
        ident = next((c for c in node.named_children if c.type == "identifier"), None)
        targs = next((c for c in node.named_children if c.type == "type_argument_list"), None)
        args = tuple(a for a in (texpr(c) for c in (targs.named_children if targs else [])) if a)
        return TExpr(text(ident), args)
    if t == "nullable_type":
        return texpr(node.child_by_field_name("type") or node.named_children[0])
    if t == "array_type":
        return TExpr("[]", tuple(a for a in [texpr(node.child_by_field_name("type"))] if a))
    if t == "alias_qualified_name":
        return texpr(node.child_by_field_name("name"))
    if t in {"implicit_type"}:
        return None
    return TExpr(text(node))


@dataclass
class Member:
    name: str
    kind: str                      # field | property | method | constructor | event
    type: TExpr | None
    line: int
    node: ts.Node
    params: list[tuple[str, TExpr | None]] = field(default_factory=list)
    attributes: list[tuple[str, list[str], int]] = field(default_factory=list)
    modifiers: set[str] = field(default_factory=set)
    owner: "TypeSym | None" = None


@dataclass
class TypeSym:
    fqn: str
    name: str
    namespace: str
    kind: str                      # class | interface | struct | enum | record
    file: str
    line: int
    project: str
    node: ts.Node
    type_params: list[str] = field(default_factory=list)
    bases: list[TExpr] = field(default_factory=list)
    attributes: list[tuple[str, list[str], int]] = field(default_factory=list)
    members: dict[str, list[Member]] = field(default_factory=dict)
    usings: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    outer: "TypeSym | None" = None
    modifiers: set[str] = field(default_factory=set)
    # filled by later passes
    role: str = "class"
    entity: "TypeSym | None" = None          # for repositories: the entity they persist

    def __hash__(self) -> int:
        return hash(self.fqn)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TypeSym) and other.fqn == self.fqn


@dataclass(frozen=True)
class BType:
    """A resolved type. `sym` is set for solution types; `name` is kept for externals."""
    name: str
    sym: TypeSym | None = None
    args: tuple["BType", ...] = ()
    tparam: bool = False

    @property
    def internal(self) -> bool:
        return self.sym is not None

    def __str__(self) -> str:
        base = self.sym.fqn if self.sym else self.name
        return base + (f"<{', '.join(map(str, self.args))}>" if self.args else "")


@dataclass
class SourceFile:
    path: str
    project: str
    tree: ts.Tree
    src: bytes
    usings: list[str]
    aliases: dict[str, str]
    types: list[TypeSym]


# ---------------------------------------------------------------------------
# Declaration collection
# ---------------------------------------------------------------------------

def _attributes(node: ts.Node) -> list[tuple[str, list[str], int]]:
    out = []
    for al in (c for c in node.children if c.type == "attribute_list"):
        for attr in (c for c in al.named_children if c.type == "attribute"):
            name = text(attr.child_by_field_name("name")).rsplit(".", 1)[-1]
            if name.endswith("Attribute"):
                name = name[: -len("Attribute")]
            args = []
            for al2 in (c for c in attr.named_children if c.type == "attribute_argument_list"):
                for arg in al2.named_children:
                    lit = _first(arg, "string_literal")
                    args.append(_string_value(lit) if lit is not None else text(arg))
            out.append((name, args, line(attr)))
    return out


def _modifiers(node: ts.Node) -> set[str]:
    return {text(c) for c in node.children if c.type == "modifier"}


def _first(node: ts.Node, type_name: str) -> ts.Node | None:
    if node.type == type_name:
        return node
    for c in node.named_children:
        hit = _first(c, type_name)
        if hit is not None:
            return hit
    return None


def _string_value(node: ts.Node) -> str:
    if node.type in {"string_literal", "verbatim_string_literal", "raw_string_literal"}:
        parts = [text(c) for c in node.named_children if c.type in {"string_literal_content", "string_content"}]
        if parts:
            return "".join(parts)
        raw = text(node)
        return raw.lstrip("@").strip('"')
    return text(node)


def _members(sym: TypeSym, body: ts.Node | None) -> None:
    if body is None:
        return
    for c in body.named_children:
        t = c.type
        mods, attrs = _modifiers(c), _attributes(c)
        if t == "field_declaration" or t == "event_field_declaration":
            vd = next((x for x in c.named_children if x.type == "variable_declaration"), None)
            if vd is None:
                continue
            ty = texpr(vd.child_by_field_name("type"))
            for decl in (x for x in vd.named_children if x.type == "variable_declarator"):
                nm = text(decl.child_by_field_name("name"))
                sym.members.setdefault(nm, []).append(
                    Member(nm, "field", ty, line(decl), c, attributes=attrs, modifiers=mods, owner=sym))
        elif t == "property_declaration":
            nm = text(c.child_by_field_name("name"))
            sym.members.setdefault(nm, []).append(
                Member(nm, "property", texpr(c.child_by_field_name("type")), line(c), c,
                       attributes=attrs, modifiers=mods, owner=sym))
        elif t in {"method_declaration", "constructor_declaration", "operator_declaration"}:
            nm = text(c.child_by_field_name("name")) if t != "constructor_declaration" else ".ctor"
            ret = texpr(c.child_by_field_name("returns") or c.child_by_field_name("type"))
            params = []
            plist = c.child_by_field_name("parameters")
            for p in (plist.named_children if plist else []):
                if p.type == "parameter":
                    params.append((text(p.child_by_field_name("name")), texpr(p.child_by_field_name("type"))))
            sym.members.setdefault(nm, []).append(
                Member(nm, "method" if t != "constructor_declaration" else "constructor", ret, line(c), c,
                       params=params, attributes=attrs, modifiers=mods, owner=sym))


def _collect(node: ts.Node, ns: str, outer: TypeSym | None, sf: SourceFile, out: list[TypeSym]) -> None:
    for c in node.named_children:
        if c.type in {"namespace_declaration", "file_scoped_namespace_declaration"}:
            name = text(c.child_by_field_name("name"))
            full = f"{ns}.{name}" if ns else name
            if c.type == "file_scoped_namespace_declaration":
                # Following siblings belong to this namespace.
                ns = full
                continue
            _collect(c.child_by_field_name("body"), full, None, sf, out)
        elif c.type in _TYPE_DECLS:
            name = text(c.child_by_field_name("name"))
            container = outer.fqn if outer else ns
            fqn = f"{container}.{name}" if container else name
            tp = c.child_by_field_name("type_parameters") or next(
                (x for x in c.named_children if x.type == "type_parameter_list"), None)
            sym = TypeSym(
                fqn=fqn, name=name, namespace=ns, kind=c.type.replace("_declaration", "").replace("record_struct", "record"),
                file=sf.path, line=line(c), project=sf.project, node=c,
                type_params=[text(x.child_by_field_name("name") or x) for x in (tp.named_children if tp else [])
                             if x.type == "type_parameter"],
                bases=[b for b in (texpr(x) for x in next((x for x in c.named_children if x.type == "base_list"),
                                                          _EMPTY).named_children) if b],
                attributes=_attributes(c), usings=sf.usings, aliases=sf.aliases, outer=outer,
                modifiers=_modifiers(c),
            )
            out.append(sym)
            body = c.child_by_field_name("body")
            _members(sym, body)
            if body is not None:
                _collect(body, ns, sym, sf, out)
        elif c.type in {"declaration_list", "global_statement"}:
            _collect(c, ns, outer, sf, out)


class _Empty:
    named_children: list = []


_EMPTY = _Empty()


def parse_file(root: Path, rel: str, project: str, p: ts.Parser) -> SourceFile:
    src = (root / rel).read_bytes()
    tree = p.parse(src)
    usings, aliases = [], {}
    for u in (c for c in tree.root_node.named_children if c.type == "using_directive"):
        alias = u.child_by_field_name("name")
        target = next((c for c in u.named_children if c is not alias and c.type in {"qualified_name", "identifier"}), None)
        if alias is not None and target is not None:
            aliases[text(alias)] = text(target)
        elif target is not None:
            usings.append(text(target))
    # usings declared inside namespace blocks apply too
    for ns in (c for c in tree.root_node.named_children if c.type == "namespace_declaration"):
        body = ns.child_by_field_name("body")
        for u in (c for c in (body.named_children if body else []) if c.type == "using_directive"):
            target = next((c for c in u.named_children if c.type in {"qualified_name", "identifier"}), None)
            if target is not None:
                usings.append(text(target))
    sf = SourceFile(rel, project, tree, src, usings, aliases, [])
    _collect(tree.root_node, "", None, sf, sf.types)
    return sf


# ---------------------------------------------------------------------------
# Symbol table
# ---------------------------------------------------------------------------

class SymbolTable:
    def __init__(self, files: list[SourceFile]):
        self.files = files
        self.by_fqn: dict[str, TypeSym] = {}
        self.by_name: dict[str, list[TypeSym]] = {}
        self.namespaces: set[str] = set()
        for f in files:
            for s in f.types:
                # partial classes: merge members into the first declaration
                if s.fqn in self.by_fqn:
                    first = self.by_fqn[s.fqn]
                    for k, v in s.members.items():
                        first.members.setdefault(k, []).extend(v)
                    first.bases.extend(b for b in s.bases if b not in first.bases)
                    continue
                self.by_fqn[s.fqn] = s
                self.by_name.setdefault(s.name, []).append(s)
                parts = s.namespace.split(".") if s.namespace else []
                for i in range(1, len(parts) + 1):
                    self.namespaces.add(".".join(parts[:i]))

    # -- name resolution ----------------------------------------------------
    def resolve_name(self, name: str, ctx: TypeSym | None, usings: list[str] | None = None,
                     aliases: dict[str, str] | None = None, namespace: str | None = None) -> TypeSym | None:
        usings = usings if usings is not None else (ctx.usings if ctx else [])
        aliases = aliases if aliases is not None else (ctx.aliases if ctx else {})
        namespace = namespace if namespace is not None else (ctx.namespace if ctx else "")
        head, _, rest = name.partition(".")
        if head in aliases:
            name = aliases[head] + ("." + rest if rest else "")
        if name.startswith("global::"):
            name = name[len("global::"):]
        # 1. nested types of the enclosing type chain (and their bases)
        o = ctx
        while o is not None:
            for t in self._self_and_bases(o):
                hit = self.by_fqn.get(f"{t.fqn}.{name}")
                if hit:
                    return hit
            o = o.outer
        # 2. current namespace and its parents
        parts = namespace.split(".") if namespace else []
        for i in range(len(parts), -1, -1):
            prefix = ".".join(parts[:i])
            hit = self.by_fqn.get(f"{prefix}.{name}" if prefix else name)
            if hit:
                return hit
        # 3. using directives (C# reports ambiguity as an error, so first unique match is correct)
        hits = {self.by_fqn[f"{u}.{name}"] for u in usings if f"{u}.{name}" in self.by_fqn}
        if len(hits) == 1:
            return hits.pop()
        return None

    def _self_and_bases(self, sym: TypeSym) -> list[TypeSym]:
        out, seen, todo = [], set(), [sym]
        while todo:
            s = todo.pop(0)
            if s.fqn in seen:
                continue
            seen.add(s.fqn)
            out.append(s)
            for b in s.bases:
                bs = self.resolve_name(b.name, s.outer or None, s.usings, s.aliases, s.namespace)
                if bs:
                    todo.append(bs)
        return out

    def bind(self, te: TExpr | None, ctx: TypeSym | None, subst: dict[str, BType] | None = None,
             method_tparams: set[str] | None = None) -> BType | None:
        if te is None:
            return None
        subst = subst or {}
        if not te.args and te.name in subst:
            return subst[te.name]
        if ctx is not None and te.name in ctx.type_params or (method_tparams and te.name in method_tparams):
            return BType(te.name, tparam=True)
        args = tuple(self.bind(a, ctx, subst, method_tparams) or BType(str(a)) for a in te.args)
        sym = self.resolve_name(te.name, ctx)
        if sym is not None:
            return BType(sym.name, sym, args)
        return BType(_PREDEFINED_ALIASES.get(te.name, te.name), None, args)

    # -- inheritance ----------------------------------------------------------
    def base_chain(self, bt: BType) -> list[tuple[TypeSym, dict[str, BType]]]:
        """[(type, substitution)] from `bt` up through every internal base/interface."""
        out: list[tuple[TypeSym, dict[str, BType]]] = []
        seen: set[str] = set()
        todo: list[tuple[TypeSym, dict[str, BType]]] = []
        if bt.sym is not None:
            todo.append((bt.sym, dict(zip(bt.sym.type_params, bt.args))))
        while todo:
            sym, sub = todo.pop(0)
            if sym.fqn in seen:
                continue
            seen.add(sym.fqn)
            out.append((sym, sub))
            for b in sym.bases:
                bb = self.bind(b, sym, sub)
                if bb is not None and bb.sym is not None:
                    todo.append((bb.sym, dict(zip(bb.sym.type_params, bb.args))))
        return out

    def external_bases(self, sym: TypeSym, sub: dict[str, BType] | None = None) -> list[BType]:
        """External (framework) base types anywhere in the chain, with generic args bound."""
        out = []
        for s, sb in self.base_chain(BType(sym.name, sym, tuple((sub or {}).get(tp) or BType(tp, tparam=True)
                                                                  for tp in sym.type_params))):
            for b in s.bases:
                bb = self.bind(b, s, sb)
                if bb is not None and bb.sym is None:
                    out.append(bb)
        return out

    def lookup(self, bt: BType, member: str, kinds: set[str] | None = None) -> tuple[Member, dict[str, BType]] | None:
        for sym, sub in self.base_chain(bt):
            for m in sym.members.get(member, []):
                if kinds is None or m.kind in kinds:
                    return m, sub
        return None

    def member_type(self, bt: BType, member: str, kinds: set[str] | None = None) -> BType | None:
        hit = self.lookup(bt, member, kinds)
        if hit is None:
            return None
        m, sub = hit
        return self.bind(m.type, m.owner, sub)

    def is_subtype(self, sym: TypeSym, ancestor: TypeSym) -> bool:
        return any(s.fqn == ancestor.fqn for s, _ in self.base_chain(BType(sym.name, sym)))
