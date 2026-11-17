"""HTTP surface: Web API/MVC route table, TypeScript HTTP calls, Razor views, Web.config."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import tree_sitter as ts
import tree_sitter_typescript as tsts

from . import catalog
from .csharp import BType, SymbolTable, TypeSym, line, text
from .extract import EdgeSink, _walk

TS_LANGUAGE = ts.Language(tsts.language_typescript())
TSX_LANGUAGE = ts.Language(tsts.language_tsx())


# ---------------------------------------------------------------------------
# Route table
# ---------------------------------------------------------------------------

@dataclass
class Action:
    controller: TypeSym
    method: str
    verbs: set[str]
    line: int
    templates: list[str] = field(default_factory=list)   # attribute-routed full templates


@dataclass
class RouteTable:
    actions: list[Action]
    api_conventions: list[tuple[str, str, int]]          # (template, file, line)
    mvc_conventions: list[tuple[str, str, int]]


def _verbs_for(m, api: bool) -> set[str]:
    verbs = {catalog.HTTP_VERB_ATTRS[a] for a, _, _ in m.attributes if a in catalog.HTTP_VERB_ATTRS}
    for a, args, _ in m.attributes:
        if a == "AcceptVerbs":
            verbs |= {x.upper() for x in args if x.isalpha()}
    if verbs:
        return verbs
    if api:  # Web API convention: action name prefix selects the verb
        for v in ("Get", "Post", "Put", "Delete", "Patch", "Head", "Options"):
            if m.name.startswith(v):
                return {v.upper()}
        return {"POST"}
    return {"GET"}


def build_route_table(tab: SymbolTable) -> RouteTable:
    actions: list[Action] = []
    for sym in tab.by_fqn.values():
        if sym.role not in {"api-controller", "mvc-controller"} or "abstract" in sym.modifiers:
            continue
        # ASP.NET Core controllers derive from ControllerBase and are API controllers when attribute-routed
        api = sym.role == "api-controller" or any(a == "ApiController" for a, _, _ in sym.attributes)
        ctrl_token = sym.name[: -len("Controller")] if sym.name.endswith("Controller") else sym.name
        # Web API 2: [RoutePrefix]; ASP.NET Core: class-level [Route]
        prefixes = [args[0] for a, args, _ in sym.attributes if a in {"RoutePrefix", "Route"} and args]
        prefix = prefixes[0] if prefixes else ""
        class_routed = any(a == "Route" for a, _, _ in sym.attributes)
        for name, ms in sym.members.items():
            for m in ms:
                if m.kind != "method" or "public" not in m.modifiers or "static" in m.modifiers:
                    continue
                if any(a == "NonAction" for a, _, _ in m.attributes):
                    continue
                act_name = next((args[0] for a, args, _ in m.attributes if a == "ActionName" and args), name)
                raw = [args[0] if args else "" for a, args, _ in m.attributes if a == "Route"]
                raw += [args[0] for a, args, _ in m.attributes if a in catalog.HTTP_VERB_ATTRS and args]
                if not raw and class_routed:
                    raw = [""]
                templates = []
                for tpl in raw:
                    if tpl.startswith("~/"):        # Web API 2: ignore the prefix
                        full = tpl[2:]
                    elif tpl.startswith("/"):       # ASP.NET Core: absolute template
                        full = tpl[1:]
                    else:
                        full = "/".join(x for x in (prefix, tpl) if x)
                    templates.append(full.replace("[controller]", ctrl_token).replace("[action]", act_name))
                actions.append(Action(sym, act_name, _verbs_for(m, api), m.line, templates))
    api_conv, mvc_conv = [], []
    for sf in tab.files:
        for n in _walk(sf.tree.root_node):
            if n.type != "invocation_expression":
                continue
            f = n.child_by_field_name("function")
            fname = text(f.child_by_field_name("name")) if f is not None and f.type == "member_access_expression" else ""
            if fname not in {"MapHttpRoute", "MapRoute"}:
                continue
            args = n.child_by_field_name("arguments")
            tpl = None
            for i, arg in enumerate(args.named_children if args else []):
                label = arg.child_by_field_name("name")
                lit = next((c for c in arg.named_children if c.type == "string_literal"), None)
                if lit is None:
                    continue
                val = "".join(text(c) for c in lit.named_children)
                if (label is not None and text(label) in {"routeTemplate", "url"}) or (label is None and i == 1):
                    tpl = val
            if tpl is not None:
                (api_conv if fname == "MapHttpRoute" else mvc_conv).append((tpl, sf.path, line(n)))
    return RouteTable(actions, api_conv, mvc_conv)


def _seg_match(tpl: str, path: list[str]) -> dict[str, str] | None:
    tsegs = [s for s in tpl.strip("/").split("/") if s]
    out: dict[str, str] = {}
    for i, ts_ in enumerate(tsegs):
        if i >= len(path):
            if ts_.startswith("{") and (ts_.endswith("?}") or "=" in ts_):
                continue
            if ts_.startswith("{*") or ts_.startswith("{**"):
                continue
            if ts_.startswith("{") and ts_.strip("{}").split(":")[0] == "id":
                continue  # RouteParameter.Optional on id in default templates
            return None
        if ts_.startswith("{"):
            out[ts_.strip("{}?").split(":")[0].split("=")[0]] = path[i]
        elif ts_.lower() != path[i].lower():
            return None
    return out if len(path) <= len(tsegs) else None


def match_route(rt: RouteTable, url: str, verb: str) -> tuple[Action, str] | None:
    path = [s for s in url.split("?")[0].strip("/").split("/") if s]
    for a in rt.actions:  # attribute routes first
        for tpl in a.templates:
            if _seg_match(tpl, path) is not None and verb in a.verbs:
                return a, "attribute-route"
    for tpl, _, _ in rt.api_conventions + rt.mvc_conventions:
        vals = _seg_match(tpl, path)
        if vals is None or "controller" not in vals:
            continue
        ctrl = vals["controller"].lower() + "controller"
        cands = [a for a in rt.actions if a.controller.name.lower() == ctrl and not a.templates]
        if not cands:
            # Controller only has attribute-routed actions; Web API still selects by verb within it
            cands = [a for a in rt.actions if a.controller.name.lower() == ctrl]
        if "action" in vals:
            cands = [a for a in cands if a.method.lower() == vals["action"].lower()]
        extra = vals.get("id")
        named = [a for a in cands if extra and a.method.lower() == extra.lower() and verb in a.verbs]
        if named:
            return named[0], "convention-route+action-name"
        by_verb = [a for a in cands if verb in a.verbs]
        if by_verb:
            return by_verb[0], "convention-route+verb"
    return None


# ---------------------------------------------------------------------------
# TypeScript HTTP calls
# ---------------------------------------------------------------------------

def _ts_text(n: ts.Node | None) -> str:
    return n.text.decode("utf-8", "ignore") if n is not None else ""


def _url_of(n: ts.Node) -> str | None:
    """Concatenate literal fragments of a URL expression; dynamic parts become '{x}'."""
    if n.type == "string":
        return "".join(_ts_text(c) for c in n.named_children if c.type == "string_fragment")
    if n.type == "template_string":
        out = ""
        for c in n.children:
            if c.type == "string_fragment":
                out += _ts_text(c)
            elif c.type == "template_substitution":
                out += "{x}"
        return out
    if n.type == "binary_expression":
        left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
        l, r = _url_of(left), _url_of(right)
        return (l if l is not None else "") + (r if r is not None else "")
    if n.type == "parenthesized_expression" and n.named_children:
        return _url_of(n.named_children[0])
    return None


def _actions_object(n: ts.Node | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if n is None or n.type != "object":
        return out
    for pair in (c for c in n.named_children if c.type == "pair"):
        key = _ts_text(pair.child_by_field_name("key")).strip("'\"")
        val = pair.child_by_field_name("value")
        for p2 in (c for c in (val.named_children if val is not None else []) if c.type == "pair"):
            if _ts_text(p2.child_by_field_name("key")).strip("'\"") == "method":
                out[key] = _ts_text(p2.child_by_field_name("value")).strip("'\"").upper()
    return out


@dataclass
class HttpCall:
    file: str
    line: int
    url: str
    verb: str
    client: str


def ts_http_calls(root: Path, rel: str, p: ts.Parser) -> tuple[list[HttpCall], list[str]]:
    src = (root / rel).read_bytes()
    tree = p.parse(src)
    calls: list[HttpCall] = []
    registered: list[str] = []
    resource_vars: dict[str, tuple[str, dict[str, str], int]] = {}
    for n in _walk(tree.root_node):
        if n.type != "call_expression":
            continue
        fn = n.child_by_field_name("function")
        args = n.child_by_field_name("arguments")
        argv = [a for a in (args.named_children if args is not None else [])]
        fname = _ts_text(fn)
        if fname.endswith(".controller") and argv and argv[0].type == "string":
            registered.append(_url_of(argv[0]) or "")
        if fname == "$resource" and argv:
            url = _url_of(argv[0])
            if not url or "/" not in url:
                continue
            custom = _actions_object(argv[2]) if len(argv) > 2 else {}
            parent = n.parent
            if parent is not None and parent.type == "member_expression":
                action = _ts_text(parent.child_by_field_name("property"))
                verb = custom.get(action) or catalog.NG_RESOURCE_ACTIONS.get(action)
                if verb:
                    calls.append(HttpCall(rel, n.start_point[0] + 1, url, verb, "$resource"))
            elif parent is not None and parent.type == "variable_declarator":
                resource_vars[_ts_text(parent.child_by_field_name("name"))] = (url, custom, n.start_point[0] + 1)
        elif fname.startswith("$http.") and argv:
            url = _url_of(argv[0])
            verb = fname.split(".", 1)[1].upper()
            if url and "/" in url and verb in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                calls.append(HttpCall(rel, n.start_point[0] + 1, url, verb, "$http"))
        elif fname == "fetch" and argv:
            url = _url_of(argv[0])
            verb = "GET"
            if len(argv) > 1:
                m = re.search(r"method\s*:\s*['\"](\w+)['\"]", _ts_text(argv[1]))
                verb = m.group(1).upper() if m else "GET"
            if url and "/" in url:
                calls.append(HttpCall(rel, n.start_point[0] + 1, url, verb, "fetch"))
    # var r = $resource(url, null, {patch: {method: 'PATCH'}}); r.patch(...)
    if resource_vars:
        for n in _walk(tree.root_node):
            if n.type != "call_expression":
                continue
            fn = n.child_by_field_name("function")
            if fn is None or fn.type != "member_expression":
                continue
            obj = _ts_text(fn.child_by_field_name("object"))
            if obj in resource_vars:
                url, custom, _ = resource_vars[obj]
                action = _ts_text(fn.child_by_field_name("property"))
                verb = custom.get(action) or catalog.NG_RESOURCE_ACTIONS.get(action)
                if verb:
                    calls.append(HttpCall(rel, n.start_point[0] + 1, url, verb, "$resource"))
    return calls, registered


# ---------------------------------------------------------------------------
# Razor views
# ---------------------------------------------------------------------------

_MODEL = re.compile(r"^\s*@model\s+([\w.<>, \[\]]+)", re.M)
_PARTIAL = re.compile(r"Html\.(?:Render)?Partial(?:Async)?\(\s*\"([^\"]+)\"")
_NG_CTRL = re.compile(r"ng-controller\s*=\s*\"(\w+)")


def _ln(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def razor_views(tab: SymbolTable, root: Path, views: list[str], sink: EdgeSink,
                ts_by_ctrl: dict[str, str]) -> list[dict]:
    nodes: list[dict] = []
    controllers = {s.name.lower(): s for s in tab.by_fqn.values() if s.role == "mvc-controller"}
    view_ids = {v: f"view:{v}" for v in views}
    by_folder_name: dict[tuple[str, str], str] = {}
    for v in views:
        pp = PurePosixPath(v)
        by_folder_name[(pp.parent.name.lower(), pp.stem.lower())] = v
    for v in views:
        src = (root / v).read_text(encoding="utf-8-sig", errors="ignore")
        pp = PurePosixPath(v)
        vid = view_ids[v]
        folder = pp.parent.name
        nodes.append({"id": vid, "label": f"{folder}/{pp.name}", "type": "view", "role": "razor-view", "path": v,
                      "file": v, "line": 1})
        m = _MODEL.search(src)
        if m:
            from .csharp import TExpr
            raw = m.group(1).strip()
            inner = re.sub(r"^(IEnumerable|IList|List|ICollection)<(.+)>$", r"\2", raw)
            model = tab.resolve_name(inner, None, usings=[], aliases={}, namespace="")
            if model is None:
                hits = tab.by_name.get(inner.rsplit(".", 1)[-1], [])
                model = hits[0] if len(hits) == 1 else None
            if model is not None:
                sink.add("BINDS_MODEL", vid, model.fqn, v, _ln(src, m.start()), "razor.model-directive",
                         cardinality="many" if inner != raw else "one")
        ctrl = controllers.get(f"{folder.lower()}controller")
        if ctrl is not None:
            ev = _view_call_site(ctrl, pp.stem)
            if ev is not None:
                sink.add("RENDERS", ctrl.fqn, vid, ctrl.file, ev[1], "razor.view-call", methods=[ev[0]])
            else:
                sink.add("RENDERS", ctrl.fqn, vid, v, 1, "razor.view-folder-convention")
        for pm in _PARTIAL.finditer(src):
            name = pm.group(1)
            target = None
            if name.startswith("~/"):
                target = name[2:]
                target = next((x for x in views if x.endswith(target)), None)
            else:
                target = by_folder_name.get((folder.lower(), name.lower())) or by_folder_name.get(("shared", name.lower()))
            if target:
                sink.add("INCLUDES", vid, view_ids[target], v, _ln(src, pm.start()), "razor.partial")
        for nm in _NG_CTRL.finditer(src):
            tsid = ts_by_ctrl.get(nm.group(1))
            if tsid:
                sink.add("HOSTS_SCRIPT", vid, tsid, v, _ln(src, nm.start()), "razor.ng-controller")
    return nodes


def _view_call_site(ctrl: TypeSym, view: str) -> tuple[str, int] | None:
    """Find `View("Name")`, or `View()` inside an action named like the view."""
    for name, ms in ctrl.members.items():
        for m in ms:
            if m.kind != "method":
                continue
            for n in _walk(m.node):
                if n.type != "invocation_expression":
                    continue
                f = n.child_by_field_name("function")
                if f is None or text(f) not in {"View", "PartialView"}:
                    continue
                args = n.child_by_field_name("arguments")
                lit = next((c for c in _walk(args) if c.type == "string_literal"), None) if args is not None else None
                called = "".join(text(c) for c in lit.named_children) if lit is not None else None
                if (called and called.lower() == view.lower()) or (called is None and name.lower() == view.lower()):
                    return name, line(n)
    return None


# ---------------------------------------------------------------------------
# Web.config / App.config
# ---------------------------------------------------------------------------

def config_entries(root: Path, configs: list[str]) -> list[dict]:
    out = []
    for rel in configs:
        raw = (root / rel).read_text(encoding="utf-8-sig", errors="ignore")
        try:
            xml = ET.fromstring(raw)
        except ET.ParseError:
            continue
        for section, attr, kind in (("connectionStrings", "name", "connection-string"), ("appSettings", "key", "app-setting")):
            for sec in xml.iter(section):
                for add in sec.iter("add"):
                    key = add.get(attr)
                    if not key:
                        continue
                    pos = raw.find(f'{attr}="{key}"')
                    entry = {"key": key, "kind": kind, "file": rel, "line": _ln(raw, pos) if pos >= 0 else 1}
                    if kind == "connection-string":
                        entry["provider"] = add.get("providerName", "")
                    out.append(entry)
    return out
