"""Legacy-complexity assessment per SIR contract, derived from the AST/AKG and the source itself.

Estimating a legacy change is mostly about what surrounds the code: framework paradigm, coupling, data layer,
testability, integrations, security and unknowns. Each detector below looks for concrete evidence (file + line)
and contributes story-point uplift; anything the code cannot answer becomes a question for the team instead of a
guess. The result is attached to the SIR contract as `legacyAssessment`, so the (stdlib-only) story scripts can
use it without touching source code.
"""
from __future__ import annotations

import re

from . import scope_modules

MAX_UPLIFT = 3

_STATIC_SINGLETONS = re.compile(r"\b(HttpContext\.Current|ConfigurationManager|ConfigurationSettings|"
                                r"Session\[|ViewState\[|Application\[|DateTime\.(?:Now|UtcNow)|Thread\.CurrentPrincipal)")
_DIRECT_NEW = re.compile(r"\bnew\s+\w*(Service|Repository|Manager|Provider|Helper|Client|Context|UnitOfWork)\w*\s*\(")
_RAW_SQL = re.compile(r"\b(SqlCommand|SqlConnection|SqlDataAdapter|OleDbCommand|DataSet|DataTable|ExecuteSqlCommand|"
                      r"SqlQuery|FromSql|StoredProcedure|CommandType\.StoredProcedure|EXEC(?:UTE)?\s+\w+)\b")
_EF = re.compile(r"\b(DbContext|DbSet<|IDbSet<|ObjectContext|NHibernate|ISession)\b")
_MESSAGING = re.compile(r"\b(MessageQueue|MSMQ|ServiceReference|HttpClient|WebClient|HttpWebRequest|SmtpClient|"
                        r"ServiceContract|OperationContract|ChannelFactory|SoapHttpClientProtocol)\b")
_SECURITY = re.compile(r"(FormsAuthentication|Membership\.|Roles\.|WindowsIdentity|MD5|SHA1|TripleDES)")
_UNKNOWN = re.compile(r"\b(TODO|HACK|FIXME|XXX|WORKAROUND|DO NOT CHANGE)\b", re.I)
_THIRD_PARTY = re.compile(r"\b(Telerik|DevExpress|Infragistics|ComponentArt|Interop\.|ActiveX|COMException|"
                          r"DllImport)\b")
_WEBFORMS = re.compile(r"(System\.Web\.UI|ViewState|Page_Load|\.aspx|IsPostBack)")
_WCF = re.compile(r"(\[ServiceContract\]|System\.ServiceModel|\.svc\b)")
_WINFORMS = re.compile(r"System\.Windows\.Forms")
_GOD_CLASS_LOC = 600


def _first(pattern: re.Pattern, lines: list[str]) -> tuple[int, str] | None:
    for i, ln in enumerate(lines, 1):
        if ln.strip().startswith(("//", "*", "/*")):
            continue
        m = pattern.search(ln)
        if m:
            return i, m.group(0)
    return None


def assess(flow: dict, wf: dict | None, src, *, module_flows: list[dict], kernel_nodes: dict[str, int],
           node_cap: dict[str, str], cap_id: str, node_loc: dict[str, int], externals: dict[str, str]) -> dict:
    """-> {"factors": [...], "uplift": int, "regressionScope": [...], "definitionOfDone": [...], "paradigm": str}"""
    factors: list[dict] = []
    seen: set[tuple] = set()

    def add(category: str, finding: str, evidence: str, points: int, question: str | None = None) -> None:
        key = (category, finding)
        if key in seen:
            return
        seen.add(key)
        factors.append({"category": category, "finding": finding, "evidence": evidence, "points": points,
                        **({"question": question} if question else {})})

    steps = (wf or {}).get("steps", [])
    files = []
    for s in steps:
        if s.get("file") and s["file"] not in files:
            files.append(s["file"])
    files = files[:8]
    corpus = {f: src.lines(f) for f in files}

    # 1. framework / UI paradigm ------------------------------------------------------------------
    paradigm = "MVC / Web API"
    for f, lines in corpus.items():
        if f.lower().endswith((".aspx.cs", ".ascx.cs")) or _first(_WEBFORMS, lines):
            hit = _first(_WEBFORMS, lines)
            paradigm = "Web Forms"
            add("framework", "Web Forms code-behind: business logic tied to page lifecycle / ViewState",
                f"{f}#L{hit[0]}" if hit else f, 2,
                "Is the page lifecycle (ViewState, postbacks) relied on for behaviour that must be preserved?")
            break
        if (hit := _first(_WCF, lines)):
            paradigm = "WCF service"
            add("framework", "WCF service contract: consumers depend on the existing contract", f"{f}#L{hit[0]}", 2,
                "Which external clients consume this service contract, and can it change?")
            break
        if _first(_WINFORMS, lines):
            paradigm = "WinForms"
            add("framework", "WinForms event-handler logic", f, 2)
            break

    # 2. coupling & blast radius ----------------------------------------------------------------
    entry_file = next((s["file"] for s in steps if s["from"] == flow["entryPoint"] and s.get("file")), None)
    entry_type = flow["entryPoint"].rpartition(".")[0]
    if entry_type and node_loc.get(entry_type, 0) > _GOD_CLASS_LOC:
        add("coupling", f"Large class ({node_loc[entry_type]} LOC): a change can touch unrelated behaviour",
            entry_file or "", 1)
    platform_calls = {s["to"].rsplit(".", 1)[0].rsplit(".", 1)[-1] for s in steps
                      if s["kind"] == "CALLS" and node_cap.get(s["to"].rpartition(".")[0]) not in (None, cap_id)}
    if len(platform_calls) >= 3:
        add("coupling", f"Calls into {len(platform_calls)} classes outside this module "
                        f"({', '.join(sorted(platform_calls)[:3])})", entry_file or "", 1)
    if max((s.get("depth", 1) for s in steps), default=1) >= 3:
        add("coupling", "Deep call chain (3+ levels): wide blast radius for a change", entry_file or "", 1)

    # 3. data layer ---------------------------------------------------------------------------------
    for f, lines in corpus.items():
        if (hit := _first(_RAW_SQL, lines)):
            add("data", f"Raw ADO.NET / SQL / stored-procedure access ({hit[1]}): logic may live in the database",
                f"{f}#L{hit[0]}", 2,
                "Which stored procedures, views or triggers does this flow depend on? They are not visible in the C# code.")
            break
    if any(_first(_EF, lines) for lines in corpus.values()):
        add("data", "Entity Framework data access (schema coupled to the model)", "", 0)
    written_shared = [t for t in flow["tablesWritten"] if kernel_nodes.get(t, 0) > 1]
    if written_shared:
        names = ", ".join(t.rsplit(".", 1)[-1] for t in written_shared[:3])
        add("data", f"Writes data shared with {max(kernel_nodes[t] for t in written_shared) - 1}+ other modules "
                    f"({names}): schema changes ripple outward", "", 1,
            f"Do other applications share the {names} table(s)? A schema change would affect them.")

    # 4. testability ----------------------------------------------------------------------------------
    for f, lines in corpus.items():
        if (hit := _first(_STATIC_SINGLETONS, lines)):
            add("testability", f"Static singleton ({hit[1]}): needs refactoring before it can be unit tested",
                f"{f}#L{hit[0]}", 1)
            break
    for f, lines in corpus.items():
        if (hit := _first(_DIRECT_NEW, lines)):
            add("testability", "Dependencies created with `new` instead of injected: hard to isolate in tests",
                f"{f}#L{hit[0]}", 1)
            break
    add("testability", "No automated tests are linked to this flow: plan manual regression of adjacent workflows", "", 0,
        "Are QA environments seeded with realistic, anonymized data and an IIS/Windows configuration matching production?")

    # 5. integration & infrastructure --------------------------------------------------------------
    ext = [externals.get(x, x.rsplit(".", 1)[-1]) for x in flow.get("externals", [])]
    if ext:
        add("integration", f"Calls external dependencies: {', '.join(sorted(set(ext))[:4])}", "", min(2, len(set(ext))),
            "Do these dependencies have a test sandbox and a fixed contract?")
    for f, lines in corpus.items():
        if (hit := _first(_MESSAGING, lines)):
            add("integration", f"Messaging / service-client usage ({hit[1]})", f"{f}#L{hit[0]}", 1)
            break
    for f, lines in corpus.items():
        if (hit := _first(_THIRD_PARTY, lines)):
            add("integration", f"Third-party / COM component ({hit[1]}): may be unmaintained and hard to debug",
                f"{f}#L{hit[0]}", 1)
            break
    for f, lines in corpus.items():
        if (hit := _first(_SECURITY, lines)):
            add("security", f"Authentication / crypto code on the path ({hit[1]}): re-verify against modern standards",
                f"{f}#L{hit[0]}", 1)
            break

    # 6. unknowns -----------------------------------------------------------------------------------------
    for f, lines in corpus.items():
        if (hit := _first(_UNKNOWN, lines)):
            add("unknowns", f"Developer note in the code ({hit[1]}): undocumented intent", f"{f}#L{hit[0]}", 1,
                "Who still knows the intent behind these notes? Otherwise it must be reverse-engineered.")
            break
    if not (wf or {}).get("fullyTraced", True):
        add("unknowns", "Call chain is not fully traced by the AST: some behaviour is not visible here", "", 1,
            "Which behaviour behind the untraced calls must be preserved?")
    add("unknowns", "Business intent is inferred from code only; no specification is linked", "", 0,
        "Agree the Definition of Done: minimal surgical parity migration, or also clean up debt (interfaces, "
        "splitting the monolith) along the way?")

    # regression scope: other use cases in this module touching the same data -----------------------------
    mine = set(flow["tablesRead"]) | set(flow["tablesWritten"])
    adjacent = [scope_modules.use_case_name(f) for f in module_flows
                if f["id"] != flow["id"] and mine & (set(f["tablesRead"]) | set(f["tablesWritten"]))]
    uplift = min(MAX_UPLIFT, sum(f["points"] for f in factors))
    dod = ["Behaviour matches the legacy flow for the traced rules (parity run on the same inputs)"]
    if adjacent:
        dod.append(f"Adjacent workflows re-tested manually or by automation: {', '.join(adjacent[:5])}")
    if any(f["category"] == "data" and f["points"] for f in factors):
        dod.append("Database dependencies (stored procedures, views, triggers, shared tables) confirmed with the DBA")
    if any(f["category"] == "testability" and f["points"] for f in factors):
        dod.append("New code is unit-testable: dependencies injected, static state wrapped behind an interface")
    return {"paradigm": paradigm, "factors": factors, "uplift": uplift, "regressionScope": adjacent[:8],
            "definitionOfDone": dod}
