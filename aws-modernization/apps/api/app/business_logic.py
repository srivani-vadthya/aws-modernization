"""Business logic of one use case, read from the C# syntax tree (tree-sitter), for the Semantic IR.

The SIR's step rules say *which* data a use case touches. This module records *what it decides*: for the entry method
and the helper methods of the same class that it calls, every path through `if` / `else` / `switch` / `foreach` /
`catch`, and what happens on that path:

* values set from business literals: `model.StatusId = GetInvoiceStatusId("Pending")`
* refusals and errors: `return BadRequest(new { error = "InvoiceNumber" })`, `throw new Exception("...")`
* records added / updated / deleted: `Uow.Particulars.Add(item)`
* notifications and calls to other services: `_emailSvc.SendNeedApprovalInvoice(...)`

Helper methods are followed from their call site, so their paths carry the caller's conditions. A predicate helper
(`CheckIfInvoiceNumberExists`) is summarised by the query it runs (`Where(i => i.InvoiceNumber == ...)`), and a helper
that can fail (`CreateNewInvoice` returns false when ...) by when it fails, so a condition such as
`CreateNewInvoice(entity) == false` can be explained. Lookup helpers (`Get...`) are not followed: the literal they
are called with is the business value. Everything is verbatim source text with file and line; no meaning is
guessed here (wording happens in the story step). Only C# is analysed; other languages return None.
"""
from __future__ import annotations

import re
from functools import lru_cache

try:
    import tree_sitter as ts
    import tree_sitter_c_sharp as tscs
    _CS = ts.Language(tscs.language())
except Exception:  # pragma: no cover - the parser is an optional dependency
    _CS = None

MAX_RULES = 14
MAX_DEPTH = 3
_LOOKUP = re.compile(r"^(Get|Find|Load|Fetch|Lookup|Read|Retrieve|To|Map|Log|Build\w*Url|Prepare\w*Model)", re.I)
_PREDICATE = re.compile(r"^(CheckIf|Check|Is|Has|Can|Exists|Validate|Should|Must|Contains)", re.I)
_PLUMBING = re.compile(r"(SaveChanges|Dispose|^Log\w*|Detach|Commit|Rollback|AutoMapper|\bMap\b|ToString|ToList|"
                       r"ToArray|First|Single|Count|Any|Where|Select|Include|OrderBy|GetAll|GetById|Format)", re.I)
_DATA_RECEIVER = re.compile(r"\b(Uow|_?uow|_?db|_?dbContext|_?context|DataContext|_?unitOfWork)\b|Repository|Repo\b", re.I)
_DATA_OPS = {"add": "add", "addrange": "add", "insert": "add", "create": "add", "update": "update",
             "delete": "delete", "remove": "delete", "removerange": "delete"}
_NOTIFY = re.compile(r"^(Send|Notify|Email|Mail|Publish|Raise|Alert)", re.I)
_REFUSE = re.compile(r"BadRequest|Unauthorized|Forbid|Conflict|StatusCode\.(BadRequest|Unauthorized|Forbidden|Conflict)")
_NOT_FOUND = re.compile(r"NotFound")


def _text(node) -> str:
    return " ".join(node.text.decode("utf-8", "ignore").split()) if node is not None else ""


def _line(node) -> int:
    return node.start_point[0] + 1


@lru_cache(maxsize=64)
def _parse(source: str):
    return ts.Parser(_CS).parse(source.encode("utf-8")) if _CS else None


def _methods(root, name: str) -> list:
    out, stack = [], [root]
    while stack:
        n = stack.pop()
        if n.type == "method_declaration":
            nm = n.child_by_field_name("name")
            if nm is not None and _text(nm) == name:
                out.append(n)
        stack.extend(n.children)
    return sorted(out, key=_line)


def _invocations(node) -> list:
    out, stack = [], [node]
    while stack:
        n = stack.pop()
        if n.type == "invocation_expression":
            out.append(n)
        if n.type != "lambda_expression":
            stack.extend(n.children)
    return sorted(out, key=lambda n: n.start_byte)


def _callee(inv) -> tuple[str, str]:
    """(receiver text, method name) of an invocation: '_emailSvc.Send(x)' -> ('_emailSvc', 'Send')."""
    fn = inv.child_by_field_name("function")
    if fn is None:
        return "", ""
    if fn.type == "member_access_expression":
        name = fn.child_by_field_name("name")
        return _text(fn.child_by_field_name("expression")), re.sub(r"<.*$", "", _text(name))
    return "", re.sub(r"<.*$", "", _text(fn))


def _args(inv) -> list[str]:
    al = inv.child_by_field_name("arguments")
    return [_text(a) for a in al.named_children] if al is not None else []


def _has_literal(node) -> bool:
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in ("string_literal", "verbatim_string_literal", "integer_literal", "real_literal",
                      "boolean_literal", "character_literal", "interpolated_string_expression"):
            return True
        if n.type == "member_access_expression" and re.match(r"(DateTime\.(Now|Today|UtcNow)|\w*Enum\.\w+)$",
                                                             _text(n)):
            return True
        stack.extend(n.children)
    return False


def _exits(node) -> bool:
    """True when a statement always leaves the block: return / throw / continue, or a block ending with one."""
    if node is None:
        return False
    if node.type in ("return_statement", "throw_statement", "continue_statement"):
        return True
    if node.type == "block" and node.named_children:
        return _exits(node.named_children[-1])
    return False


class _Walker:
    """Walks one method body; records actions with the path of conditions that leads to them."""

    def __init__(self, analysis: "_Analysis", method: str, file: str, lines: list[str]):
        self.a, self.method, self.file, self.lines = analysis, method, file, lines
        self.local_lists: set[str] = set()      # local collections that items are removed from (a 'remaining' set)
        self.aliases: dict[str, dict] = {}
        # business values held in local variables, with the path they were set on:
        # `if (x.IsApprove) statusId = Get("approved"); else statusId = Get("rejected");` -> statusId: [(path, value)]
        self.locals: dict[str, list[tuple[list[dict], str]]] = {}

    # ---------------------------------------------------------------- statements
    def walk(self, node, path: list[dict]) -> None:
        t = node.type
        if t == "block":
            cur = path
            for ch in node.named_children:
                self.walk(ch, cur)
                # a guard clause ('if (soa == null) return;') means the rest of the block runs only when it is false
                if ch.type == "if_statement" and ch.child_by_field_name("alternative") is None \
                        and _exits(ch.child_by_field_name("consequence")):
                    cur = cur + [{"code": _text(ch.child_by_field_name("condition")), "negated": True}]
        elif t == "if_statement":
            cond = node.child_by_field_name("condition")
            self._calls_in(cond, path)
            code = _text(cond)
            self.walk(node.child_by_field_name("consequence"), path + [{"code": code, "negated": False}])
            alt = node.child_by_field_name("alternative")
            if alt is not None:
                self.walk(alt, path + [{"code": code, "negated": True}])
        elif t == "else_clause":
            for ch in node.named_children:
                self.walk(ch, path)
        elif t == "switch_statement":
            value = _text(node.child_by_field_name("value"))
            labels = []
            for section in node.child_by_field_name("body").named_children:
                pats = [_text(c) for c in section.named_children if c.type in ("constant_pattern", "case_switch_label")
                        or c.type.endswith("pattern")]
                is_default = any(c.type == "default" for c in section.children)
                cond = ({"code": value, "default": list(labels), "negated": False} if is_default or not pats else
                        {"code": " || ".join(f"{value} == {p}" for p in pats), "negated": False, "case": pats})
                labels += pats
                for ch in section.named_children:
                    if ch.type not in ("constant_pattern",) and not ch.type.endswith("pattern"):
                        self.walk(ch, path + [cond])
        elif t == "foreach_statement":
            var, coll = _text(node.child_by_field_name("left")), _text(node.child_by_field_name("right"))
            remaining = coll in self.local_lists
            self.walk(node.child_by_field_name("body"),
                      path + [{"code": coll, "foreach": var, "remaining": remaining, "negated": False}])
        elif t in ("for_statement", "while_statement", "do_statement", "using_statement", "lock_statement",
                   "checked_statement", "unsafe_statement", "fixed_statement"):
            body = node.child_by_field_name("body")
            if body is not None:
                self.walk(body, path)
        elif t == "try_statement":
            self.walk(node.child_by_field_name("body"), path)
            for ch in node.named_children:
                if ch.type == "catch_clause":
                    self.walk(ch.child_by_field_name("body"), path + [{"code": "", "catch": True, "negated": False}])
                elif ch.type == "finally_clause":
                    for b in ch.named_children:
                        self.walk(b, path)
        elif t == "local_declaration_statement":
            for decl in node.named_children[0].named_children if node.named_children else []:
                if decl.type != "variable_declarator":
                    continue
                name = _text(decl.child_by_field_name("name"))
                value = next((c for c in decl.named_children if c.type != "identifier"), None)
                if value is not None:
                    self.aliases[name] = {"code": _text(value), "kind": "value"}
                    self._calls_in(value, path)
                    self._queries(value, name)
                    if _has_literal(value) and ".Where(" not in _text(value):
                        self.locals[name] = [([dict(p) for p in path], _text(value))]
        elif t == "expression_statement":
            self._expression(node.named_children[0] if node.named_children else None, path, node)
        elif t == "return_statement":
            value = node.named_children[0] if node.named_children else None
            self._calls_in(value, path)
            code = _text(value)
            if code in ("false", "true"):
                self._add(path, {"type": "fail" if code == "false" else "succeed"}, node)
            elif value is not None and _NOT_FOUND.search(code):
                self._add(path, {"type": "not-found"}, node)
            elif value is not None and _REFUSE.search(code):
                err = re.search(r"\b(?:error|message|Message)\s*=\s*\"([^\"]+)\"|\"([^\"]+)\"", code)
                self._add(path, {"type": "refuse", "error": (err.group(1) or err.group(2)) if err else None}, node)
            elif value is not None:
                self._add(path, {"type": "return", "code": code}, node)
        elif t == "throw_statement":
            msg = re.search(r"\"([^\"]+)\"", _text(node))
            self._add(path, {"type": "throw", "message": msg.group(1) if msg else None}, node)

    # ---------------------------------------------------------------- expressions
    def _expression(self, expr, path, stmt) -> None:
        if expr is None:
            return
        if expr.type == "assignment_expression":
            left, right = expr.child_by_field_name("left"), expr.child_by_field_name("right")
            self._calls_in(right, path)
            if left is None or right is None:
                return
            target, value = _text(left), _text(right)
            init = right.child_by_field_name("initializer") if right.type == "object_creation_expression" else None
            if init is not None:
                # vm = new InvoiceItemViewModel { StatusName = "New", DueDate = DateTime.Now.AddMonths(1) }:
                # each member set from a business value is a rule of its own
                for member in init.named_children:
                    if member.type == "assignment_expression" and _has_literal(member.child_by_field_name("right")):
                        self._add(path, {"type": "set", "target": f"{target}.{_text(member.child_by_field_name('left'))}",
                                         "value": _text(member.child_by_field_name("right"))}, stmt)
                return
            if left.type == "identifier":                 # a local variable: remember its business value
                if _has_literal(right):
                    self.locals.setdefault(target, []).append(([dict(p) for p in path], value))
                return
            if left.type not in ("member_access_expression", "element_access_expression"):
                return
            if right.type == "identifier" and value in self.locals:
                # the field takes the value the local holds; each value comes with the conditions it was set under
                first_loop = next((i for i, p in enumerate(path) if p.get("foreach")), len(path))
                for lpath, val in self.locals[value]:
                    extra = [c for c in lpath if c not in path]
                    combined = path[:first_loop] + extra + path[first_loop:]
                    self._add(combined, {"type": "set", "target": target, "value": val}, stmt)
                return
            query = right.type == "identifier" and ".Where(" in str(self.aliases.get(value, {}).get("code", ""))
            linking = re.search(r"Id$", target) and re.search(r"(^|\.)Id$|Id$", value)   # foreign-key plumbing
            if _has_literal(right) or query or (path and not linking):
                self._add(path, {"type": "set", "target": target, "value": value}, stmt)
            return
        if expr.type == "invocation_expression":
            receiver, name = _callee(expr)
            op = _DATA_OPS.get(name.lower())
            if op and _DATA_RECEIVER.search(receiver):
                self._add(path, {"type": "data", "op": op, "entity": receiver.split(".")[-1], "args": _args(expr)}, stmt)
                return
            if name.lower() == "remove" and receiver in self.aliases:
                self.local_lists.add(receiver)
                return
            if not receiver or receiver == "this":
                if self.a.is_helper(name):
                    self._add(path, {"type": "step", "method": name}, stmt)
                    self.a.follow(name, path, self.method)
                return
            if _PLUMBING.search(name) or _PLUMBING.search(receiver.split(".")[-1]):
                return
            if receiver.startswith("_") or re.search(r"(Svc|Service|Manager|Client|Gateway|Notifier)$", receiver):
                kind = "notify" if _NOTIFY.match(name) else "call"
                self._add(path, {"type": kind, "method": name, "args": _args(expr)}, stmt)
            return
        self._calls_in(expr, path)

    def _calls_in(self, node, path) -> None:
        """Helpers called inside a condition or a value run on the current path: follow them."""
        if node is None:
            return
        for inv in _invocations(node):
            receiver, name = _callee(inv)
            if (not receiver or receiver == "this") and self.a.is_helper(name):
                self.a.follow(name, path, self.method)

    def _queries(self, value, name: str) -> None:
        for inv in _invocations(value):
            _, meth = _callee(inv)
            if meth == "Where":
                for arg in _args(inv):
                    m = re.fullmatch(r"\(?(\w+)\)?\s*=>\s*(.+)", arg)
                    if m:
                        self.a.queries.setdefault(self.method, []).append(
                            {"source": _text(inv.child_by_field_name("function")).rsplit(".Where", 1)[0],
                             "param": m.group(1), "predicate": m.group(2), "variable": name})

    def _add(self, path, action, node) -> None:
        self.a.actions.append({"path": [dict(p) for p in path], "action": action, "method": self.method,
                               "file": self.file, "line": _line(node),
                               "snippet": "\n".join(self.lines[_line(node) - 1: node.end_point[0] + 1]).strip()[:400]})


class _Analysis:
    def __init__(self, files: dict[str, list[str]], method_files: dict[str, str], owner: str,
                 method_lines: dict[str, set[int]] | None = None):
        self.files, self.method_files, self.owner = files, method_files, owner
        self.method_lines = method_lines or {}    # lines the workflow saw inside each method: picks the overload
        self.actions: list[dict] = []
        self.queries: dict[str, list[dict]] = {}
        self.aliases: dict[str, dict[str, dict]] = {}     # method -> variable -> what it holds
        self.helpers: dict[str, dict] = {}
        self._seen: set[tuple] = set()
        self._depth = 0

    def is_helper(self, name: str) -> bool:
        return name in self.method_files and not _PLUMBING.search(name)

    def follow(self, name: str, path: list[dict], caller: str) -> None:
        key = (name, tuple((p.get("code"), p.get("negated"), p.get("catch", False)) for p in path))
        if key in self._seen or self._depth >= MAX_DEPTH:
            return
        self._seen.add(key)
        if _LOOKUP.match(name):          # a lookup: the literal it is called with is the value, nothing to follow
            return
        self._depth += 1
        try:
            self.run(name, path)
        finally:
            self._depth -= 1

    def run(self, name: str, path: list[dict]) -> None:
        file = self.method_files.get(name)
        lines = self.files.get(file) or []
        tree = _parse("\n".join(lines)) if lines else None
        decls = _methods(tree.root_node, name) if tree else []
        if not decls:
            return
        hints = self.method_lines.get(name) or set()
        # overloads (Edit(int id) / Edit(Model m)): the one that contains the lines the workflow traced
        decls.sort(key=lambda d: not any(_line(d) <= h <= d.end_point[0] + 1 for h in hints))
        body = decls[0].child_by_field_name("body")
        if body is None:
            return
        before = len(self.actions)
        w = _Walker(self, name, file, lines)
        w.walk(body, path)
        self.aliases.setdefault(name, {}).update(w.aliases)
        own = [a for a in self.actions[before:] if a["method"] == name]   # not the actions of nested helpers
        fails = [a["path"][len(path):] for a in own if a["action"]["type"] == "fail"]
        succeeds = [a["path"][len(path):] for a in own if a["action"]["type"] == "succeed"]
        returns = [a["action"]["code"] for a in own if a["action"]["type"] == "return"]
        self.helpers[name] = {"failsWhen": fails, "succeedsWhen": succeeds, "returns": returns,
                              "where": self.queries.get(name, []), "predicate": bool(_PREDICATE.match(name)),
                              "file": file, "line": _line(decls[0])}


def analyse(entry: str, steps: list[dict], read_lines) -> dict | None:
    """Business logic of a use case. `entry` is the fully-qualified entry method, `steps` the workflow steps
    (from / to / file / line) and `read_lines(rel_path)` returns a source file's lines. None when not C#."""
    if _CS is None:
        return None
    owner = entry.rsplit(".", 1)[0]
    method_files: dict[str, str] = {}
    method_lines: dict[str, set[int]] = {}
    for s in steps:
        for fq in (s.get("from"), s.get("to")):
            if fq and fq.rsplit(".", 1)[0] == owner and s.get("file") and s["file"].endswith(".cs"):
                method_files.setdefault(fq.rsplit(".", 1)[1], s["file"])
        if s.get("from") and s["from"].rsplit(".", 1)[0] == owner and s.get("line"):
            method_lines.setdefault(s["from"].rsplit(".", 1)[1], set()).add(int(s["line"]))
    entry_name = entry.rsplit(".", 1)[1]
    if entry_name not in method_files:
        return None
    files = {f: read_lines(f) for f in set(method_files.values())}
    a = _Analysis(files, method_files, owner, method_lines)
    a.run(entry_name, [])
    # predicate helpers referenced only in conditions are summarised too (their query explains the check)
    for name, file in method_files.items():
        if name not in a.helpers and _PREDICATE.match(name):
            a.run(name, [{"code": "", "negated": False, "summary": True}])
            a.actions = [x for x in a.actions if not (x["path"] and x["path"][0].get("summary"))]
    return _rules(a, entry_name)


def _rules(a: _Analysis, entry_name: str) -> dict | None:
    """Group actions by path into rules; returns/folds are kept in the helper summaries, not as rules."""
    grouped: dict[tuple, dict] = {}
    for x in a.actions:
        kind = x["action"]["type"]
        if kind in ("fail", "succeed", "return", "step"):
            continue     # folded into the helper summaries; a helper's own actions carry the meaning of a call
        key = (tuple((p.get("code"), p.get("negated"), p.get("catch", False), p.get("foreach")) for p in x["path"]),
               "notify" if kind == "notify" else "main")
        rule = grouped.setdefault(key, {"when": x["path"], "then": [], "method": x["method"], "file": x["file"],
                                        "line": x["line"], "snippets": []})
        if x["action"] not in rule["then"]:
            rule["then"].append(x["action"])
            rule["snippets"].append(x["snippet"])
    rules = sorted(grouped.values(), key=lambda r: (r["method"] != entry_name, r["file"], r["line"]))[:MAX_RULES]
    if not rules:
        return None
    used = {m.group(0) for r in rules for p in r["when"] for m in re.finditer(r"\b\w+\b", str(p.get("code")))}
    used |= {m.group(0) for r in rules for t in r["then"] for v in t.values() if isinstance(v, str)
             for m in re.finditer(r"\b\w+\b", v)}
    used |= {m.group(0) for r in rules for t in r["then"] for v in t.get("args", []) for m in re.finditer(r"\b\w+\b", v)}
    helpers: dict[str, dict] = {}
    todo = [k for k in a.helpers if k in used]
    while todo:     # a helper that explains another helper's failure is needed too
        name = todo.pop()
        h = a.helpers.get(name)
        if name in helpers or not h or not (h["failsWhen"] or h["where"] or h["returns"]):
            continue
        helpers[name] = h
        todo += [m.group(0) for path in h["failsWhen"] + h["succeedsWhen"] for p in path
                 for m in re.finditer(r"\b\w+(?=\()", str(p.get("code")))]
        todo += [m.group(0) for r in h["returns"] for m in re.finditer(r"\b\w+(?=\()", r)]
    methods = {r["method"] for r in rules} | {entry_name} | set(helpers)
    # every variable of those methods: a query can refer to another variable (`p.ExpiryDate <= expiryDate`)
    aliases = {m: dict(a.aliases[m]) for m in methods if a.aliases.get(m)}
    return {"entry": entry_name, "rules": rules, "aliases": aliases, "helpers": helpers}
