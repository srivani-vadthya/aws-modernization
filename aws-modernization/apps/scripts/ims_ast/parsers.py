"""
Language parsers for every legacy .NET architecture + TypeScript.

Supported:
  .cs          — ASP.NET MVC, Web API, EF6, WCF (.svc.cs), ASMX (.asmx.cs),
                 Web Forms code-behind (.aspx.cs / .ascx.cs), Global.asax.cs,
                 AssemblyInfo.cs, EF6 Migrations
  .vb          — VB.NET (Web Forms, class libraries, modules)
  .ts / .tsx   — React 18 TypeScript frontend
  web.config / app.config — XML configuration files
"""
from __future__ import annotations
import re
from pathlib import Path
from .models import AstFile, AstSymbol
from .maps import CAPABILITY_MAP, EXTERNAL_SERVICES

# ---------------------------------------------------------------------------
# Shared debt rules
# ---------------------------------------------------------------------------
CSHARP_DEBT_RULES: list[tuple[str, str]] = [
    (r"DateTime\.Now\b",          "Use DateTime.UtcNow or TimeProvider abstraction"),
    (r"\.Result\b|\.Wait\(\)",    "Blocking async call — use await instead"),
    (r"catch\s*\(\s*Exception\b", "Broad exception catch — narrow the exception type"),
    (r"new\s+HttpClient\s*\(",    "Instantiate HttpClient via IHttpClientFactory"),
    (r"Thread\.Sleep\(",          "Use Task.Delay in async context"),
    (r"\bDataContext\b",          "Legacy EF6 DataContext — migrate to EF Core DbContext"),
    (r"\bGenericRepository\b",    "Generic repository over DbContext — consider removing abstraction layer"),
    (r"\bObjectContext\b",        "Legacy EF4 ObjectContext — migrate to EF Core DbContext"),
    (r"\bDatabase\.SetInitializer", "EF6 database initializer — remove for EF Core"),
]

VB_DEBT_RULES: list[tuple[str, str]] = [
    (r"On Error (Resume Next|GoTo)", "Unstructured error handling — use Try/Catch"),
    (r"\bDataContext\b",             "Legacy EF6 DataContext — migrate to EF Core DbContext"),
    (r"DateTime\.Now\b",             "Use DateTime.UtcNow or TimeProvider abstraction"),
    (r"\.Result\b|\.Wait\(\)",       "Blocking async call — use Await instead"),
]

TS_DEBT_RULES: list[tuple[str, str]] = [
    (r"\bany\b",                   "Avoid 'any' — use explicit types"),
    (r"console\.(log|warn|error)", "Remove console statements before production"),
    (r"//\s*(TODO|FIXME)",         "Unresolved TODO/FIXME comment"),
    (r"useState<any>",             "Untyped useState — provide a generic type"),
]

# Legacy architecture markers (arch_flags)
ARCH_MARKERS: list[tuple[str, str]] = [
    (r"\bSystem\.Web\.UI\.Page\b",          "WebForms Page"),
    (r"\bSystem\.Web\.UI\.UserControl\b",   "WebForms UserControl"),
    (r"\bSystem\.Web\.Services\.WebService\b", "ASMX WebService"),
    (r"\bSystem\.ServiceModel\b",           "WCF ServiceModel"),
    (r"\[ServiceContract\]",                "WCF ServiceContract"),
    (r"\[OperationContract\]",              "WCF OperationContract"),
    (r"\bHttpApplication\b",                "Global.asax HttpApplication"),
    (r"\bDbMigration\b",                    "EF6 Migration"),
    (r"\bDbMigrationsConfiguration\b",      "EF6 MigrationsConfiguration"),
    (r"\[assembly:",                        "AssemblyInfo attribute"),
    (r"\bApiController\b",                  "ASP.NET Web API 2 ApiController"),
    (r"\bController\b",                     "ASP.NET MVC Controller"),
]


def _capability_for(name: str, fallback: str) -> str:
    return CAPABILITY_MAP.get(name, fallback)


def _arch_flags(src: str) -> list[str]:
    return [label for pattern, label in ARCH_MARKERS if re.search(pattern, src)]


def _external_calls(body: str) -> list[str]:
    return [svc_id for svc, svc_id in EXTERNAL_SERVICES.items() if re.search(svc, body, re.IGNORECASE)]


# ---------------------------------------------------------------------------
# C# parser — covers all .cs variants
# ---------------------------------------------------------------------------
_TYPE_RE = re.compile(
    r"^\s*(?:public|internal|protected|private)?\s*(?:abstract\s+|sealed\s+|static\s+|partial\s+)*"
    r"(class|interface|enum|record|struct)\s+(\w+)"
    r"(?:\s*:\s*([\w,\s<>?]+))?",
    re.MULTILINE,
)


def _lang_for_cs(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".aspx.cs") or name.endswith(".ascx.cs"):
        return "webforms"
    if name.endswith(".asmx.cs"):
        return "asmx"
    if name.endswith(".svc.cs"):
        return "wcf"
    if name == "global.asax.cs":
        return "global-asax"
    return "csharp"


def parse_csharp(path: Path, rel: str) -> AstFile:
    src  = path.read_text(encoding="utf-8", errors="ignore")
    lang = _lang_for_cs(path)
    cap  = _capability_for(path.stem, "unknown")
    af   = AstFile(path=rel, language=lang, capability=cap, loc=len(src.splitlines()))

    af.imports = re.findall(r"^using\s+([\w.]+);", src, re.MULTILINE)

    ns_m = re.search(r"namespace\s+([\w.]+)", src)
    ns   = ns_m.group(1) if ns_m else None

    file_arch = _arch_flags(src)

    for m in _TYPE_RE.finditer(src):
        kind    = m.group(1)
        name    = m.group(2)
        bases   = [b.strip() for b in m.group(3).split(",")] if m.group(3) else []
        lineno  = src[: m.start()].count("\n") + 1
        sym_cap = _capability_for(name, cap)

        sym = AstSymbol(
            kind=kind, name=name, file=rel, line=lineno,
            capability=sym_cap, namespace=ns, base_types=bases,
        )

        pre = src[max(0, m.start() - 300): m.start()]
        sym.decorators = re.findall(r"\[(\w+)", pre)

        body = src[m.end(): m.end() + 4096]
        sym.calls          = list(set(re.findall(r"(\w+)\s*\(", body)))[:30]
        sym.external_calls = _external_calls(body)
        sym.tech_debt_flags = [note for pat, note in CSHARP_DEBT_RULES if re.search(pat, body)]
        sym.arch_flags      = file_arch + _arch_flags(body)

        af.symbols.append(sym)

    return af


# ---------------------------------------------------------------------------
# VB.NET parser — Web Forms, class libraries, modules
# ---------------------------------------------------------------------------
_VB_TYPE_RE = re.compile(
    r"^\s*(?:Public|Friend|Protected|Private)?\s*(?:MustInherit\s+|NotInheritable\s+|Partial\s+)*"
    r"(Class|Interface|Enum|Structure|Module)\s+(\w+)"
    r"(?:\s+Inherits\s+([\w.]+))?",
    re.MULTILINE | re.IGNORECASE,
)


def parse_vb(path: Path, rel: str) -> AstFile:
    src  = path.read_text(encoding="utf-8", errors="ignore")
    lang = "webforms-vb" if path.name.lower().endswith(".aspx.vb") else "vb"
    cap  = _capability_for(path.stem, "unknown")
    af   = AstFile(path=rel, language=lang, capability=cap, loc=len(src.splitlines()))

    af.imports = re.findall(r"^Imports\s+([\w.]+)", src, re.MULTILINE | re.IGNORECASE)

    ns_m = re.search(r"Namespace\s+([\w.]+)", src, re.IGNORECASE)
    ns   = ns_m.group(1) if ns_m else None

    file_arch = _arch_flags(src)

    for m in _VB_TYPE_RE.finditer(src):
        kind   = m.group(1).lower()
        name   = m.group(2)
        bases  = [m.group(3).strip()] if m.group(3) else []
        lineno = src[: m.start()].count("\n") + 1

        sym = AstSymbol(
            kind=kind, name=name, file=rel, line=lineno,
            capability=_capability_for(name, cap), namespace=ns, base_types=bases,
        )

        body = src[m.end(): m.end() + 4096]
        sym.calls           = list(set(re.findall(r"(\w+)\s*\(", body)))[:30]
        sym.external_calls  = _external_calls(body)
        sym.tech_debt_flags = [note for pat, note in VB_DEBT_RULES if re.search(pat, body)]
        sym.arch_flags      = file_arch + _arch_flags(body)

        af.symbols.append(sym)

    return af


# ---------------------------------------------------------------------------
# Config parser — web.config / app.config
# ---------------------------------------------------------------------------
def parse_config(path: Path, rel: str) -> AstFile:
    src = path.read_text(encoding="utf-8", errors="ignore")
    af  = AstFile(path=rel, language="config", capability="ims-webmvc", loc=len(src.splitlines()))

    conn_strings = re.findall(r'connectionString\s*=\s*"([^"]+)"', src)
    for cs in conn_strings:
        sym = AstSymbol(kind="config", name="connectionString", file=rel, line=0, capability="ims-data")
        if re.search(r"(SqlClient|SQLOLEDB|System\.Data\.SqlClient)", cs, re.IGNORECASE):
            sym.arch_flags.append("SQL Server connection string")
        af.symbols.append(sym)

    if re.search(r"<system\.web>", src, re.IGNORECASE):
        af.symbols.append(AstSymbol(kind="config", name="system.web", file=rel, line=0,
                                    capability="ims-webmvc", arch_flags=["ASP.NET system.web config"]))
    if re.search(r"<system\.serviceModel>", src, re.IGNORECASE):
        af.symbols.append(AstSymbol(kind="config", name="system.serviceModel", file=rel, line=0,
                                    capability="ims-webmvc", arch_flags=["WCF system.serviceModel config"]))
    if re.search(r"<system\.webServer>", src, re.IGNORECASE):
        af.symbols.append(AstSymbol(kind="config", name="system.webServer", file=rel, line=0,
                                    capability="ims-webmvc", arch_flags=["IIS system.webServer config"]))

    return af


# ---------------------------------------------------------------------------
# TypeScript / TSX parser
# ---------------------------------------------------------------------------
def parse_typescript(path: Path, rel: str) -> AstFile:
    src = path.read_text(encoding="utf-8", errors="ignore")
    af  = AstFile(path=rel, language="typescript", capability="frontend", loc=len(src.splitlines()))

    af.imports = re.findall(r"^import\s+.+from\s+['\"](.+)['\"]", src, re.MULTILINE)

    for m in re.finditer(r"^(?:export\s+)?interface\s+(\w+)", src, re.MULTILINE):
        af.symbols.append(AstSymbol(
            kind="interface", name=m.group(1), file=rel,
            line=src[: m.start()].count("\n") + 1, capability="frontend",
        ))

    comp_re = re.compile(
        r"^(?:export\s+)?(?:default\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:\(|React\.FC))",
        re.MULTILINE,
    )
    for m in comp_re.finditer(src):
        name  = m.group(1) or m.group(2)
        lineno = src[: m.start()].count("\n") + 1
        sym   = AstSymbol(kind="component", name=name, file=rel, line=lineno, capability="frontend")

        body = src[m.end(): m.end() + 3000]
        sym.calls           = list(set(re.findall(r"(\w+)\s*\(", body)))[:20]
        sym.tech_debt_flags = [note for pat, note in TS_DEBT_RULES if re.search(pat, body)]

        af.symbols.append(sym)

    return af
