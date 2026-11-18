"""Semantic IR (SIR) generation for the scoped module, from the AKG + AST artifacts.

Pipeline (follows apps/scripts/sir-generation-instructions.md: the LLM only ever sees *bounded nodes*):
  1. Deterministic scaffold. Each traced use case (entry point -> calls -> data / external / event) becomes
     one SIR contract. Every rule is anchored to an AST step: file, line, a snippet read verbatim from the
     source, and the AST node id. These trace fields are never produced by the LLM.
  2. Semantic lifting (LLM). For each contract the LLM is asked for business wording only: contract
     name/summary, the statement + classification of each rule, the state machine and side effects.
  3. Safe merge. Only those wording fields are accepted, validated, and tagged with their provenance. If the
     LLM is unavailable the deterministic wording stays and the contract is tagged "deterministic".
"""
from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import business_logic, legacy_assessment, scope_modules, store
from .llm_json import ask_json

logger = logging.getLogger(__name__)

MAX_CONTRACTS = 12
MAX_RULES = 10
LLM_CHUNK = 3
SNIPPET_AFTER = 1

DETERMINISTIC_CORE = "Deterministic Core (Must not be altered by LLM)"
PRUNED = "Pruned — replaced by cloud framework"
APPLICATION_LOGIC = "Application Logic"
KINDS = {"deterministic_business_rule", "legacy_plumbing_pruned"}

_PLUMBING = re.compile(r"(SaveChanges|Dispose|\bLog\w*|GetRepository|Commit|Rollback|AutoMapper|\.Map\b|ToString|"
                       r"Format|Initialize|\.Close\b|\.Open\b)", re.I)
_BRANCH = re.compile(r"^\s*(if\b|else\s+if\b|switch\b|throw\b|return\s+(BadRequest|NotFound|Forbid|Unauthorized|"
                     r"HttpNotFound)|ModelState\.AddModelError|.*\.Validate\w*\()")
_OPERATIONAL_EDGES = {"CALLS", "READS", "WRITES", "ACCESSES_DATA", "INVOKES_EXTERNAL", "REFERENCES", "MAPS_TO",
                      "HTTP_CALLS"}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- source access (AST evidence)

class _Source:
    def __init__(self, root: Path | None):
        self.root = root.resolve() if root else None
        self._cache: dict[str, list[str]] = {}

    def lines(self, rel: str | None) -> list[str]:
        if not rel or not self.root:
            return []
        if rel not in self._cache:
            lines: list[str] = []
            try:
                p = (self.root / rel).resolve()
                if p.is_relative_to(self.root) and p.is_file():
                    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                pass
            self._cache[rel] = lines
        return self._cache[rel]

    def snippet(self, rel: str | None, line: int | None, after: int = SNIPPET_AFTER) -> str:
        lines = self.lines(rel)
        if not lines or not line or line < 1 or line > len(lines):
            return ""
        chunk = [ln.rstrip() for ln in lines[line - 1: line + after]]
        indent = min((len(c) - len(c.lstrip()) for c in chunk if c.strip()), default=0)
        return "\n".join(c[indent:] for c in chunk).strip()

    def find_token(self, rel: str | None, token: str) -> int | None:
        """First line mentioning `token` (case-insensitive); used for graphs whose edges carry no line."""
        if not token:
            return None
        needle = token.lower()
        for i, ln in enumerate(self.lines(rel), 1):
            bare = ln.strip()
            if bare.startswith(("*", "//", "#", "--", "/*")) or (len(ln) > 6 and ln[6] == "*"):
                continue  # comment lines (incl. COBOL col-7 '*') are not evidence
            if needle in ln.lower():
                return i
        return None


def _brace_span(lines: list[str], start: int) -> int | None:
    """1-based line where the block opened at/after `start` (1-based) closes."""
    depth, opened = 0, False
    for i in range(start - 1, len(lines)):
        text = re.sub(r'"(?:[^"\\]|\\.)*"|//.*', "", lines[i])
        for ch in text:
            if ch == "{":
                depth, opened = depth + 1, True
            elif ch == "}":
                depth -= 1
                if opened and depth == 0:
                    return i + 1
    return None


def _locate_method(lines: list[str], member: str, hint_line: int | None) -> tuple[int, int, str] | None:
    """(decl_line, end_line, parameter_text) of method `member`; prefers the overload that contains hint_line."""
    pat = re.compile(rf"^\s*(?:\[[^\]]*\]\s*)*(?:public|protected|private|internal)\b[^;=]*?\b{re.escape(member)}\s*\(")
    found = []
    for i, ln in enumerate(lines, 1):
        if pat.search(ln):
            text = " ".join(lines[i - 1: i + 6])
            start = text.index(member + "(") if member + "(" in text else text.index(member)
            depth, params, j = 0, "", text.index("(", start)
            for ch in text[j:]:
                if ch == "(":
                    depth += 1
                    if depth == 1:
                        continue
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                params += ch
            end = _brace_span(lines, i)
            if end:
                found.append((i, end, params))
    for cand in found:
        if hint_line and cand[0] <= hint_line <= cand[1]:
            return cand
    return found[0] if found else None


def _parse_params(text: str) -> list[dict]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    out = []
    for raw in parts:
        raw = re.sub(r"\[[^\]]*\]", "", raw).strip()
        raw = re.sub(r"^(this|params|ref|out|in)\s+", "", raw)
        if not raw:
            continue
        default = "=" in raw
        raw = raw.split("=")[0].strip()
        bits = raw.rsplit(None, 1)
        if len(bits) == 2:
            out.append({"name": bits[1], "type": bits[0], "required": not default and not bits[0].endswith("?")})
    return out


# --------------------------------------------------------------------------- scaffold helpers

def _short(symbol: str, parts: int = 2) -> str:
    return ".".join(symbol.split(".")[-parts:])


def _snake(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", scope_modules._words(text)).strip("_").upper()


def _rule(n: int, sir_id: str, *, step_kind: str, target: str, owner: str, file: str | None, line: int | None,
          src: _Source, statement: str, classification: str, kind: str, trust: str, operation: str | None = None,
          snippet: str | None = None) -> dict:
    node_kind = {"ACCESSES_DATA": "WRITES" if operation == "write" else "READS"}.get(step_kind, step_kind)
    return {
        "ruleId": f"{sir_id}.R{n}", "statement": statement, "classification": classification, "kind": kind,
        "astNode": f"AST:{_short(owner)}:L{line or 0}:{node_kind}",
        "legacyLines": f"{file}#L{line}" if file and line else (file or ""),
        "snippet": snippet if snippet is not None else src.snippet(file, line),
        "trustBoundary": trust, "source": "deterministic",
        "_target": target,
    }


def _step_rule(n: int, sir_id: str, step: dict, src: _Source, label: dict[str, str]) -> dict | None:
    kind, to, frm = step["kind"], step["to"], step["from"]
    if to.endswith((".ctor", ".cctor")):
        return None
    target = label.get(to, to.rsplit(".", 1)[-1])
    member = to.rsplit(".", 1)[-1]
    common = dict(step_kind=kind, target=to, owner=frm, file=step.get("file"), line=step.get("line"), src=src,
                  operation=step.get("operation"))
    if kind == "ACCESSES_DATA":
        if step.get("operation") == "write":
            return _rule(n, sir_id, statement=f"Persists changes to {target}", classification="State Mutation",
                         kind="deterministic_business_rule", trust=DETERMINISTIC_CORE, **common)
        return _rule(n, sir_id, statement=f"Reads {target}", classification="Data Retrieval",
                     kind="deterministic_business_rule", trust=APPLICATION_LOGIC, **common)
    if kind == "INVOKES_EXTERNAL":
        return _rule(n, sir_id, statement=f"Calls external dependency {target}",
                     classification="External Integration", kind="deterministic_business_rule",
                     trust=DETERMINISTIC_CORE, **common)
    if kind == "CALLS":
        if _PLUMBING.search(to):
            return _rule(n, sir_id, statement=f"Infrastructure call {_short(to)}", classification="Legacy Plumbing",
                         kind="legacy_plumbing_pruned", trust=PRUNED, **common)
        owner = to.rpartition(".")[0].rsplit(".", 1)[-1]
        return _rule(n, sir_id, statement=f"Delegates to {owner}.{member}" if owner else f"Calls {member}",
                     classification="Orchestration", kind="deterministic_business_rule", trust=APPLICATION_LOGIC,
                     **common)
    return None


def _priority(rule: dict) -> int:
    if rule["kind"] == "legacy_plumbing_pruned":
        return 3
    return 0 if rule["trustBoundary"] == DETERMINISTIC_CORE else 1


def _branch_rules(sir_id: str, start_n: int, flow: dict, wf: dict | None, src: _Source,
                  limit: int = 4) -> tuple[list[dict], list[dict]]:
    """Guard / validation lines of the entry method body (if/throw/BadRequest...), plus its parameter list."""
    if not wf:
        return [], []
    entry = wf["entryPoint"]
    own = [s for s in wf["steps"] if s["from"] == entry and s.get("file")]
    file = own[0]["file"] if own else None
    lines = src.lines(file)
    loc = _locate_method(lines, entry.rsplit(".", 1)[-1], own[0]["line"] if own else None) if lines else None
    if not loc:
        return [], []
    start, end, params = loc
    rules: list[dict] = []
    for ln in range(start + 1, end):
        text = lines[ln - 1]
        if _BRANCH.match(text) and not text.strip().startswith("//"):
            rules.append(_rule(start_n + len(rules), sir_id, step_kind="BRANCH", target=entry, owner=entry,
                               file=file, line=ln, src=src, classification="Validation / Control Flow",
                               kind="deterministic_business_rule", trust=APPLICATION_LOGIC,
                               statement=f"Branches on: {text.strip().rstrip('{').strip()[:110]}"))
        if len(rules) >= limit:
            break
    return rules, _parse_params(params)


MAX_GUARD_CONDITIONS = 12


def _guard_rule(branch: list[dict]) -> list[dict]:
    """A method's if/throw/BadRequest lines are the conditions of ONE business rule (request validation),
    not a rule each: a branch is a decision point inside a behaviour, not a requirement of its own."""
    if not branch:
        return []
    conds = [b["statement"].removeprefix("Branches on: ") for b in branch]
    first = branch[0]
    return [{**first,
             "statement": ("Validates the request before processing: " + "; ".join(conds))[:300],
             "classification": "Validation / Control Flow",
             "conditions": conds,
             "conditionLines": [b["legacyLines"] for b in branch],
             "snippet": "\n".join(b["snippet"] for b in branch)[:800]}]


def _action_code(a: dict) -> str:
    """One business-logic action as a short, code-faithful phrase (the story step words it for people)."""
    t = a.get("type")
    if t == "set":
        return f"sets {a['target']} = {a['value']}"
    if t == "refuse":
        return f"refuses the request (error \"{a['error']}\")" if a.get("error") else "refuses the request"
    if t == "not-found":
        return "returns not found"
    if t == "throw":
        return f"throws \"{a['message']}\"" if a.get("message") else "throws an error"
    if t == "data":
        return f"{a['op']}s {a['entity']}"
    if t in ("notify", "call"):
        return f"calls {a['method']}({', '.join(a.get('args') or [])})"
    return t or ""


def _logic_rules(sir_id: str, logic: dict, owner: str) -> list[dict]:
    """The use case's business decisions as SIR rules: each anchored to the file and line of its first action."""
    out = []
    for r in logic["rules"]:
        when = " and ".join(
            "something fails" if p.get("catch") else
            f"for each {p['foreach']} in {p['code']}" if p.get("foreach") else
            ("not " if p.get("negated") else "") + str(p.get("code"))
            for p in r["when"])
        then = "; ".join(_action_code(a) for a in r["then"])
        classification = ("Error Handling" if any(p.get("catch") for p in r["when"]) else
                          "Business Decision" if r["when"] else "Business Value")
        out.append({
            "ruleId": f"{sir_id}.R0", "statement": (f"When {when}: {then}" if when else then)[:300],
            "classification": classification, "kind": "deterministic_business_rule",
            "astNode": f"AST:{_short(owner, 1)}.{r['method']}:L{r['line']}:DECIDES",
            "legacyLines": f"{r['file']}#L{r['line']}", "snippet": "\n".join(r["snippets"])[:800],
            "trustBoundary": DETERMINISTIC_CORE, "source": "deterministic", "_target": f"{owner}.{r['method']}",
            "logic": {"method": r["method"], "when": r["when"], "then": r["then"]},
        })
    return out


def _workflow_contract(sir_id: str, flow: dict, wf: dict | None, src: _Source, label: dict[str, str],
                       node_label: dict[str, str]) -> dict:
    steps = (wf or {}).get("steps", [])
    seen, rules = set(), []
    for step in steps:
        key = (step["kind"], step["to"], step.get("line"))
        if key in seen:
            continue
        seen.add(key)
        r = _step_rule(0, sir_id, step, src, label)
        if r:
            rules.append(r)
    rules.sort(key=_priority)  # stable: keeps source order within a class
    rules = rules[:MAX_RULES]
    branch, inputs = _branch_rules(sir_id, 0, flow, wf, src, limit=MAX_GUARD_CONDITIONS)
    # C#: the full business logic (every decision with its outcome, across the helpers it calls) replaces the
    # bare list of the entry method's `if` lines. Other languages keep the condition list.
    logic = None
    if wf and wf.get("entryPoint"):
        try:
            logic = business_logic.analyse(wf["entryPoint"], steps, src.lines)
        except Exception:   # analysis must never take SIR generation down
            logger.exception("business-logic analysis failed for %s", wf.get("entryPoint"))
            logic = None
    if logic:
        rules = _logic_rules(sir_id, logic, wf["entryPoint"].rsplit(".", 1)[0]) + rules
    else:
        rules = (_guard_rule(branch) + rules)[:MAX_RULES + 1]
    for i, r in enumerate(rules, 1):
        r["ruleId"] = f"{sir_id}.R{i}"
    reads, writes = flow["tablesRead"], flow["tablesWritten"]
    ent = lambda ids: [label.get(t, t.rsplit(".", 1)[-1]) for t in ids]  # noqa: E731
    states = ["RECEIVE_REQUEST"]
    for step in steps:
        if step["from"] != flow["entryPoint"]:
            continue
        name = step["to"].rsplit(".", 1)[-1]
        if name in {"ctor", "cctor"}:
            continue
        if step["kind"] == "ACCESSES_DATA":
            s = f"{'WRITE' if step.get('operation') == 'write' else 'READ'}_{_snake(label.get(step['to'], name))}"
        elif step["kind"] == "INVOKES_EXTERNAL":
            s = f"CALL_EXTERNAL_{_snake(name)}"
        elif _PLUMBING.search(step["to"]):
            continue
        else:
            s = f"CALL_{_snake(name)}"
        if s not in states:
            states.append(s)
    states = states[:9] + ["COMPLETE"]
    side = [f"Persists changes to {e}" for e in ent(writes)]
    side += [f"Publishes event {e.rsplit('.', 1)[-1]}" for e in (wf or {}).get("events", [])]
    side += [f"Invokes external dependency {node_label.get(x, x.rsplit('.', 1)[-1])}" for x in flow.get("externals", [])]
    trig = (wf or {}).get("trigger") or {}
    return {
        "name": scope_modules.use_case_name(flow),
        "summary": (f"{flow['entryLabel']}: reads {', '.join(ent(reads)) or 'nothing'}; "
                    f"writes {', '.join(ent(writes)) or 'nothing'}."),
        "inputs": inputs or ([{"name": f"{trig['verb']} {trig['url']}", "type": "HttpRequest", "required": True}]
                             if trig else []),
        "rules": rules,
        "stateMachine": " -> ".join(states),
        "sideEffects": side or ["No persistent side effects detected (read-only flow)"],
        "integrations": [f"INT-{node_label.get(x, x.rsplit('.', 1)[-1])}" for x in flow.get("externals", [])],
        "trace": {"entryPoint": flow["entryPoint"], "evidence": flow.get("evidence")},
        # what the decision rules refer to: local variables (per method) and helper summaries (when they fail)
        **({"businessLogic": {"entry": logic["entry"], "aliases": logic["aliases"], "helpers": logic["helpers"]}}
           if logic else {}),
    }


def _anchor_contracts(cap_id: str, applied: dict, src: _Source, inv_paths: dict[str, str], budget: int) -> list[dict]:
    """Modules with no traced use cases: one contract per code/entity node that has operational edges."""
    nodes = {n["id"]: n for n in applied.get("nodes", [])}
    by_source: dict[str, list[dict]] = {}
    for e in applied.get("edges", []):
        s = nodes.get(e["source"])
        if s and s.get("capability") == cap_id and e.get("kind") in _OPERATIONAL_EDGES:
            by_source.setdefault(e["source"], []).append(e)
    out = []
    for sid, edges in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
        node = nodes[sid]
        label = str(node.get("label", sid)).split("\n")[0]
        file = node.get("file") or node.get("path") or inv_paths.get(sid.upper())
        rules = []
        for e in edges[:MAX_RULES]:
            tgt = nodes.get(e["target"], {})
            tlabel = str(tgt.get("label", e["target"])).split("\n")[0]
            line = e.get("line") or src.find_token(file, tlabel) or src.find_token(file, e["target"])
            efile = e.get("file") or file
            kind = e["kind"]
            statement = {"READS": f"Reads {tlabel}", "WRITES": f"Writes {tlabel}", "ACCESSES_DATA": f"Accesses {tlabel}",
                         "REFERENCES": f"{label} references {tlabel}", "MAPS_TO": f"{label} maps to {tlabel}",
                         "INVOKES_EXTERNAL": f"Calls external dependency {tlabel}"}.get(kind, f"Calls {tlabel}")
            rules.append({
                "ruleId": "", "statement": statement,
                "classification": {"REFERENCES": "Referential Integrity", "MAPS_TO": "Referential Integrity",
                                   "READS": "Data Retrieval", "WRITES": "State Mutation",
                                   "ACCESSES_DATA": "Data Access", "INVOKES_EXTERNAL": "External Integration",
                                   }.get(kind, "Orchestration"),
                "kind": "deterministic_business_rule",
                "astNode": f"AST:{label}:L{line or 0}:{kind}",
                "legacyLines": f"{efile}#L{line}" if efile and line else (efile or ""),
                "snippet": src.snippet(efile, line),
                "trustBoundary": DETERMINISTIC_CORE if kind in {"WRITES", "INVOKES_EXTERNAL"} else APPLICATION_LOGIC,
                "source": "deterministic", "_target": e["target"],
            })
        written = [r["_target"] for r, e in zip(rules, edges) if e["kind"] == "WRITES"]
        out.append({
            "name": f"Maintain {label}" if node.get("type") in {"entity", "table"} else label,
            "summary": f"{label} and its {len(rules)} operational relationship(s) in the module.",
            "inputs": [], "rules": rules, "stateMachine": f"RECEIVE_REQUEST -> PROCESS_{_snake(label)} -> COMPLETE",
            "sideEffects": [f"Writes {nodes.get(t, {}).get('label', t)}" for t in written]
                           or ["No persistent side effects detected"],
            "integrations": [], "trace": {"entryPoint": sid, "evidence": None},
        })
        if len(out) >= budget:
            break
    return out


# --------------------------------------------------------------------------- LLM semantic lifting

_SYSTEM = (
    "You perform semantic lifting for a legacy-modernization Semantic Intermediate Representation (SIR). "
    "You receive bounded AST/AKG nodes for one use case: the entry point, the data it reads/writes, and for each "
    "rule the exact source evidence (file, line, snippet). Write business-language wording ONLY from that "
    "evidence. Never invent behaviour, numbers, entities or conditions; copy literals exactly. If a snippet is "
    "empty or ambiguous, say 'Behaviour not determinable from the AST evidence' instead of guessing. You do NOT "
    "produce file names, line numbers, snippets or ids. Reply with JSON only."
)

_USER = (
    "For each contract return an object in a JSON array:\n"
    '{"id": <contract id>, "name": <3-7 word business name>, "summary": <one sentence of business intent>, '
    '"stateMachine": <optional: states joined by " -> ", UPPER_SNAKE_CASE, 3-10 states>, '
    '"sideEffects": [<business-language side effects supported by the evidence>], '
    '"rules": [{"ref": <rule ref>, "statement": <one sentence, business meaning of that evidence>, '
    '"classification": <2-4 words, e.g. "Bounded Integrity Invariant", "Audited Financial Formula", '
    '"State Mutation", "Validation">, "kind": "deterministic_business_rule" | "legacy_plumbing_pruned"}]}\n'
    'Use "legacy_plumbing_pruned" only for infrastructure that a cloud framework would replace '
    "(logging, unit-of-work commit, object mapping).\n\nCONTRACTS:\n"
)


def _llm_view(c: dict) -> dict:
    return {"id": c["id"], "module": c["module"], "entryPoint": c["trace"]["entryPoint"], "inputs": c["inputs"],
            "sideEffectsFound": c["sideEffects"],
            "rules": [{"ref": r["ruleId"], "evidence": r["legacyLines"], "snippet": r["snippet"][:400],
                       "operation": r["astNode"].rsplit(":", 1)[-1], "target": r["_target"].rsplit(".", 1)[-1],
                       "currentStatement": r["statement"]} for r in c["rules"]]}


def _lift_chunk(chunk: list[dict]) -> tuple[dict[str, dict], str | None]:
    prompt = _USER + json.dumps([_llm_view(c) for c in chunk], indent=1)
    parsed, model = None, None
    for _ in range(2):  # one retry: the model endpoint can time out or throttle under parallel load
        parsed, model = ask_json(_SYSTEM, prompt, max_tokens=3800)
        if isinstance(parsed, list):
            break
    out: dict[str, dict] = {}
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and item.get("id"):
                out[str(item["id"])] = item
    return out, model


_STATE_RE = re.compile(r"^[A-Z][A-Z0-9_ ]{0,39}$")


def _text(v, limit: int) -> str | None:
    return v.strip()[:limit] if isinstance(v, str) and v.strip() else None


def _merge_llm(contract: dict, lifted: dict, model: str | None) -> int:
    """Accept wording fields only; trace fields (ids, lines, snippets, astNode) are never overwritten."""
    changed = 0
    if (v := _text(lifted.get("name"), 80)):
        contract["name"], changed = v, changed + 1
    if (v := _text(lifted.get("summary"), 300)):
        contract["summary"], changed = v, changed + 1
    states = [s.strip() for s in str(lifted.get("stateMachine") or "").split("->")]
    if 3 <= len(states) <= 12 and all(_STATE_RE.match(s) for s in states):
        contract["stateMachine"] = " -> ".join(states)
    fx = lifted.get("sideEffects")
    if isinstance(fx, list) and fx and all(isinstance(x, str) and x.strip() for x in fx):
        contract["sideEffects"] = [x.strip()[:200] for x in fx[:8]]
    by_ref = {r.get("ref"): r for r in (lifted.get("rules") or []) if isinstance(r, dict)}
    for rule in contract["rules"]:
        got = by_ref.get(rule["ruleId"])
        if not got:
            continue
        stmt = _text(got.get("statement"), 300)
        if stmt:
            rule["statement"], rule["source"] = stmt, "llm"
            changed += 1
        if (c := _text(got.get("classification"), 40)):
            rule["classification"] = c
        # Business logic stays business logic unless the LLM says it is plumbing AND the AST agrees it is a call.
        if got.get("kind") in KINDS and rule["astNode"].endswith(":CALLS"):
            rule["kind"] = got["kind"]
            rule["trustBoundary"] = PRUNED if got["kind"] == "legacy_plumbing_pruned" else rule["trustBoundary"]
    contract["origin"] = "llm" if changed else "deterministic"
    contract["model"] = model if changed else None
    return changed


# --------------------------------------------------------------------------- public API

def _existing_numbers(seed: dict) -> int:
    nums = [int(m.group(1)) for s in seed.get("semantic_ir", []) if (m := re.match(r"SIR-(\d+)$", str(s.get("id", ""))))]
    return max(nums, default=0)


def build_contracts(eng: dict, cap_id: str, *, use_llm: bool = True, source_dir: Path | None = None,
                    start_at: int = 1) -> tuple[list[dict], dict]:
    seed = eng["seed"]
    scope_modules.ensure_analysis(seed)
    applied = seed["applied_graph"]
    src = _Source(source_dir if source_dir is not None else store.engagement_dir(eng["id"]) / "source")
    nodes = applied.get("nodes", [])
    node_label = {n["id"]: str(n.get("label", n["id"])).split("\n")[0] for n in nodes}
    label = dict(node_label)
    wf_by_id = {w["id"]: w for w in (seed.get("dotnet_akg") or {}).get("codeWorkflows", [])}
    flows = scope_modules.flows_by_module(seed).get(cap_id, [])
    flows = sorted(flows, key=lambda f: (not f["isMutation"], -len(f["transactionBoundary"]), f["id"]))[:MAX_CONTRACTS]

    kernel_nodes = {k["nodeId"]: len(k.get("consumingCapabilities", [])) for k in applied.get("sharedKernels", [])}
    node_cap = {n["id"]: n.get("capability") for n in nodes}
    node_loc = {n["id"]: int(n.get("loc") or 0) for n in nodes}
    module_flows = scope_modules.flows_by_module(seed).get(cap_id, [])
    drafts: list[dict] = []
    for flow in flows:
        wf = wf_by_id.get(flow["id"].removeprefix("UC:"))
        draft = _workflow_contract("", flow, wf, src, label, node_label)
        draft["legacyAssessment"] = legacy_assessment.assess(
            flow, wf, src, module_flows=module_flows, kernel_nodes=kernel_nodes, node_cap=node_cap, cap_id=cap_id,
            node_loc=node_loc, externals=node_label)
        drafts.append(draft)
    basis = "use-case flows traced from entry points to data sinks"
    if not drafts:
        inv = scope_modules._inventory_index(eng)
        drafts = _anchor_contracts(cap_id, applied, src, inv, MAX_CONTRACTS)
        basis = "operational AKG relationships of the module's code and data assets (no traced entry-point flows)"

    contracts = []
    for i, d in enumerate(drafts):
        sir_id = f"SIR-{start_at + i:03d}"
        for j, r in enumerate(d["rules"], 1):
            r["ruleId"] = f"{sir_id}.R{j}"
        contracts.append({"id": sir_id, "module": cap_id, "origin": "deterministic", "model": None,
                          "generatedAt": _now(), **d})

    meta = {"basis": basis, "contracts": len(contracts), "llm": {"status": "skipped" if not use_llm else "unavailable",
                                                                   "model": None, "lifted": 0}}
    if use_llm and contracts:
        chunks = [contracts[i:i + LLM_CHUNK] for i in range(0, len(contracts), LLM_CHUNK)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(_lift_chunk, chunks))
        lifted_n, models = 0, set()
        for chunk, (got, model) in zip(chunks, results):
            for c in chunk:
                if c["id"] in got and _merge_llm(c, got[c["id"]], model):
                    lifted_n += 1
                    models.add(model)
        if lifted_n:
            meta["llm"] = {"status": "ok", "model": ", ".join(sorted(m for m in models if m)), "lifted": lifted_n}
    for c in contracts:
        for r in c["rules"]:
            r.pop("_target", None)
    return contracts, meta


def generate(eng: dict, *, use_llm: bool = True, force: bool = False) -> dict:
    """Ensure the scoped module has SIR contracts in seed.semantic_ir. Mutates + saves the engagement."""
    scope = eng.get("scope")
    if not scope:
        raise ValueError("Select a scope before generating the Semantic IR")
    cap_id = scope["capabilityId"]
    with _locks_guard:
        lock = _locks.setdefault(eng["id"], threading.Lock())
    with lock:
        fresh = store.load(eng["id"]) or eng   # another request may have just generated it
        seed = fresh.setdefault("seed", {})
        have = [s for s in seed.get("semantic_ir", []) if s.get("module") == cap_id]
        if have and not force:
            return fresh
        contracts, meta = build_contracts(fresh, cap_id, use_llm=use_llm, start_at=_existing_numbers(
            {"semantic_ir": [s for s in seed.get("semantic_ir", []) if s.get("module") != cap_id]}) + 1)
        seed["semantic_ir"] = [s for s in seed.get("semantic_ir", []) if s.get("module") != cap_id] + contracts
        fresh["sirMeta"] = {"capabilityId": cap_id, "generatedAt": _now(), **meta}
        # A regenerated SIR invalidates anything derived from the old one.
        fresh.pop("userStories", None)
        fresh.pop("testScenarios", None)
        return store.save(fresh)
