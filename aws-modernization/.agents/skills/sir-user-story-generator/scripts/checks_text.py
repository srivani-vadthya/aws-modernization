"""Turn the business logic of a legacy use case (from the SIR) into plain English.

The translation is structural: it says what the code literally tests or does, in words, and never guesses a meaning
the code does not state.

* Checks: `if (model.Particulars.Count > 1)` -> "there is more than 1 particular";
  `if (model.StatusName.ToLower() == "unpaid")` -> 'the status is "unpaid"'.
* Variables are named by what they hold: `var particularVAT = model.Particulars[1]` -> "the second particular (VAT)".
* A failing helper is explained by why it fails: `CreateNewInvoice(entity) == false`, where the helper fails when
  `CheckIfInvoiceNumberExists(entity)`, which queries `Invoices.Where(i => i.InvoiceNumber == entity.InvoiceNumber
  && ...)` -> "an invoice with the same invoice number and the same insurance provider already exists".
* Actions: values set ('the status is set to "Pending"'), refusals ('the request is refused with the error
  "InvoiceNumber"'), records added / updated / deleted, emails sent.
* Negation flips the operator (`==` <-> `!=`, `>` <-> `<=`, De Morgan for `&&` / `||`), so a negated check reads
  naturally ("the invoice has been saved before") instead of "not ...".

A condition the rules do not recognise is still shown, cleaned of code punctuation, never dropped.
Standard library only.
"""
from __future__ import annotations

import re

# variables that stand for the record the use case is about (the view model, the request model, the entity)
_SELF = {"model", "vm", "entity", "viewmodel", "this", "dto", "request", "input", "obj"}
_SUBMITTED = {"model", "dto", "request", "input"}   # what the user sent, as opposed to a record looked up
_CASE_FUNCS = re.compile(r"\.(?:ToLower|ToUpper|ToLowerInvariant|ToUpperInvariant|Trim)\(\)")
_PATH = r"[A-Za-z_]\w*(?:\[\d+\])?(?:\.[A-Za-z_]\w*(?:\[\d+\])?)*"
_NUM = r"-?\d+(?:\.\d+)?"
_OPS = {">": "more than", ">=": "at least", "<": "less than", "<=": "at most", "==": "", "!=": "not"}
_FLIP = {"==": "!=", "!=": "==", ">": "<=", "<=": ">", "<": ">=", ">=": "<"}
_ORDINAL = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]
_PREDICATE = re.compile(r"^(CheckIf|Check|Is|Has|Can|Exists|Validate|Should|Must|Contains)")
# words in a variable name that say nothing about the business ('soaEntity', 'tmpEntity' -> 'the SOA')
_NOISE_WORDS = {"item", "list", "entity", "entities", "tmp", "temp", "model", "vm", "obj", "data", "result", "new",
                "old", "current", "existing", "value", "dto", "record", "row", "the"}


class Ctx:
    """What the translator knows about a use case: variable meanings (per method) and helper summaries."""

    def __init__(self, noun: str, aliases: dict | None = None, helpers: dict | None = None,
                 method: str | None = None, entry: str | None = None, acronyms: set[str] | None = None):
        self.noun, self.helpers = noun, helpers or {}
        self.method, self.entry = method, entry
        self.acronyms = {a for a in (acronyms or set()) if a.isupper()}
        self._aliases = aliases or {}
        self.local: dict[str, str] = {}     # foreach variables in scope -> phrase

    def _info(self, var: str) -> dict | None:
        for m in (self.method, self.entry, *self._aliases):
            info = (self._aliases.get(m) or {}).get(var) if m else None
            if info:
                return info
        return None

    def phrase(self, var: str) -> str | None:
        if var in self.local:
            return self.local[var]
        info = self._info(var)
        return _alias_phrase(var, info, self) if info else None

    def query(self, var: str) -> dict | None:
        """{'entity', 'parts', 'single'} when the variable holds a query result (`.Where(...)`), else None."""
        info = self._info(var)
        return _query(str(info.get("code", "")), self) if info and ".Where(" in str(info.get("code", "")) else None

    def fix(self, text: str) -> str:
        """Known acronyms (e.g. the business area 'SOA') keep their capitals: 'the soa' -> 'the SOA'."""
        for a in self.acronyms:
            text = re.sub(rf"(?<![\"\w]){re.escape(a.lower())}(s?)(?![\"\w])", lambda m: a + m.group(1), text,
                          flags=re.I)
        return text


# --------------------------------------------------------------------------- words

def _tokens(ident: str) -> list[str]:
    """'particularVAT' -> ['particular', 'VAT']; 'ParticularTypeId' -> ['particular', 'type', 'id']."""
    raw = re.findall(r"[A-Z]{2,}(?=[A-Z][a-z]|\d|$|_)|[A-Z]?[a-z]+|[A-Z]|\d+", ident)
    return [t if len(t) > 1 and t.isupper() else t.lower() for t in raw]


def _words(ident: str) -> str:
    return " ".join(_tokens(ident))


def _singular(noun: str) -> str:
    if noun.endswith("ies"):
        return noun[:-3] + "y"
    if noun.endswith(("ses", "xes", "ches", "shes")):
        return noun[:-2]
    return noun[:-1] if noun.endswith("s") and not noun.endswith("ss") else noun


def _plural(noun: str) -> str:
    if noun.endswith("s"):
        return noun
    if noun.endswith("y") and noun[-2:-1] not in "aeiou":
        return noun[:-1] + "ies"
    return noun + ("es" if noun.endswith(("x", "ch", "sh")) else "s")


def _gerund(verb: str) -> str:
    v = verb.lower()
    if v.endswith("ie"):
        return v[:-2] + "ying"
    if v.endswith("e") and not v.endswith(("ee", "ye", "oe")):
        return v[:-1] + "ing"
    if len(v) <= 4 and re.fullmatch(r"[^aeiou]*[aeiou][^aeiouwxy]", v):
        return v + v[-1] + "ing"
    return v + "ing"


def _article(phrase: str) -> str:
    return f"{'an' if phrase[:1].lower() in 'aeiou' else 'a'} {phrase}"


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _entity_of(source: str) -> str:
    """The records a query reads: 'Uow.Invoices.GetAll() ' or 'Uow.Particulars.GetAll().Where(...).ToList()'
    -> 'invoice' / 'particular'."""
    m = re.search(r"\b(?:Uow|_?uow|_?db|_?dbContext|_?context|DataContext|_?unitOfWork)\.(\w+)", source) or \
        re.search(r"\b(\w+)\s*\.\s*(?:GetAll|Where|AsQueryable|Find|Query)\b", source)
    if m:
        return _singular(_words(m.group(1)))
    names = [s for s in re.findall(r"[A-Za-z_]\w*", source) if s not in ("GetAll", "AsQueryable", "Query", "Set")]
    return _singular(_words(names[-1])) if names else "record"


# --------------------------------------------------------------------------- queries

def _where_clauses(code: str) -> list[tuple[str, str]]:
    """(parameter, predicate) of every `.Where(x => ...)` in a query, in order."""
    out = []
    for m in re.finditer(r"\.Where\(\s*\(?(\w+)\)?\s*=>", code):
        depth, i = 1, m.end()
        while i < len(code) and depth:
            depth += {"(": 1, ")": -1}.get(code[i], 0)
            i += 1
        out.append((m.group(1), code[m.end():i - 1].strip()))
    return out


def _field(path: str) -> str:
    """'Status.Name' -> 'status'; 'Policy.ClientId' -> 'client'; 'Client.Id' -> 'client'; 'IssueDate' -> 'issue date'."""
    segs = [s for s in path.split(".") if s]
    last = segs[-1]
    if last in ("Id", "Name", "Code", "Value") and len(segs) > 1:
        return _words(segs[-2])
    return _words(_strip_suffix(last))


def _where_part(param: str, pred: str, ctx: "Ctx") -> str | None:
    """One filter of a query in words: 's.Status.Name.ToLower() == "unpaid"' -> 'status "unpaid"'."""
    p = _strip_parens(_CASE_FUNCS.sub("", pred))
    m = re.fullmatch(rf"{re.escape(param)}\.({_PATH})\s*(==|!=|<=|>=|<|>)\s*(.+)", p)
    if not m:
        return _plain(p.replace(f"{param}.", ""))
    left, op, right = m.group(1), m.group(2), m.group(3).strip()
    if left == "Id":                          # a look-up by id: 'the chosen record', not a business filter
        return None
    if op == "==" and re.fullmatch(r"(\w+)\.Id", right) and right.split(".")[0].lower() in _SELF:
        return f"@of the {ctx.noun}"          # p.InvoiceId == entity.Id: the records of this invoice
    field = _field(left)
    lit = re.fullmatch(r"\"([^\"]*)\"", right)
    if lit:
        return f"{field} \"{lit.group(1)}\"" if op == "==" else f"{field} other than \"{lit.group(1)}\""
    if re.fullmatch(_NUM, right):
        return f"{field} {_OPS[op] + ' ' if _OPS[op] else ''}{right}"
    if re.fullmatch(r"\w+", right) and ctx._info(right) and not ctx.query(right) and \
            re.match(r"DateTime\.", str(ctx._info(right).get("code", ""))):
        when = {"<": "before", "<=": "on or before", ">": "after", ">=": "on or after", "==": "on", "!=": "not on"}[op]
        return f"{field} {when} {_value(str(ctx._info(right)['code']), ctx)}"   # p.ExpiryDate <= expiryDate
    if re.fullmatch(_PATH, right):
        other = _subject(right, ctx)
        if "date" in field and op in ("<", "<=", ">", ">="):
            when = {"<": "before", "<=": "on or before", ">": "after", ">=": "on or after"}[op]
            return f"{field} {when} the {_field(right)} of {other['owner']}"
        if op == "==" and _field(right) == field:
            return f"the same {field} as {other['owner']}"
        return f"{field} {_OPS[op] + ' ' if _OPS[op] else 'equal to '}{other['text']}"
    return f"{field} {_OPS[op] or 'equal to'} {_plain(right)}"


def _query(code: str, ctx: "Ctx") -> dict:
    code = re.sub(r"\s+", " ", code)
    preds = [(prm, part) for prm, pred in _where_clauses(code) for part in _split_top(_strip_parens(pred), "&&")]
    by_id = any(re.fullmatch(rf"{re.escape(prm)}\.Id\s*==\s*.+", _strip_parens(p)) for prm, p in preds)
    parts = [x for x in (_where_part(prm, pred, ctx) for prm, pred in preds) if x]
    # .Select(p => p.Client) after the filters: the query returns clients, not policies (a list of ids stays a
    # list of the table's records)
    proj = [f for _, f in re.findall(r"\.Select\(\s*(\w+)\s*=>\s*\1\.([A-Z]\w*)\s*\)", code) if not f.endswith("Id")]
    entity = _singular(_words(proj[-1])) if proj else _entity_of(code)
    of = next((p[1:] for p in parts if p.startswith("@")), "")
    parts = [p for p in parts if not p.startswith("@")]
    return {"entity": entity, "parts": parts, "byId": by_id, "of": of,
            "single": bool(re.search(r"\.(First|Single|Last)\w*\(\)\s*$", code))}


def _q_text(q: dict, *, plural: bool) -> str:
    """'invoices of the SOA with status "unpaid"' (no article): the records a query returns, in words."""
    noun = _plural(q["entity"]) if plural else q["entity"]
    return f"{noun}{' ' + q['of'] if q.get('of') else ''}" + (f" with {_join(q['parts'])}" if q["parts"] else "")


# --------------------------------------------------------------------------- variables

def _alias_phrase(var: str, info: dict, ctx: Ctx) -> str:
    """What a local variable holds, in words, with the variable's own name as a hint when it adds meaning.
    A query result is named by its records ('the SOA'); its filters are spelled out where it is tested."""
    code = re.sub(r"\s+", " ", str(info.get("code", ""))).strip()
    if ".Where(" in code:
        q = _query(code, ctx)
        return f"the {q['entity'] if q['single'] else _plural(q['entity'])}"
    base = None
    m = re.fullmatch(rf"({_PATH})\[(\d+)\]", code)
    if m:
        coll = _subject(m.group(1), ctx)["member"] or _words(m.group(1).split(".")[-1])
        n = int(m.group(2))
        base = f"the {_ORDINAL[n] if n < len(_ORDINAL) else f'item {n + 1} of the'} {_singular(coll)}"
    m = m or re.fullmatch(rf"({_PATH})\.(First|FirstOrDefault|Last|LastOrDefault|Single|SingleOrDefault)\(\)", code)
    if base is None and m:
        coll = _subject(m.group(1), ctx)["member"] or _words(m.group(1).split(".")[-1])
        base = f"the {'last' if m.group(2).startswith('Last') else 'first'} {_singular(coll)}"
    if base is None:
        m = re.fullmatch(rf"({_PATH})\.GetById\(.*?\)(?:\.(\w+))?", code)
        if m:
            base = f"the {_words(re.sub(r'(?<=[a-z])(Id|Name)$', '', m.group(2)))}" if m.group(2) else \
                f"the {_entity_of(m.group(1))}"
    if base is None and re.search(r"\.Map<\w+>\(|new \w+\(", code):
        return f"the {ctx.noun}"
    if base is None:
        return f"the {_words(re.sub(r'(?<=[a-z])Url$', 'Link', var))}"
    extra = [t for t in _tokens(var) if t.lower() not in base.lower().split() and t.lower() not in _NOISE_WORDS]
    return f"{base} ({' '.join(extra)})" if extra and base else base


# --------------------------------------------------------------------------- subjects

def _indexed(seg: str) -> str:
    """'Policies[0]' -> 'first policy'; 'Status' -> 'status'."""
    m = re.fullmatch(r"(\w+)\[(\d+)\]", seg)
    if not m:
        return _words(seg)
    n = int(m.group(2))
    return f"{_ORDINAL[n] if n < len(_ORDINAL) else f'item {n + 1} of the'} {_singular(_words(m.group(1)))}"


def _subject(path: str, ctx: Ctx) -> dict:
    """What a code path refers to, in words. Returns {'text', 'self', 'id', 'owner', 'member', 'root'}."""
    noun = ctx.noun
    segs = path.split(".")
    root = segs[0]
    base = re.sub(r"\[\d+\]$", "", root)
    first_item = root.endswith("[0]")
    member = segs[-1] if len(segs) > 1 else ""
    is_id = bool(re.search(r"(?<=[a-z])Id$", member or root)) or (member or root).lower() == "id"
    alias = ctx.phrase(base) if base.lower() not in _SELF else None
    if alias:
        owner = alias
    elif base.lower() in _SELF:
        owner = f"the {noun}"
    elif first_item:
        owner = "the first item"
    elif base.lower() in ("item", "list", "items", "row"):
        owner = f"the {base.lower()}"
    elif base.lower() == "id":
        owner = "a record"
    else:
        name = re.sub(r"(?<=[a-z])Id$", "", base)
        owner = f"the {_words(name)}"
    common = {"self": base.lower() in _SELF, "id": is_id, "owner": owner, "root": base.lower(), "alias": bool(alias)}
    if not member:
        return {"text": owner, "member": "", **common}
    mem = _strip_suffix(member)
    middle = " ".join(_indexed(s) for s in segs[1:-1])
    member_words = " ".join(w for w in (middle, _words(mem)) if w)
    if (base.lower() in _SELF or first_item) and not alias:
        if middle and _indexed(segs[-2]) != _words(segs[-2]):     # vm.Policies[0].Premium
            text = f"the {middle}" if mem.lower() == "id" else f"the {_words(mem)} of the {middle}"
        else:
            text = f"the {member_words}"
    else:
        text = f"the {member_words} of {owner}"
    return {"text": text, "member": member_words, **common}


_LOOKUP_NAMES = ("Status", "Type", "State", "Category", "Role", "Kind", "Stage", "Level")


def _strip_suffix(member: str) -> str:
    """'PolicyId' -> 'Policy'; 'StatusName' -> 'Status' (a lookup's name is the lookup); 'ClientName' stays
    'ClientName' (a client's name is not the client)."""
    m = re.fullmatch(r"(\w*?[a-z0-9])(Id|Name)", member)
    if not m:
        return member
    if m.group(2) == "Id":
        return m.group(1)
    return m.group(1) if m.group(1).endswith(_LOOKUP_NAMES) else member


# --------------------------------------------------------------------------- expressions

def _split_top(expr: str, op: str) -> list[str]:
    """Split on a top-level operator ('||' or '&&'), respecting parentheses and quotes."""
    parts, depth, quote, start, i = [], 0, False, 0, 0
    while i < len(expr):
        ch = expr[i]
        if ch == '"':
            quote = not quote
        elif not quote and ch == "(":
            depth += 1
        elif not quote and ch == ")":
            depth -= 1
        elif not quote and depth == 0 and expr.startswith(op, i):
            parts.append(expr[start:i].strip())
            start = i + len(op)
            i += len(op)
            continue
        i += 1
    parts.append(expr[start:].strip())
    return parts


def _strip_parens(expr: str) -> str:
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")") and _balanced(expr[1:-1]):
        expr = expr[1:-1].strip()
    return expr


def _balanced(expr: str) -> bool:
    depth = 0
    for ch in expr:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth < 0:
            return False
    return depth == 0


def negate(expr: str) -> str:
    """The C# expression that is true exactly when `expr` is false (operators flipped, De Morgan)."""
    e = _strip_parens(expr)
    for op, other in (("||", "&&"), ("&&", "||")):
        parts = _split_top(e, op)
        if len(parts) > 1:
            return f" {other} ".join(f"({negate(p)})" for p in parts)
    m = re.fullmatch(r"!\s*(.+)", e)
    if m and (_balanced(m.group(1)) and (m.group(1).startswith("(") or re.fullmatch(rf"{_PATH}(\(.*\))?", m.group(1)))):
        return _strip_parens(m.group(1))
    m = re.fullmatch(r"(.+?)\s*==\s*(true|false)", e)
    if m:
        return f"{m.group(1)} == {'false' if m.group(2) == 'true' else 'true'}"
    m = re.fullmatch(r"(.+?)\s*(==|!=|>=|<=|>|<)\s*(.+)", e)
    if m and _balanced(m.group(1)) and _balanced(m.group(3)):
        return f"{m.group(1)} {_FLIP[m.group(2)]} {m.group(3)}"
    if re.fullmatch(_PATH, e) or _single_call(e):
        return f"!{e}"          # a flag or a call: '!x' is understood by the atoms
    return f"!({e})"


def _single_call(e: str) -> bool:
    """'CreateNewInvoice(entity)' -> True; 'Foo(a) + Bar(b)' -> False (the first '(' must close at the end)."""
    m = re.match(rf"{_PATH}\(", e)
    if not m:
        return False
    depth = 0
    for i in range(m.end() - 1, len(e)):
        depth += {"(": 1, ")": -1}.get(e[i], 0)
        if depth == 0:
            return i == len(e) - 1
    return False


def _helper_reason(name: str, args: str, fails: bool, ctx: Ctx) -> str | None:
    """Why helper `name` fails (or succeeds), from what the SIR recorded about it."""
    h = ctx.helpers.get(name)
    if not h:
        return None
    paths = h.get("failsWhen") or []
    if fails and paths and all(paths):
        reasons = [" and ".join(describe(p["code"] if not p.get("negated") else negate(p["code"]), ctx)
                                for p in path if p.get("code")) for path in paths]
        return " or ".join(r for r in reasons if r) or None
    if not fails and paths and all(paths):
        return " and ".join(describe(negate(p["code"]) if not p.get("negated") else p["code"], ctx)
                            for path in paths for p in path if p.get("code"))
    return None


def _query_phrase(name: str, ctx: Ctx, negated: bool) -> str | None:
    """A predicate helper explained by its query: 'an invoice with the same invoice number ... already exists'."""
    h = ctx.helpers.get(name) or {}
    where = (h.get("where") or [])
    if not where:
        return None
    q = where[0]
    entity = _entity_of(q.get("source", ""))
    parts = []
    for cond in _split_top(_strip_parens(q.get("predicate", "")), "&&"):
        m = re.fullmatch(rf"{re.escape(q.get('param', ''))}\.({_PATH})\s*==\s*({_PATH})", _strip_parens(cond))
        if m:
            left, right = m.group(1).split(".")[-1], m.group(2).split(".")[-1]
            field = _words(re.sub(r"(?<=[a-z])(Id|Name)$", "", left))
            parts.append(f"the same {field}" if left == right else f"{field} equal to {_subject(m.group(2), ctx)['text']}")
        else:
            parts.append(describe(cond, ctx))
    other = "another " if "Duplicate" in name else ""
    thing = f"{other}{entity}" if other else _article(entity)
    if negated:
        return f"no {'other ' if other else ''}{entity} with {_join(parts)} exists"
    return f"{thing} with {_join(parts)} already exists"


def _atom(expr: str, ctx: Ctx) -> str:
    noun = ctx.noun
    e = _strip_parens(_CASE_FUNCS.sub("", expr))
    if re.fullmatch(r"!\s*ModelState\.IsValid|ModelState\.IsValid\s*==\s*false", e):
        return "the entered details are not valid"
    if re.fullmatch(r"ModelState\.IsValid(\s*==\s*true)?", e):
        return "the entered details are valid"

    m = re.fullmatch(rf"(!)?\s*(\w+)\((.*)\)(\s*==\s*(true|false))?", e)
    if m and not m.group(2)[0].islower():          # a call to a business step: SaveModifications(entity)
        name = m.group(2)
        negative = bool(m.group(1)) != (m.group(5) == "false")
        if _PREDICATE.match(name):
            q = _query_phrase(name, ctx, negative)
            if q:
                return q
            words = _words(re.sub(r"^(CheckIf|Check|Is|Has|Can|Should|Must)", "", name))
            return f"{'it is not the case that ' if negative else ''}the {words}" if words else _plain(e)
        reason = _helper_reason(name, m.group(3), negative, ctx)
        if reason:
            return reason
        verb, *rest = _tokens(name) or [name]
        what = " ".join(rest)
        return f"{_gerund(verb)}{' the ' + what if what else ''} {'fails' if negative else 'succeeds'}"

    m = re.fullmatch(rf"({_PATH})\.Count(?:\(\))?\s*(>=|<=|==|!=|>|<)\s*(\d+)", e)
    q = ctx.query(m.group(1)) if m and re.fullmatch(r"\w+", m.group(1)) else None
    if q:                               # invoiceList.Count() == 0, where invoiceList is a query
        op, n = m.group(2), int(m.group(3))
        if (op in ("<=", "==") and n == 0) or (op == "<" and n == 1):
            return f"there are no {_q_text(q, plural=True)}"
        if (op == ">" and n == 0) or (op == ">=" and n == 1) or (op == "!=" and n == 0):
            return f"there is at least one {_q_text(q, plural=False)}"
        return f"the number of {_q_text(q, plural=True)} is {_OPS[op] + ' ' if _OPS[op] else ''}{n}"
    if m:
        s, op, n = _subject(m.group(1), ctx), m.group(2), int(m.group(3))
        items = s["member"] or s["owner"].removeprefix("the ")
        has = s["member"] and not s["self"]
        if (op in ("<=", "==") and n == 0) or (op == "<" and n == 1):
            return f"{s['owner']} has no {_plural(items)}" if has else f"there are no {_plural(items)}"
        if (op == ">" and n == 0) or (op == ">=" and n == 1) or (op == "!=" and n == 0):
            return f"{s['owner'] + ' has' if has else 'there is'} at least one {_singular(items)}"
        if op == "<=" and n == 1:
            return f"{s['owner'] + ' has' if has else 'there is'} at most one {_singular(items)}"
        noun_n = _singular(items) if n == 1 else _plural(items)
        who = f"{s['owner']} has" if has else ("there is" if n == 1 else "there are")
        return f"{who} {_OPS[op] + ' ' if _OPS[op] else ''}{n} {noun_n}".replace("  ", " ")

    m = re.fullmatch(rf"(!)?\s*({_PATH})\.HasValue(\s*==\s*(true|false))?", e)
    if m:
        missing = bool(m.group(1)) != (m.group(4) == "false")
        return _presence(_subject(m.group(2), ctx), missing, noun)

    m = re.fullmatch(rf"({_PATH})\s*(==|!=)\s*null", e)
    if m:
        q = ctx.query(m.group(1)) if re.fullmatch(r"\w+", m.group(1)) else None
        if q:                           # soa == null, where soa is the first record of a query
            if not q["parts"] and not q.get("of"):          # a plain look-up by id
                return f"the {q['entity']} is {'not ' if m.group(2) == '==' else ''}found"
            return f"there is no {_q_text(q, plural=False)}" if m.group(2) == "==" else \
                f"there is {_article(_q_text(q, plural=False))}"
        return _presence(_subject(m.group(1), ctx), m.group(2) == "==", noun)

    m = re.fullmatch(rf"({_PATH})\s*(==|!=)\s*\"([^\"]*)\"", e)
    if m:
        return f"{_subject(m.group(1), ctx)['text']} is {'not ' if m.group(2) == '!=' else ''}\"{m.group(3)}\""

    m = re.fullmatch(rf"({_PATH})\s*(==|!=)\s*\w+\.(\w+)", e)
    if m and m.group(3)[0].isupper():
        return (f"{_subject(m.group(1), ctx)['text']} is {'not ' if m.group(2) == '!=' else ''}"
                f"\"{_words(m.group(3)).capitalize()}\"")

    m = re.fullmatch(rf"({_PATH})\.Year\s*(<|>|<=|>=)\s*(\d{{4}})", e)
    if m:
        s = _subject(m.group(1), ctx)
        rel = {"<": "before", ">": "after", "<=": "in or before", ">=": "in or after"}[m.group(2)]
        return f"{s['text']} is {rel} {m.group(3)}"

    m = re.fullmatch(rf"({_PATH})\s*(>=|<=|==|!=|>|<)\s*({_NUM})", e)
    if m:
        s, op, n = _subject(m.group(1), ctx), m.group(2), m.group(3)
        if s["id"] and n == "0" and op in ("==", "!="):
            if s["member"] == "id":      # x.Id == 0: the record has never been saved
                who = f"the {noun}" if s["self"] and not s["alias"] else s["owner"]
                return f"{who} has not been saved yet" if op == "==" else f"{who} has been saved before"
            return f"{s['text']} is {'not set' if op == '==' else 'set'}"
        return f"{s['text']} is {_OPS[op] + ' ' if _OPS[op] else ''}{n}"

    m = re.fullmatch(rf"(!)?\s*({_PATH})(\s*==\s*(true|false))?", e)
    if m:
        negative = bool(m.group(1)) != (m.group(4) == "false")
        path = m.group(2)
        last = path.split(".")[-1]
        flag = re.match(r"(Is|Has|Can|Should|Was)([A-Z]\w*)", last)
        holder = _subject(".".join(path.split(".")[:-1]), ctx)["text"] if "." in path else f"the {noun}"
        if flag:
            return f"{holder} is {'not ' if negative else ''}marked \"{_words(flag.group(2))}\""
        return f"{_subject(path, ctx)['text']} is {'not ' if negative else ''}set"
    return _plain(e)


def _presence(s: dict, missing: bool, noun: str) -> str:
    if s["owner"] == "a record" and not s["member"]:
        return "no record is chosen" if missing else "a record is chosen"
    if s["id"]:
        what = s["text"].removeprefix("the ")
        what = re.sub(r"\s*\bid$", "", what).strip() or noun
        return f"no {what} is chosen" if missing else f"{_article(what)} is chosen"
    if s["self"] and not s["member"]:
        if s["root"] in _SUBMITTED:   # the submitted form itself
            return f"no {noun} details are given" if missing else f"the {noun} details are given"
        return f"the {noun} is not found" if missing else f"the {noun} is found"
    return f"{s['text']} is not available" if missing else f"{s['text']} is available"


def _plain(expr: str) -> str:
    """Fallback for a condition the rules do not recognise: code punctuation turned into words."""
    e = re.sub(r"[A-Za-z_]\w*", lambda m: _words(m.group(0)), expr)
    for code, text in (("==", " is "), ("!=", " is not "), (">=", " is at least "), ("<=", " is at most "),
                       (">", " is more than "), ("<", " is less than "), ("&&", " and "), ("||", " or "),
                       ("!", "not "), ("(", " "), (")", " "), (".", " ")):
        e = e.replace(code, text)
    return re.sub(r"\s+", " ", e).strip()


def _drop_redundant(atoms: list[str]) -> list[str]:
    """In 'policy != null && policy.Endorsements != null && policy.Endorsements.Count > 0' the null checks only
    guard the last test: keep the most specific condition on a path."""
    paths = [re.match(rf"\s*({_PATH})", a).group(1) if re.match(rf"\s*({_PATH})", a) else "" for a in atoms]
    keep = []
    for a, p in zip(atoms, paths):
        guard = re.fullmatch(rf"\s*{re.escape(p)}\s*!=\s*null\s*", a) if p else None
        if guard and any(q != p and q.startswith(p + ".") for q in paths):
            continue
        keep.append(a)
    return keep


def describe(expr: str, ctx: "Ctx | str") -> str:
    """One condition expression (no 'if') -> plain English. `ctx` is a Ctx, or just the business noun."""
    ctx = ctx if isinstance(ctx, Ctx) else Ctx(ctx)
    e = _strip_parens(_CASE_FUNCS.sub("", expr))
    m = re.fullmatch(r"!\s*\((.*)\)", e)
    if m and _balanced(m.group(1)):
        inner = _split_top(m.group(1), "||")
        eq = [re.fullmatch(rf"({_PATH})\s*==\s*(\".*?\"|{_NUM})", _strip_parens(x)) for x in inner]
        if len(inner) > 1 and all(eq) and len({x.group(1) for x in eq}) == 1:
            values = [x.group(2) for x in eq]
            subject = _subject(eq[0].group(1), ctx)["text"]
            return f"{subject} is neither {', '.join(values[:-1])} nor {values[-1]}"
        flipped = negate(m.group(1))
        if flipped.startswith("!(") or flipped == e:     # cannot be flipped: say so plainly, never loop
            return f"it is not the case that {describe(m.group(1), ctx)}"
        return describe(flipped, ctx)
    ors = _split_top(e, "||")
    if len(ors) > 1:
        # 'list == null || list.Count <= 0' -> 'the list is empty'
        subjects = {re.sub(r"\.Count$", "", re.match(rf"\s*({_PATH})", x).group(1))
                    for x in ors if re.match(rf"\s*({_PATH})", x)}
        if len(ors) == 2 and len(subjects) == 1 and re.search(r"==\s*null", ors[0]) and ".Count" in ors[1]:
            return f"{_subject(subjects.pop(), ctx)['text']} is empty"
        return " or ".join(describe(x, ctx) for x in ors)
    ands = _split_top(e, "&&")
    if len(ands) > 1:
        # '(x != null) && (x.Count > 0)', e.g. from a negated 'x == null || x.Count <= 0' -> 'x is not empty'
        subjects = {re.sub(r"\.Count$", "", re.match(rf"\s*\(?\s*({_PATH})", x).group(1))
                    for x in ands if re.match(rf"\s*\(?\s*({_PATH})", x)}
        if len(ands) == 2 and len(subjects) == 1 and re.search(r"!=\s*null", ands[0]) and ".Count" in ands[1]:
            return f"{_subject(subjects.pop(), ctx)['text']} is not empty"
        return " and ".join(describe(x, ctx) for x in _drop_redundant([_strip_parens(a) for a in ands]))
    return _atom(e, ctx)


def outcome(line: str) -> str | None:
    """What a failed check does, in words: 'throw new Exception("Too big")' -> 'the message "Too big" is shown'."""
    t = line.strip().rstrip(";")
    if t.startswith("throw"):
        msg = re.search(r"\"([^\"]+)\"", t)
        return f"the message \"{msg.group(1)}\" is shown" if msg else "an error is shown"
    if t.startswith("return"):
        if "NotFound" in t:
            return "a \"not found\" page is shown"
        if "BadRequest" in t or "Unauthorized" in t or "Forbid" in t:
            return "the request is refused"
        msg = re.search(r"\"([^\"]+)\"", t)
        return f"the message \"{msg.group(1)}\" is shown" if msg else None
    return None


def checks(conditions: list[str], noun: str) -> list[dict]:
    """[{'code', 'text', 'outcome'}] for each distinct check, in order. 'switch (x)' becomes 'the x decides what
    happens'; a following throw/return becomes the outcome of the check before it."""
    ctx = Ctx(noun)
    out: list[dict] = []
    seen: set[str] = set()
    for raw in conditions:
        line = re.sub(r"\s*//.*$", "", str(raw)).strip()
        result = outcome(line)
        if line.startswith(("throw", "return")):
            if out and result and not out[-1]["outcome"]:
                out[-1]["outcome"] = result
            continue
        m = re.fullmatch(r"(?:else\s+)?if\s*\((.*)\)\s*\{?", line) or re.fullmatch(r"(.*)", line)
        expr = m.group(1).strip()
        sw = re.fullmatch(r"switch\s*\((.*)\)\s*\{?", line)
        key = re.sub(r"\s+", "", sw.group(1) if sw else expr)
        if key in seen:
            continue
        seen.add(key)
        if sw:
            text = f"{_subject(_CASE_FUNCS.sub('', sw.group(1).strip()), ctx)['text']} decides what happens"
        else:
            text = describe(expr, ctx)
        out.append({"code": str(raw).strip(), "text": text, "outcome": None})
    return out


# --------------------------------------------------------------------------- business logic rules

_GENERIC_COLLECTIONS = {"list", "items", "item", "collection", "array", "set", "results", "result", "rows", "row",
                        "entries", "values", "data", "records", "models", "model"}


def _split_plus(code: str) -> list[str]:
    """Top-level '+' operands of a string concatenation, respecting quotes and parentheses."""
    parts, depth, quote, cur = [], 0, False, ""
    for ch in code:
        if ch == '"':
            quote = not quote
        elif not quote and ch in "([":
            depth += 1
        elif not quote and ch in ")]":
            depth -= 1
        if ch == "+" and not quote and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    parts.append(cur.strip())
    return parts


def _value(code: str, ctx: Ctx) -> str:
    """The value a field is set to, in words: 'GetInvoiceStatusId("Pending")' -> '"Pending"'."""
    c = re.sub(r"\s+", " ", code.strip())
    m = re.fullmatch(r"new\s+DateTime\(\s*(\d{4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})[^)]*\)", c)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{d} {_MONTHS[mo - 1]} {y}" if 1 <= mo <= 12 else c
    if re.fullmatch(r"DateTime\.(Now|UtcNow)", c):
        return "the current date and time"
    if c == "DateTime.Today":
        return "today's date"
    m = re.fullmatch(r"DateTime\.(?:Now|Today|UtcNow)\.Add(Days|Months|Years|Hours)\((.+)\)", c)
    if m:
        amount = m.group(2).strip()
        unit = m.group(1).lower()
        if amount == "1":
            return f"today plus 1 {unit[:-1]}"
        if re.fullmatch(_NUM, amount):
            return f"today plus {amount} {unit}"
        setting = _words(amount.split(".")[-1])        # DataContext.ExpiringPolicyDays: a configured number of days
        return f"today plus the {setting} setting" + ("" if unit in setting.split() else f" ({unit})")
    m = re.fullmatch(rf"(.+?)\.Select\(\s*(\w+)\s*=>\s*\2\.(\w+)\s*\)\s*\.(Sum|Count|Max|Min|Average)\(\)", c) or \
        re.fullmatch(rf"(.+?)\.(?P<agg>Sum|Max|Min|Average)\(\s*(\w+)\s*=>\s*\3\.(\w+)\s*\)", c)
    if m:   # invoiceList.Select(i => i.TotalAmountDue).Sum() -> 'the total of the total amount due of the invoices ...'
        src, field, agg = (m.group(1), m.group(3), m.group(4)) if "agg" not in m.groupdict() else \
            (m.group(1), m.group(4), m.group("agg"))
        word = {"Sum": "total", "Count": "number", "Max": "highest", "Min": "lowest", "Average": "average"}[agg]
        return f"the {word} of the {_words(field)} of {_records_of(src, ctx)}"
    m = re.search(r"\.(OrderByDescending|OrderBy)\(\s*(\w+)\s*=>\s*\2\.(\w+)\s*\)", c)
    if m:   # policy.Endorsements.OrderByDescending(e => e.EffectiveDate)...EndorsementNumber
        coll = c[:m.start()]
        tail = re.findall(r"\.Select\(\s*\w+\s*=>\s*\w+\.(\w+)\s*\)|\)\s*\.(\w+)\s*$", c[m.end():])
        field = next((a or b for a, b in tail if (a or b)), "")
        s = _subject(coll, ctx)
        which = "latest" if m.group(1) == "OrderByDescending" else "earliest"
        what = f"the {which} {_singular(s['member'] or s['text'].removeprefix('the '))}"
        what += f" of {s['owner']}" if s["member"] and not s["self"] else ""
        return (f"the {_words(field)} of {what}" if field else what) + f" (by {_words(m.group(3))})"
    if re.fullmatch(r"new\s+(?:List|HashSet|Collection)<\s*\w+\s*>\(\)", c):
        return "an empty list"
    if ".Where(" in c and not re.fullmatch(r"\w+", c):    # an inline query
        q = _query(c, ctx)
        if not q["parts"] and not q.get("of") and q["byId"]:
            return f"the chosen {q['entity']}"
        return f"the {_q_text(q, plural=not q['single'])}"
    m = re.fullmatch(r"(?:[A-Za-z_]\w*\.)+(?:Get)?([A-Z]\w*)\(\s*\)", c)
    if m:   # ListProviderSvc.GetClientsWithPoliciesSimpleList() -> 'the clients with policies simple list'
        return f"the {_words(m.group(1))}"
    if re.fullmatch(r"\w+", c) and ctx.query(c):         # a field filled from a query: say which records
        q = ctx.query(c)
        return f"the {_q_text(q, plural=not q['single'])}"
    if re.fullmatch(r"\w+", c) and ctx._info(c):          # a local holding a computed value
        return _value(str(ctx._info(c).get("code", "")), ctx) if ctx._info(c).get("code") != c else _plain(c)
    lits = re.findall(r"\"([^\"]*)\"", c)
    if len(lits) == 1 and re.fullmatch(r"[\w.]*\(\s*\"[^\"]*\"\s*\)|\"[^\"]*\"", c):
        return f"\"{lits[0]}\""
    m = re.fullmatch(r"\w+Enum\.(\w+)", c)
    if m:
        return f"\"{_words(m.group(1)).capitalize()}\""
    if re.fullmatch(_NUM, c) or c in ("true", "false", "null"):
        return {"null": "empty"}.get(c, c)
    parts = _split_plus(c)
    if len(parts) > 1 and any(re.fullmatch(r"\"[^\"]*\"", p) for p in parts):
        # 'item.LastName + ", " + item.FirstName' -> '"<last name>, <first name>"'
        shown = "".join(p[1:-1] if re.fullmatch(r"\"[^\"]*\"", p) else
                        f"<{_words(p.split('.')[-1]) if re.fullmatch(_PATH, p) else _plain(p)}>" for p in parts)
        return f"\"{shown}\""
    if re.fullmatch(_PATH, c):
        return _subject(c, ctx)["text"]
    if lits:
        return " and ".join(f"\"{x}\"" for x in lits)
    return _plain(c)


def _records_of(src: str, ctx: Ctx) -> str:
    """The records an aggregate runs over: a query variable spelled out with its filters, or a path in words."""
    src = src.strip()
    if re.fullmatch(r"\w+", src) and ctx.query(src):
        return f"the {_q_text(ctx.query(src), plural=True)}"
    if ".Where(" in src:
        return f"the {_q_text(_query(src, ctx), plural=True)}"
    return _subject(src, ctx)["text"] if re.fullmatch(_PATH, src) else _plain(src)


def _thing(var: str, entity: str, ctx: Ctx) -> str:
    if var:
        root = var.split(".")[0]
        if root in ctx.local:
            return ctx.local[root]
        if root.lower() in _SELF:
            return f"the {ctx.noun}"
        p = ctx.phrase(root)
        if p:
            return p
    return f"the {_singular(_words(entity))}"


def _action(a: dict, ctx: Ctx) -> str | None:
    t = a.get("type")
    if t == "set":
        target = _CASE_FUNCS.sub("", a["target"])
        last = target.split(".")[-1]
        flag = re.match(r"(Is|Has|Can|Should|Was)([A-Z]\w*)$", last)
        if flag and a["value"].strip() in ("true", "false"):   # vm.IsReadOnly = true -> 'is marked "read only"'
            holder = _subject(".".join(target.split(".")[:-1]), ctx)["text"] if "." in target else f"the {ctx.noun}"
            return f"{holder} is {'' if a['value'].strip() == 'true' else 'not '}marked \"{_words(flag.group(2))}\""
        subject = _subject(target, ctx)
        last_word = (subject["member"] or subject["text"]).split(" ")[-1]
        plural = last_word.endswith("s") and not last_word.endswith(("ss", "us", "is"))   # 'the expiring policies'
        return f"{subject['text']} {'are' if plural else 'is'} set to {_value(a['value'], ctx)}"
    if t == "refuse":
        return f"the request is refused with the error \"{a['error']}\"" if a.get("error") else "the request is refused"
    if t == "not-found":
        return "a \"not found\" page is shown"
    if t == "throw":
        return f"the message \"{a['message']}\" is shown" if a.get("message") else "an error is raised"
    if t == "data":
        verb = {"add": "added", "update": "updated", "delete": "deleted"}[a["op"]]
        return f"{_thing((a.get('args') or [''])[0], a.get('entity', ''), ctx)} is {verb}"
    if t == "notify":
        words = _tokens(a.get("method", ""))
        what = " ".join(words[1:]) if words and words[0] in ("send", "notify", "email", "mail", "publish") else \
            " ".join(words)
        channel = "email" if re.search(r"mail|smtp", str(a.get("receiver", "")) + a.get("method", ""), re.I) or \
            words[:1] == ["send"] else "notification"
        args = [x for x in (a.get("args") or []) if x.split(".")[0].lower() not in _SELF]
        details = _join([(_subject(x, ctx)["text"] if "." in x else (ctx.phrase(x) or f"the {_words(x)}"))
                         for x in args])
        return f"a \"{what}\" {channel} is sent" + (f" with {details}" if details else "")
    if t == "call":
        return f"the \"{_words(a.get('method', ''))}\" step runs"
    return None


def _each(p: dict, rule: dict, ctx: Ctx) -> tuple[str, str]:
    """A foreach in words: ('each invoice with status "unpaid"', 'the invoice') or ('each particular of the
    invoice', 'the particular')."""
    coll_code = p.get("code", "")
    q = ctx.query(coll_code) if re.fullmatch(r"\w+", coll_code) else None
    if q and p.get("remaining"):
        # the records saved for this invoice minus the ones handled earlier ('pIdList.Remove(item.Id)')
        single = q["entity"]
        scope = f"each {single} already saved for the {ctx.noun} that is no longer in it"
    elif q:
        single = q["entity"]
        scope = f"each {_q_text(q, plural=False)}"
    else:
        alias_code = str((ctx._info(coll_code) or {}).get("code", "")) if re.fullmatch(r"\w+", coll_code) else ""
        if alias_code and re.search(r"\b(?:Uow|_?db|_?context|DataContext)\.", alias_code):
            single, rest = _entity_of(alias_code), ""
        else:
            s = _subject(coll_code, ctx)
            coll = s["member"] or s["text"].removeprefix("the ")
            single = _singular(coll.split(" of ")[0])
            rest = f" of {s['owner']}" if s["member"] and not s["self"] else (
                f" of the {ctx.noun}" if s["member"] else "")
        if single.lower() in _GENERIC_COLLECTIONS:
            single = "item"
        scope = (f"each {single} already saved for the {ctx.noun} that is no longer in it" if p.get("remaining")
                 else f"each {single}{rest}")
    return scope, f"the {single}"


def logic_rule(rule: dict, ctx: Ctx) -> dict:
    """One business-logic rule -> {'given': [conditions], 'then': [what happens]}. Conditions before a `foreach`
    describe the situation; the foreach and the conditions on its item say which records the actions apply to."""
    ctx.local = {}
    given, scope, item_conds, item = [], None, [], None
    for p in rule.get("when", []):
        if p.get("catch"):
            given.append("anything goes wrong")
        elif p.get("foreach"):
            scope, item = _each(p, rule, ctx)
            ctx.local[p["foreach"]] = item
        else:
            code = p.get("code", "")
            if p.get("default") is not None:
                text = (f"{_subject(code, ctx)['text']} is none of " + _join([_value(x, ctx) for x in p["default"]])
                        if p["default"] else None)
            else:
                text = describe(negate(code) if p.get("negated") else code, ctx)
            if not text:
                continue
            (item_conds if scope else given).append(text)
    then = [x for x in (_action(a, ctx) for a in rule.get("then", [])) if x]
    if scope and then:
        rel = [c.replace(item + " ", "", 1) if c.startswith(item + " ") else c for c in item_conds]
        who = f"{scope}{' that ' + ' and '.join(rel) if rel else ''}"
        if len(then) == 1 and then[0].startswith(f"{item} is "):        # 'each particular ... is added'
            then = [then[0].replace(f"{item} is ", f"{who} is ", 1)]
        else:                                                           # 'for each X: its status ..., it is updated'
            own = [re.sub(rf"\bthe ([\w ]+?) of {re.escape(item)}\b", r"its \1", t) for t in then]
            own = [re.sub(rf"^{re.escape(item)} is\b", "it is", t) for t in own]
            then = [f"for {who}, " + _join(own)]
    return {"given": [ctx.fix(g) for g in given], "then": [ctx.fix(t) for t in then]}
