from __future__ import annotations

import json
import os
import re
import subprocess
import posixpath
import fnmatch
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import templates
from .dependencies import collect_dependencies
from .models import Artifact, COLLECTOR_VERSION, Finding, PackageRequest
from .repository import ContextError, canonical, digest, engagement_root, safe_child

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "bin", "obj", "dist", "target", ".vs", "packages"}
SECRET_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".keystore"}
SECRET_NAMES = {".npmrc", ".pypirc", "credentials", "id_rsa", "id_ed25519"}
SOURCE_SUFFIXES = {".cs", ".vb", ".fs", ".csproj", ".vbproj", ".fsproj", ".sln", ".config", ".json",
                   ".xml", ".props", ".targets", ".ts", ".tsx", ".js", ".jsx", ".css", ".less",
                   ".scss", ".html", ".cshtml", ".razor", ".proto", ".wsdl", ".xsd", ".graphql",
                   ".gql", ".sql", ".py", ".java", ".go", ".pubxml"}
BUILD_NAMES = {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "pom.xml", "build.gradle",
               "build.gradle.kts", "settings.gradle", "gradle.properties", "requirements.txt", "pyproject.toml",
               "poetry.lock", "go.mod", "go.sum", "cargo.toml", "cargo.lock", "dockerfile", "global.json",
               "nuget.config", "packages.config", "directory.build.props", "directory.build.targets",
               "tsconfig.json", "vite.config.ts", "webpack.config.js", "next.config.js", "next.config.ts",
               "next.config.mjs", "docker-compose.yml", "compose.yaml", "makefile", "cmakelists.txt"}
SECRET_TEXT = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
                         r"(?i:(?:password|api[_-]?key|client[_-]?secret|access[_-]?token|connectionstring)\s*[\"']?\s*[:=]\s*[\"']([^\"'\r\n]{6,}))")


@dataclass
class Collection:
    engagement: dict
    scope: dict
    target: dict
    source: dict
    files: dict[str, bytes] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    template_rows: list[dict] = field(default_factory=list)
    dependencies: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    inventory_rows: list[dict] = field(default_factory=list)
    fingerprint: str = ""
    consistency: str = ""

    def finding(self, code, message, artifact=None, severity="warning", evidence=None, action="Review the missing or uncertain evidence."):
        self.findings.append(Finding(code=code, severity=severity, message=message, artifactId=artifact,
                                     evidence=evidence or [], action=action))

    def add(self, artifact_id, kind, path, data, origin, role="context", provenance="unknown", evidence=None, approval=None, scan=True):
        if scan and SECRET_TEXT.search(data.decode("utf-8", errors="ignore")):
            self.finding("SENSITIVE_CONTENT_EXCLUDED", "Potential credentials were detected; content was not packaged.",
                         artifact_id, "blocker", [origin], "Sanitize the source artifact outside package generation and regenerate.")
            return
        self.files[path] = data
        self.artifacts.append(Artifact(id=artifact_id, kind=kind, path=path, origin=origin,
            sha256=digest(data), bytes=len(data), moduleId=self.scope["capabilityId"], role=role,
            provenance=provenance, evidence=evidence or [], approval=approval or {},
            modificationAllowed=role == "selected"))

    def snapshot(self, name, value, origin, provenance="unknown", approval=None):
        self.add(name, "snapshot", "snapshots/" + name + ".json", canonical(value), origin,
                 provenance=provenance, approval=approval)


def _walk(root: Path, skip_packages=False):
    if not root.exists():
        return
    if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
        return
    for p in sorted(root.iterdir()):
        if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
            yield p, "linked"
        elif p.is_dir():
            if p.name not in SKIP_DIRS and not (skip_packages and p.name == "module-context"):
                yield from _walk(p, skip_packages)
        elif p.is_file():
            yield p, None


def _secret_path(p: Path) -> bool:
    return p.name.lower().startswith(".env") or p.suffix.lower() in SECRET_SUFFIXES or p.name.lower() in SECRET_NAMES


def _approval(eng: dict, phase: str) -> dict:
    gate = eng.get("gates", {}).get(phase, {})
    return {**gate, "decision": gate.get("decision"), "actor": gate.get("actor"), "at": gate.get("at"),
            "binding": "phase-only-not-content-bound"}


def _repository_id(url):
    if not url:
        return None
    if "://" not in url:
        return str(url).split("@")[-1]  # drop SSH user info
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))


def _project_support(source_root, all_source, wanted, c):
    """Follow MSBuild project ownership and declared references without executing a build."""
    projects = [r for r in all_source if r.lower().endswith((".csproj", ".vbproj"))]
    selected = [r for r, (role, _) in wanted.items() if role == "selected"]
    queue = []
    for path in selected:
        owners = [p for p in projects if path.startswith(posixpath.dirname(p) + "/") or not posixpath.dirname(p)]
        if owners:
            queue.append(max(owners, key=lambda p: len(posixpath.dirname(p))))
    seen = set()
    while queue:
        project = queue.pop()
        if project in seen:
            continue
        seen.add(project)
        wanted.setdefault(project, ("build-support", ["owns selected/dependency source"]))
        parent = posixpath.dirname(project)
        try:
            tree = ET.fromstring(safe_child(source_root, project).read_bytes())
        except (ET.ParseError, OSError):
            c.finding("BUILD_MANIFEST_UNREADABLE", "Project references could not be inspected.", evidence=[project])
            continue
        if tree.get("Sdk"):
            for rel in all_source:
                if (not parent or rel.startswith(parent + "/")) and rel.endswith((".cs", ".vb", ".resx", ".razor", ".cshtml")):
                    wanted.setdefault(rel, ("dependency", [project + ": implicit SDK project input (conditions not evaluated)"]))
        for el in tree.iter():
            tag = el.tag.split("}")[-1]
            raw = el.get("Project") if tag == "Import" else el.get("Include")
            if tag not in {"ProjectReference", "Compile", "Content", "EmbeddedResource", "None", "Import"} or not raw:
                continue
            if "$" in raw or "%" in raw:
                c.finding("BUILD_REFERENCE_UNRESOLVED", "An MSBuild expression requires evaluation outside packaging.", evidence=[project, tag])
                continue
            # A literal Import guarded by Exists(...) is an optional build tool
            # integration. MSBuild deliberately skips it when absent, so it is
            # not an unavailable source artifact and must not block packaging.
            optional_import = tag == "Import" and "exists(" in (el.get("Condition") or "").lower()
            for part in raw.replace("\\", "/").split(";"):
                rel = posixpath.normpath(posixpath.join(parent, part))
                if rel.startswith("../") or rel.startswith("/") or ":" in rel:
                    c.finding("BUILD_REFERENCE_OUTSIDE_SOURCE", "A build input lies outside ingested source.", severity="blocker", evidence=[project])
                    continue
                matches = [p for p in all_source if fnmatch.fnmatchcase(p, rel)] if "*" in rel or "?" in rel else [rel]
                for match in matches:
                    if optional_import and match not in all_source:
                        c.finding("BUILD_REFERENCE_OPTIONAL_MISSING",
                                  "An optional MSBuild import is absent; its Exists condition prevents it from being loaded.",
                                  evidence=[project, match],
                                  action="Restore the optional build tool only if its legacy build behavior must be reproduced.")
                        continue
                    wanted.setdefault(match, ("dependency", [project + ": " + tag]))
                    if tag == "ProjectReference" and match in all_source:
                        queue.append(match)


def _source_references(value):
    """Only explicit source-reference fields, never arbitrary strings in prompts."""
    if isinstance(value, dict):
        for key, v in value.items():
            if key in {"file", "path", "legacyLines"} and isinstance(v, str):
                for part in v.split(", "):
                    yield re.split(r"#L|:\d+(?:-\d+)?$", part)[0].replace("\\", "/")
            elif key in {"traces", "conditionLines"} and isinstance(v, list):
                for line in v:
                    if isinstance(line, str):
                        yield re.split(r"#L|:\d+(?:-\d+)?$", line)[0].replace("\\", "/")
            else:
                yield from _source_references(v)
    elif isinstance(value, list):
        for v in value:
            yield from _source_references(v)


def _trace_source_path(raw: str, known_source: set[str]) -> tuple[str | None, bool]:
    """Resolve a trace reference without treating its explanatory text as a path.

    Existing discovery/SIR data sometimes records ``path (symbol detail)``.  A
    known repository path is accepted; unknown file-like paths remain source
    candidates so genuine missing-source blockers are retained.  Other trace
    text is evidence, not a filesystem path.
    """
    value = raw.strip().replace("\\", "/")
    if value in known_source:
        return value, True
    matches = [path for path in known_source if value.startswith(path) and
               (len(value) == len(path) or value[len(path)].isspace() or value[len(path)] in "([{")]
    if matches:
        return max(matches, key=len), True
    candidate = re.split(r"\s+\(", value, maxsplit=1)[0].strip()
    # File-like, repository-relative references still need a SOURCE_MISSING
    # finding when unavailable; do not silently discard them.
    if (candidate and "/" not in candidate[:1] and not re.match(r"^[A-Za-z]:", candidate)
            and ":" not in candidate and ".." not in Path(candidate).parts
            and Path(candidate).suffix.lower() in SOURCE_SUFFIXES):
        return candidate, False
    return None, False


def _generated_output_source(rel: str, all_source: dict[str, str]) -> str | None:
    """Return the checked-in authoring source for a missing generated web asset."""
    path = Path(rel)
    if path.suffix.lower() != ".css":
        return None
    stem = path.stem[:-4] if path.stem.lower().endswith(".min") else path.stem
    for suffix in (".less", ".scss"):
        candidate = path.with_name(stem + suffix).as_posix()
        if candidate in all_source:
            return candidate
    return None


def _is_deployment_profile(rel: str, evidence: list[str]) -> bool:
    return ("/publishprofiles/" in f"/{rel.lower()}" and rel.lower().endswith(".pubxml")
            and any(item.endswith(": Content") or item.endswith(": None") for item in evidence))


def collect(eid: str, request: PackageRequest) -> Collection:
    root = engagement_root(eid)
    raw = safe_child(root, "engagement.json").read_bytes()
    try:
        eng = json.loads(raw)
    except ValueError as exc:
        raise ContextError("Engagement JSON is invalid") from exc
    if eng.get("id") != eid:
        raise ContextError("Engagement identity mismatch")
    scope = eng.get("scope") or {}
    if scope.get("capabilityId") != request.moduleId:
        raise ContextError("Requested module must match the currently selected scope")
    seed = eng.get("seed") or {}
    source_root = safe_child(root, "source")
    c = Collection(eng, scope, seed.get("target") or {}, {})
    approvals = {p: _approval(eng, p) for p in ("discovery", "graph", "scope", "semantic-ir", "user-stories", "test-scenarios")}
    c.snapshot("scope", scope, "engagement.json#/scope", "mixed", approvals["scope"])
    c.snapshot("target", c.target, "engagement.json#/seed/target", "unknown",
               {"approved": c.target.get("approved", False), "actor": c.target.get("approvedBy"),
                "at": c.target.get("approvedAt"), "binding": "recorded-target-approval"})
    c.snapshot("approvals", eng.get("gates", {}), "engagement.json#/gates", "observed")
    c.snapshot("clarifications", seed.get("clarifications", {}), "engagement.json#/seed/clarifications", "unknown")
    c.snapshot("module-metadata", {"capabilities": seed.get("capabilities", []), "scopeModules": seed.get("scope_modules", [])}, "engagement.json#/seed", "mixed")
    graph = seed.get("graph") or {}
    applied = seed.get("applied_graph") or {}
    c.snapshot("original-graphs", {"graph": graph, "appliedGraph": applied}, "engagement.json#/seed", "mixed")
    c.dependencies = collect_dependencies(scope, graph, applied)
    c.snapshot("module-graph", c.dependencies, "engagement.json#/seed/graph; /seed/applied_graph",
               "deterministic-derived" if graph.get("evidenceRequired") else "unknown", approvals["graph"])
    selected_ids = set(c.dependencies["selectedNodeIds"])
    context_ids = set(c.dependencies["contextNodeIds"])
    akg = seed.get("dotnet_akg") or {}
    workflows = [w for w in akg.get("codeWorkflows", [])
                 if w.get("entryPoint", "").rsplit(".", 1)[0] in context_ids
                 or w.get("entryPoint") in context_ids]
    # Retain full existing analysis as contextual evidence: selection rules must not silently drop
    # workflows whose identifiers cannot be mapped by a language-specific convention.
    c.snapshot("analysis-context", {"dotnetAkg": akg, "scopeAnalysis": seed.get("scope_analysis"),
               "analyzerInventory": (eng.get("inventory") or {}).get("analyzers", []),
               "moduleWorkflows": workflows, "fullAstSnapshot": "not-persisted-by-current-pipeline"},
               "engagement.json#/seed", "mixed")
    c.snapshot("inventory", eng.get("inventory"), "engagement.json#/inventory", "observed")
    sir = [s for s in seed.get("semantic_ir", []) if s.get("module") == request.moduleId]
    c.snapshot("sir", sir, "engagement.json#/seed/semantic_ir", "mixed", approvals["semantic-ir"])
    c.snapshot("sir-metadata", eng.get("sirMeta"), "engagement.json#/sirMeta", "observed")
    stories = eng.get("userStories") or {}
    if stories and stories.get("scope") != request.moduleId:
        c.finding("STORIES_MODULE_MISMATCH", "Current stories belong to another module.", "stories", "blocker")
        stories = {}
    c.snapshot("stories", stories, "engagement.json#/userStories", "mixed", approvals["user-stories"])
    c.snapshot("requirements", {"association": "not-established", "requirements": seed.get("requirements", []),
               "legacyBacklog": seed.get("backlog", [])}, "engagement.json#/seed/requirements; /seed/backlog", "unknown")
    tests = eng.get("testScenarios") or {}
    if tests and tests.get("scope") != request.moduleId:
        c.finding("TESTS_MODULE_MISMATCH", "Current test scenarios belong to another module.", "tests", "blocker")
        tests = {}
    c.snapshot("tests", tests, "engagement.json#/testScenarios", "mixed", approvals["test-scenarios"])
    # Existing persisted evidence only. Never call discovery/pack/generation endpoints.
    artifact_hashes = {}
    for rel in ("artifacts/discovery-approved.json", "artifacts/discovery.json",
                "artifacts/discovery-evidence.json", "artifacts/discovery-graph.json", "artifacts/discovery-comments.json",
                "artifacts/dotnet-akg.json", "akg-overrides.json", "source/akg-overrides.json"):
        p = safe_child(root, rel)
        if p.is_file():
            data = p.read_bytes()
            artifact_hashes[rel] = digest(data)
            approval = {}
            if rel == "artifacts/discovery-approved.json":
                try:
                    report = json.loads(data)
                    approval = {**report.get("approval", {}),
                                "binding": "recorded-discovery-source-digest"}
                    if report.get("sourceDigest") != (eng.get("sourceDiscovery") or {}).get("sourceDigest"):
                        c.finding("DISCOVERY_DIGEST_MISMATCH", "Approved report and engagement discovery digests differ.",
                                  "existing:" + rel, "blocker")
                except (ValueError, AttributeError):
                    c.finding("DISCOVERY_APPROVAL_UNREADABLE", "Approval metadata cannot be read.", "existing:" + rel, "blocker")
            c.add("existing:" + rel, "existing-evidence", "snapshots/existing/" + rel, data, rel, provenance="mixed", approval=approval)
    # Include saved test projects as generated evidence, not passing baselines.
    for dirname in ("artifacts/tests", "artifacts/user-stories", "artifacts/evidence", "artifacts/supporting-documents"):
        for p, excluded in _walk(safe_child(root, dirname)):
            rel = p.relative_to(root).as_posix()
            if excluded or _secret_path(p):
                c.finding("ARTIFACT_EXCLUDED", "Linked or credential file excluded.", evidence=[rel])
                continue
            data = p.read_bytes()
            artifact_hashes[rel] = digest(data)
            c.add("existing:" + rel, "existing-support", "snapshots/existing/" + rel, data, rel, provenance="unknown")
    wanted: dict[str, tuple[str, list[str]]] = {}
    for item in scope.get("files", []) + scope.get("programs", []) + scope.get("tables", []):
        path = item.get("path") or item.get("file")
        if path:
            wanted[path] = ("selected", ["scope file membership"])
    for path in scope.get("extraPaths", []):
        wanted[path] = ("selected", ["explicit scope extraPath"])
    for n in c.dependencies["nodes"]:
        path = n.get("file") or n.get("path")
        if path:
            role = "selected" if n["id"] in selected_ids else "dependency"
            if n.get("capability") != request.moduleId:
                role = "shared" if any(k.get("nodeId") == n["id"] for k in applied.get("sharedKernels", [])) else "dependency"
            wanted.setdefault(path, (role, [n["id"]]))
    # Clarifications are decision records. Their evidence can describe proposed
    # target files (for example a future Playwright configuration), so it must
    # remain in the clarification snapshot but must not be treated as legacy
    # source inventory.
    trace_references = list(_source_references([sir, c.dependencies["edges"], workflows, seed.get("requirements", [])]))
    all_source, excluded_source = {}, []
    for p, excluded in _walk(source_root):
        rel = p.relative_to(source_root).as_posix()
        if excluded or _secret_path(p):
            excluded_source.append(rel)
            continue
        data = p.read_bytes()
        all_source[rel] = digest(data)
        lower = p.name.lower()
        role = None
        if lower in BUILD_NAMES or p.suffix.lower() in {".sln", ".csproj", ".vbproj", ".props", ".targets", ".gradle"}:
            role = "build-support"
        elif lower.startswith(("openapi", "swagger")) or p.suffix.lower() in {".proto", ".wsdl", ".xsd", ".graphql", ".gql"}:
            role = "integration-contract"
        elif any(x.lower() in {"test", "tests", "__tests__", "spec", "specs"} for x in p.relative_to(source_root).parts[:-1]) or lower.endswith((".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx", "_test.go")) or lower.startswith("test_"):
            role = "test-baseline"
        # Extra paths can name directories; expand them without changing source.
        for extra in scope.get("extraPaths", []):
            safe_child(source_root, extra)
            if rel.startswith(extra.rstrip("/") + "/"):
                wanted.setdefault(rel, ("selected", ["explicit scope extraPath"]))
        if role:
            wanted.setdefault(rel, (role, ["repository supporting-file convention; applicability not verified"]))
    for raw_path in trace_references:
        resolved, known = _trace_source_path(raw_path, set(all_source))
        if resolved:
            wanted.setdefault(resolved, ("dependency", ["existing SIR/workflow/edge source reference"] if known else ["unresolved existing SIR/workflow/edge source reference"]))
        else:
            c.finding("TRACE_REFERENCE_UNRESOLVED", "Trace text does not identify a repository-relative source file; it was retained as evidence but not used as a path.",
                      "analysis-context", evidence=[raw_path], action="Correct the upstream trace to reference a repository-relative source path.")
    _project_support(source_root, all_source, wanted, c)
    for rel, (role, evidence) in sorted(wanted.items()):
        p = safe_child(source_root, rel)
        if p.is_dir():
            continue
        if rel in excluded_source or _secret_path(p):
            c.finding("SOURCE_EXCLUDED", "A referenced linked/credential source file was excluded.", severity="blocker", evidence=[rel])
        elif rel not in all_source or not p.is_file():
            authoring_source = _generated_output_source(rel, all_source)
            if authoring_source and any(item.endswith(": Content") for item in evidence):
                authoring_path = safe_child(source_root, authoring_source)
                if "source/" + authoring_source not in c.files:
                    c.add("source:" + authoring_source, "source", "source/" + authoring_source,
                          authoring_path.read_bytes(), "source/" + authoring_source, role="dependency",
                          provenance="observed", evidence=[f"authoring source for generated build output {rel}"])
                c.finding("GENERATED_BUILD_OUTPUT_MISSING",
                          "A generated CSS output is absent; its checked-in authoring stylesheet was included instead.",
                          evidence=[rel, authoring_source],
                          action="Regenerate the web asset during a legacy build if byte-identical output is required.")
            elif _is_deployment_profile(rel, evidence):
                c.finding("DEPLOYMENT_PROFILE_MISSING",
                          "An optional publish profile is absent; it is not application source required for modernization.",
                          evidence=[rel],
                          action="Supply a deployment profile later if the legacy publish configuration must be reproduced.")
            else:
                c.finding("SOURCE_MISSING", "A context source file is unavailable.", severity="blocker", evidence=[rel])
        else:
            if "source/" + rel not in c.files:
                c.add("source:" + rel, "source", "source/" + rel, p.read_bytes(), "source/" + rel,
                      role=role, provenance="observed", evidence=evidence)
    for row in templates.select(request.templateIds, c.target):
        metadata, contents = templates.inspect_bundle(row, c.target)
        for rel, data in contents.items():
            # Authoritative instruction documents contain credential-shaped examples.
            # Preserve their original bytes; source/artifact credential scanning remains unchanged.
            c.add("template:" + row["id"] + "/" + rel, "template", "templates/" + row["id"] + "/" + rel,
                  data, "registered-template:" + metadata["sourceIdentity"] + "/" + rel,
                  role="guidance", provenance="observed", evidence=row["limitations"], scan=False)
        c.template_rows.append(metadata)
    included = {a.origin: a for a in c.artifacts}
    for rel, sha in sorted(all_source.items()):
        artifact = included.get("source/" + rel)
        excluded = any(f.code == "SENSITIVE_CONTENT_EXCLUDED" and f.artifactId == "source:" + rel for f in c.findings)
        c.inventory_rows.append({"path": "source/" + rel, "sha256": sha,
            "artifactId": artifact.id if artifact else None,
            "status": "included" if artifact else "excluded" if excluded else "not-selected",
            "reason": "collected source" if artifact else "sensitive-content policy" if excluded else "outside selected context"})
    for rel in excluded_source:
        c.inventory_rows.append({"path": "source/" + rel, "status": "excluded", "reason": "credential or linked source"})
    for f in c.findings:
        if f.code in {"SOURCE_MISSING", "ARTIFACT_EXCLUDED"}:
            for rel in f.evidence:
                c.inventory_rows.append({"path": rel, "status": "unavailable" if f.code == "SOURCE_MISSING" else "excluded", "reason": f.message})
    # Account for remaining artifact files without collecting prior modernization outputs.
    for p, excluded in _walk(safe_child(root, "artifacts"), skip_packages=True):
        rel = p.relative_to(root).as_posix()
        # Package/engine records are derived outputs, never source workflow
        # inputs. Including them in inventory changes the package fingerprint
        # after every prepare call and defeats immutable-package reuse.
        if rel.startswith(("artifacts/module-context/", "artifacts/modernization-engine-runs/",
                           "artifacts/modernization-plans/", "artifacts/modernization-orchestrations/",
                           "artifacts/modernization-executions/")):
            continue
        if rel not in included:
            c.inventory_rows.append({"path": rel, "status": "excluded" if excluded or _secret_path(p) else "unsupported",
                                     "reason": "not included by workflow evidence collector"})
    c.inventory_rows.append({"path": "full-ast", "status": "unavailable", "reason": "not persisted by existing pipeline"})
    source_hash = digest(canonical(all_source))
    c.source = {"type": eng.get("sourceType"), "repository": _repository_id(eng.get("gitUrl")),
                "requestedBranch": eng.get("gitBranch"), "commit": None, "commitStatus": "not-resolved",
                "repositoryContentDigest": source_hash, "digestAlgorithm": "sha256",
                "digestPolicy": "all readable source files except declared cache/credential/linked exclusions",
                "excludedPaths": excluded_source, "excludedDirectoryNames": sorted(SKIP_DIRS),
                "discoveryDigest": (eng.get("sourceDiscovery") or {}).get("sourceDigest")}
    # Resolve only this source tree's own Git metadata, never a parent platform checkout.
    git_dir = source_root / ".git"
    if git_dir.is_dir() and not git_dir.is_symlink():
        try:
            result = subprocess.run(["git", "--git-dir", str(git_dir), "rev-parse", "--verify", "HEAD"],
                capture_output=True, text=True, timeout=10, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
            sha = result.stdout.strip()
            if result.returncode == 0 and re.fullmatch(r"[a-f0-9]{40,64}", sha):
                c.source.update(commit=sha, commitStatus="resolved-local-metadata")
        except (OSError, subprocess.TimeoutExpired):
            pass
    trace = []
    backlog = stories.get("backlog") or {}
    for epic in backlog.get("epics", []):
        for feature in epic.get("features", []):
            for story in feature.get("stories", []):
                trace.append({"storyId": story["id"], "trace": story.get("trace", {}),
                              "acceptanceCriteria": story.get("acceptanceCriteria", [])})
    c.snapshot("traceability", {"stories": trace, "contracts": [{"sirId": s["id"], "trace": s.get("trace"),
                "rules": [{"ruleId": r.get("ruleId"), "astNode": r.get("astNode"), "legacyLines": r.get("legacyLines")}
                          for r in s.get("rules", [])]} for s in sir],
                "testCoverage": tests.get("coverage", [])}, "derived from existing trace fields", "deterministic-derived")
    c.coverage = {"fullAstSnapshot": "unavailable", "dependencyCompleteness": "not-proven",
                  "requirementsModuleAssociation": "not-established", "sourceFiles": sum(a.kind == "source" for a in c.artifacts),
                  "sirContracts": len(sir), "stories": len(trace), "sourceExclusions": excluded_source,
                  "knownSirContractLimit": 12, "testEvidence": "see tests snapshot; checks are not live verification"}
    c.consistency = digest(canonical({"engagement": digest(raw), "source": all_source, "commit": c.source["commit"], "artifacts": artifact_hashes,
                                      "templates": c.template_rows}))
    c.fingerprint = digest(canonical({"collector": COLLECTOR_VERSION, "engagement": eid, "module": request.moduleId,
        "source": c.source, "artifacts": [a.model_dump() for a in c.artifacts], "templates": c.template_rows,
        "findings": [f.model_dump() for f in c.findings], "inventory": c.inventory_rows}))
    return c
