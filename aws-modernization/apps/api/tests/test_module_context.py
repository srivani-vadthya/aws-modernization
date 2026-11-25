import io
import json
import zipfile
from pathlib import Path

import pytest

from app import store
from app.module_context import templates, service
from app.module_context.collector import collect
from app.module_context.models import Manifest, PackageRequest
from app.module_context.repository import ContextError, download, list_manifests, read_manifest, safe_child

EID = "abc123abc123"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value, (dict, list)) else value, encoding="utf-8")


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ENG_DIR", tmp_path / "engagements")
    root = store.ENG_DIR / EID
    source = root / "source"
    write(source / "Orders.cs", "class Orders { Shared shared; }")
    write(source / "Shared.cs", "class Shared {}")
    write(source / "Consumer.cs", "class Consumer {}")
    write(source / "App.csproj", "<Project />")
    write(source / "contracts/service.proto", "syntax = 'proto3';")
    write(source / "tests/test_existing.py", "def test_existing(): assert True")
    write(source / ".env", "SECRET=do-not-package")
    write(source / "manual/extra.txt", "extra context")
    eng = {"id": EID, "sourceType": "git", "gitUrl": "https://user:secret@example.org/team/repo.git?token=secret",
           "gitBranch": "dev", "gates": {p: {"decision": "approved", "actor": "reviewer"} for p in
                                       ("discovery", "scope", "semantic-ir", "user-stories")},
           "scope": {"capabilityId": "orders", "files": [{"path": "Orders.cs"}], "extraPaths": ["manual"],
                     "useCases": [{"id": "u1", "entryPoint": "Orders.Create"}]},
           "seed": {"graph": {"evidenceRequired": True,
                    "nodes": [{"id": "Orders", "file": "Orders.cs", "capability": "orders", "type": "program"},
                              {"id": "Shared", "file": "Shared.cs", "capability": "shared", "type": "program"},
                              {"id": "Consumer", "file": "Consumer.cs", "capability": "other", "type": "program"}],
                    "edges": [{"source": "Orders", "target": "Shared", "kind": "CALLS"},
                              {"source": "Shared", "target": "Orders", "kind": "CALLS"},
                              {"source": "Consumer", "target": "Orders", "kind": "CALLS"}]},
                    "semantic_ir": [{"id": "SIR-1", "module": "orders", "trace": {"entryPoint": "Orders.Create"},
                                     "rules": [{"ruleId": "SIR-1.R1", "legacyLines": "Orders.cs#L1"}]},
                                    {"id": "SIR-2", "module": "other", "rules": []}],
                    "target": {"language": "csharp", "framework": "aspnetcore", "frameworkVersion": "8",
                               "approved": True, "approvalStatus": "APPROVED"}},
           "userStories": {"scope": "orders", "backlog": {"epics": [{"features": [{"stories": [
               {"id": "US-1", "title": "Create", "acceptanceCriteria": ["Given valid input, when saved, then stored"],
                "trace": {"sirId": "SIR-1", "ruleIds": ["SIR-1.R1"]}}]}]}]}}}
    write(root / "engagement.json", eng)
    # Safe template registry in fixture; no real template writes.
    t = tmp_path / "templates"
    write(t / "SKILL.md", "Existing template guidance")
    monkeypatch.setattr(templates, "registry", lambda: [
        {"id": "dotnet8-guidance", "root": t, "kind": "guidance", "language": "csharp",
         "framework": "aspnetcore", "major": "8", "limitations": []}])
    return root, eng, t


def existing_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and "module-context" not in p.parts}


def request():
    return PackageRequest(moduleId="orders", templateIds=["dotnet8-guidance"])


def test_portable_package_and_no_existing_mutation(context, monkeypatch):
    root, eng, t = context
    before, template_before = existing_bytes(root), existing_bytes(t)
    monkeypatch.setattr(store, "save", lambda *a: pytest.fail("store.save called"))
    result = service.generate(EID, request())
    m = Manifest.model_validate(result["manifest"])
    assert m.moduleId == "orders" and m.schemaVersion == "2.0.0"
    assert m.readiness.executionVerified is False
    assert m.source["repository"] == "https://example.org/team/repo.git"
    paths = {a.path: a for a in m.artifacts}
    assert paths["source/Orders.cs"].modificationAllowed
    assert not paths["source/Shared.cs"].modificationAllowed
    assert paths["source/App.csproj"].role == "build-support"
    assert paths["source/contracts/service.proto"].role == "integration-contract"
    assert paths["source/tests/test_existing.py"].role == "test-baseline"
    assert "source/manual/extra.txt" in paths
    assert "source/.env" not in paths
    assert "source/Consumer.cs" not in paths
    archive = zipfile.ZipFile(io.BytesIO(download(EID, m.packageId)))
    assert "schema.json" in archive.namelist()
    assert len(json.loads(archive.read("snapshots/sir.json"))) == 1
    deps = json.loads(archive.read("snapshots/module-graph.json"))
    assert any(e["source"] == "Consumer" for e in deps["incomingConsumers"])
    assert service.freshness(EID, m.packageId)["status"] == "current"
    assert existing_bytes(root) == before
    assert existing_bytes(t) == template_before


def test_versions_deduplicate_and_detect_changes(context):
    root, _, _ = context
    a = service.generate(EID, request())
    b = service.generate(EID, request())
    assert not b["created"] and a["manifest"]["packageId"] == b["manifest"]["packageId"]
    write(root / "source/Shared.cs", "class Shared { int changed; }")
    assert service.freshness(EID, a["manifest"]["packageId"])["status"] == "stale"
    c = service.generate(EID, request())
    assert c["created"] and c["manifest"]["packageId"] != a["manifest"]["packageId"]
    assert len(list_manifests(EID, "orders")) == 2
    assert download(EID, a["manifest"]["packageId"])


def test_missing_optional_and_required_data_produces_report(context):
    root, eng, _ = context
    eng["seed"]["semantic_ir"] = []
    eng["seed"]["target"] = {}
    write(root / "engagement.json", eng)
    (root / "source/Shared.cs").unlink()
    m = service.generate(EID, PackageRequest(moduleId="orders"))["manifest"]
    codes = {f["code"] for f in m["readiness"]["findings"]}
    assert {"SIR_MISSING", "SOURCE_MISSING", "TARGET_NOT_APPROVED", "TEST_SCENARIOS_MISSING"} <= codes
    assert m["readiness"]["modernizationPrerequisites"] == "blocked"


def test_template_incompatibility_and_no_implicit_selection(context):
    root, eng, _ = context
    eng["seed"]["target"]["frameworkVersion"] = "10"
    write(root / "engagement.json", eng)
    m = service.generate(EID, request())["manifest"]
    assert "TEMPLATE_VERSION_CONFLICT" in {f["code"] for f in m["readiness"]["findings"]}
    assert service.generate(EID, PackageRequest(moduleId="orders", templateIds=[]))["manifest"]["templates"] == []


def test_integrity_detection(context):
    root, _, _ = context
    m = service.generate(EID, request())["manifest"]
    write(root / "artifacts/module-context" / m["packageId"] / "source/Orders.cs", "tampered")
    with pytest.raises(ContextError, match="integrity"):
        download(EID, m["packageId"])


def test_paths_scope_and_unknown_engagement(context):
    root, eng, _ = context
    with pytest.raises(ContextError):
        service.generate(EID, PackageRequest(moduleId="other"))
    with pytest.raises(ContextError):
        list_manifests("ffffffffffff")
    assert not (store.ENG_DIR / "ffffffffffff").exists()
    eng["scope"]["extraPaths"] = ["../outside"]
    write(root / "engagement.json", eng)
    with pytest.raises(ContextError, match="Unsafe"):
        collect(EID, request())


def test_windows_relative_paths_are_normalized_but_escape_attempts_remain_rejected(context):
    root, _, _ = context
    assert safe_child(root / "source", r"folder\\Orders.cs").as_posix().endswith("/source/folder/Orders.cs")
    for unsafe in (r"..\\outside", r"C:\\outside", r"\\server\\share", "/outside"):
        with pytest.raises(ContextError, match="Unsafe"):
            safe_child(root / "source", unsafe)


def test_descriptive_trace_reference_uses_known_source_path_without_crashing(context):
    root, eng, _ = context
    eng["seed"]["requirements"] = [{"id": "REQ-TRACE", "traces": [
        "Orders.cs (Orders.Create: validates requested order details)",
        "not a repository path; analyst note only",
    ]}]
    write(root / "engagement.json", eng)
    manifest = service.generate(EID, request())["manifest"]
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    findings = {finding["code"] for finding in manifest["readiness"]["findings"]}
    assert "source/Orders.cs" in artifact_paths
    assert "TRACE_REFERENCE_UNRESOLVED" in findings
    assert "SOURCE_MISSING" not in findings


def test_clarification_target_file_is_retained_as_evidence_not_required_legacy_source(context):
    root, eng, _ = context
    eng["seed"]["clarifications"] = {"tests": [{"evidence": {"path": "playwright.config.ts"}}]}
    write(root / "engagement.json", eng)
    manifest = service.generate(EID, request())["manifest"]
    missing = [item for item in manifest["readiness"]["findings"] if item["code"] == "SOURCE_MISSING"]
    assert not missing
    assert "playwright.config.ts" in (root / "artifacts/module-context" / manifest["packageId"] /
                                        "snapshots/clarifications.json").read_text(encoding="utf-8")


def test_mutation_during_collection_does_not_publish(context, monkeypatch):
    root, _, _ = context
    original = service.collect
    calls = []
    def changing(*args):
        c = original(*args)
        calls.append(1)
        if len(calls) == 1:
            write(root / "source/Orders.cs", "changed")
        return c
    monkeypatch.setattr(service, "collect", changing)
    with pytest.raises(ContextError, match="Inputs changed"):
        service.generate(EID, request())
    assert list_manifests(EID) == []


def test_sensitive_source_is_not_exported(context):
    root, _, _ = context
    write(root / "source/Orders.cs", 'const string api_key = "private-value-123";')
    m = service.generate(EID, request())["manifest"]
    assert "SENSITIVE_CONTENT_EXCLUDED" in {f["code"] for f in m["readiness"]["findings"]}
    z = zipfile.ZipFile(io.BytesIO(download(EID, m["packageId"])))
    assert all(b"private-value-123" not in z.read(p) for p in z.namelist())


def test_scope_switch_preserves_old_package(context):
    root, eng, _ = context
    m = service.generate(EID, request())["manifest"]
    eng["scope"]["capabilityId"] = "other"
    write(root / "engagement.json", eng)
    assert service.freshness(EID, m["packageId"])["status"] == "not-comparable"
    assert read_manifest(EID, m["packageId"])["moduleId"] == "orders"
    assert download(EID, m["packageId"])


def test_routes_preserve_workflow(context):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.module_context.routes import router
    root, _, _ = context
    before = existing_bytes(root)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    base = f"/api/engagements/{EID}/module-context-packages"
    result = client.post(base, json=request().model_dump())
    assert result.status_code == 200
    pid = result.json()["manifest"]["packageId"]
    assert client.get(base).json()["packages"][0]["packageId"] == pid
    assert client.get(base + "/" + pid).status_code == 200
    assert client.get(base + "/" + pid + "/download").content.startswith(b"PK")
    integrity = client.get(base + "/" + pid + "/integrity")
    assert integrity.status_code == 200 and integrity.json()["internalReferences"] == "validated"
    assert client.get(base + "/" + pid + "/freshness").json()["status"] == "current"
    assert client.get("/api/module-context-schema").json()["title"] == "Manifest"
    assert client.get("/api/module-context-schema?version=1.0.0").json()["title"] == "ManifestV1"
    assert client.get("/api/module-context-templates").json()["templates"][0]["available"]
    assert client.post(base, json={"moduleId": "other"}).status_code == 409
    assert client.post(base, json={"moduleId": "orders", "templateIds": ["../../x"]}).status_code == 422
    assert client.get(base + "/bad-id").status_code == 404
    assert existing_bytes(root) == before


def test_build_project_closure(context):
    root, eng, _ = context
    write(root / "source/App.csproj", '<Project><ItemGroup><Compile Include="Orders.cs" />'
          '<ProjectReference Include="Shared/Shared.csproj" /></ItemGroup></Project>')
    write(root / "source/Shared/Shared.csproj", '<Project Sdk="Microsoft.NET.Sdk"/>')
    write(root / "source/Shared/Implementation.cs", 'class DependencyImplementation {}')
    m = service.generate(EID, request())["manifest"]
    a = next(a for a in m["artifacts"] if a["path"] == "source/Shared/Implementation.cs")
    assert a["role"] == "dependency" and not a["modificationAllowed"]


def test_optional_build_import_and_generated_css_do_not_become_missing_source_blockers(context):
    root, _, _ = context
    write(root / "source/App.csproj", '''<Project><ItemGroup>
        <Content Include="styles/site.css" />
        <Content Include="styles/site.min.css" />
    </ItemGroup><Import Project="tools/optional.targets" Condition="Exists('tools/optional.targets')" /></Project>''')
    write(root / "source/styles/site.less", "body { color: navy; }")
    manifest = service.generate(EID, request())["manifest"]
    findings = manifest["readiness"]["findings"]
    missing = {item["evidence"][0] for item in findings if item["code"] == "SOURCE_MISSING"}
    codes = {item["code"] for item in findings}
    paths = {item["path"] for item in manifest["artifacts"]}
    assert "styles/site.css" not in missing
    assert "styles/site.min.css" not in missing
    assert "tools/optional.targets" not in missing
    assert {"GENERATED_BUILD_OUTPUT_MISSING", "BUILD_REFERENCE_OPTIONAL_MISSING"} <= codes
    assert "source/styles/site.less" in paths


def test_test_checks_never_become_verified(context):
    root, eng, _ = context
    eng["testScenarios"] = {"scope": "orders", "sourceDigest": "stale",
                            "runs": [{"mode": "checks", "summary": {"passed": 100}}]}
    write(root / "engagement.json", eng)
    m = service.generate(EID, request())["manifest"]
    codes = {f["code"] for f in m["readiness"]["findings"]}
    assert {"TESTS_STALE", "BASELINE_NOT_VERIFIED"} <= codes
    assert not m["readiness"]["executionVerified"]


def test_template_changes_create_new_version(context):
    _, _, t = context
    m = service.generate(EID, request())["manifest"]
    write(t / "SKILL.md", "Updated external template instruction")
    assert service.freshness(EID, m["packageId"])["status"] == "stale"
    assert service.generate(EID, request())["created"]


def test_two_engagements_are_isolated(context):
    root, eng, _ = context
    import shutil
    other = "fed321fed321"
    other_root = root.parent / other
    shutil.copytree(root, other_root)
    eng["id"] = other
    write(other_root / "engagement.json", eng)
    first = service.generate(EID, request())["manifest"]
    second = service.generate(other, request())["manifest"]
    assert first["inputFingerprint"] != second["inputFingerprint"]
    with pytest.raises(ContextError):
        read_manifest(EID, second["packageId"])


@pytest.mark.parametrize("bad", ["../escape", "C:/escape", "sub/../../escape", "\\\\server\\share"])
def test_unsafe_extra_paths(context, bad):
    root, eng, _ = context
    eng["scope"]["extraPaths"] = [bad]
    write(root / "engagement.json", eng)
    with pytest.raises(ContextError):
        service.generate(EID, request())


def test_deep_package_paths(context):
    from app.module_context.repository import io_path
    root, eng, _ = context
    relative = '/'.join(['deep_context'] * 18) + '/evidence.txt'
    write(io_path(root / 'source' / relative), 'Supporting source evidence')
    eng['scope']['extraPaths'] = [relative]
    write(root / 'engagement.json', eng)
    m = service.generate(EID, request())['manifest']
    with zipfile.ZipFile(io.BytesIO(download(EID, m['packageId']))) as archive:
        assert archive.read('source/' + relative) == b'Supporting source evidence'


def test_authoritative_bundles_and_hashes():
    from app.module_context.repository import canonical, digest
    rows = templates.registry()
    assert {r['id'] for r in rows} == {'dotnet8-guidance', 'react-guidance'}
    for row, count in zip(rows, [7, 8]):
        metadata, content = templates.inspect_bundle(row, {'language': 'csharp', 'frontendRequirement': 'React'})
        assert metadata['available'] and metadata['fileCount'] == count
        assert metadata['sourceIdentity'].startswith('.agents/skills/')
        assert metadata['contentDigest'] == digest(canonical({k: digest(v) for k,v in content.items()}))
        for skill in metadata['files']:
            assert skill['sha256'] == digest((row['root']/skill['path']).read_bytes())
            assert skill['sourcePath'] == row['sourcePath'] + '/' + skill['path']
            assert skill['applicability']['evaluation'] == 'requires-review'
    dotnet, _ = templates.inspect_bundle(rows[0])
    assert dotnet['frameworkVersions'] == ['net8.0']
    assert {'name':'Microsoft.EntityFrameworkCore','version':'8.0.0','basis':'declared-in-skill'} in dotnet['dependencies']
    assert not dotnet['parentGuidance']['selectable']
    with pytest.raises(ContextError):
        templates.select(['dotnet8-starter'])


def test_automatic_and_explicit_empty_selection(context):
    root, eng, _ = context
    m = service.generate(EID, PackageRequest(moduleId='orders'))['manifest']
    assert [t['id'] for t in m['templates']] == ['dotnet8-guidance']
    empty = service.generate(EID, PackageRequest(moduleId='orders', templateIds=[]))['manifest']
    assert empty['templates'] == []
    assert any(f['code']=='TEMPLATES_NOT_SELECTED' and f['severity']=='blocker' for f in empty['readiness']['findings'])
    eng['seed']['target'] = {}
    write(root/'engagement.json', eng)
    assert service.generate(EID, PackageRequest(moduleId='orders'))['manifest']['templates'] == []


def test_missing_skill_blocks_but_packages(context):
    root, _, t = context
    (t/'SKILL.md').unlink()
    m = service.generate(EID, request())['manifest']
    assert not m['templates'][0]['available']
    assert 'TEMPLATE_MISSING' in {f['code'] for f in m['readiness']['findings']}


def test_real_skill_snapshots_unchanged(context, monkeypatch):
    from app.module_context.repository import digest
    # Restore real registry while retaining isolated engagement storage.
    monkeypatch.undo()
    root, eng, _ = context
    monkeypatch.setattr(store, 'ENG_DIR', root.parent)
    eng['seed']['target']['frontendRequirement'] = 'React'
    eng['seed']['target']['data'] = 'PostgreSQL'
    write(root/'engagement.json', eng)
    before = {str(p): p.read_bytes() for r in templates.registry() for p in r['root'].rglob('SKILL.md')}
    upstream = existing_bytes(root)
    m = service.generate(EID, PackageRequest(moduleId='orders'))['manifest']
    assert len(m['templates']) == 2
    with zipfile.ZipFile(io.BytesIO(download(EID,m['packageId']))) as z:
        for t in m['templates']:
            for f in t['files']:
                data=z.read(f['packagePath'])
                assert digest(data)==f['sha256']
                assert data==(templates.APP_ROOT/f['sourcePath']).read_bytes()
    codes={f['code'] for f in m['readiness']['findings']}
    assert {'TEMPLATE_DATABASE_CONFLICT','TEMPLATE_GUIDANCE_CONFLICT','REACT_APPLICABILITY_REVIEW','TEMPLATE_DEPENDENCIES_UNRESOLVED'} <= codes
    assert all(Path(p).read_bytes()==data for p,data in before.items())
    assert existing_bytes(root)==upstream


def test_v2_contract_traceability_approvals_and_integrity(context):
    from app.module_context.repository import verify
    m = service.generate(EID, request())["manifest"]
    contract = m["contract"]
    assert m["schemaVersion"] == "2.0.0"
    assert contract["artifactCount"] == len(m["artifacts"])
    assert contract["traceability"]["summary"]["totalArtifacts"] == len(m["artifacts"])
    assert contract["traceability"]["summary"]["resolvedRelationships"] > 0
    assert contract["approvals"]["records"][0]["comment"] is None
    assert all(a["binding"] == "unavailable" for a in contract["approvals"]["records"])
    assert contract["target"]["templateIds"] == ["dotnet8-guidance"]
    report = verify(EID, m["packageId"])
    assert report["valid"] and report["internalReferences"] == "validated"
    archive = zipfile.ZipFile(io.BytesIO(download(EID, m["packageId"])))
    assert set(archive.namelist()) == {"manifest.json", *(a["path"] for a in m["artifacts"])}


def test_historical_v1_manifest_remains_readable(context):
    from app.module_context.repository import canonical, digest
    root, _, _ = context
    original = service.generate(EID, request())["manifest"]
    old = {k: v for k, v in original.items() if k != "contract"}
    old["schemaVersion"] = "1.0.0"
    old["collectorVersion"] = "1.1.0"
    old["packageId"] = "f" * 32
    old["packageDigest"] = ""
    old["packageDigest"] = digest(canonical(old))
    target = root / "artifacts/module-context" / old["packageId"]
    target.mkdir(parents=True)
    for artifact in old["artifacts"]:
        source = root / "artifacts/module-context" / original["packageId"] / artifact["path"]
        out = target / artifact["path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(source.read_bytes())
    (target / "manifest.json").write_bytes(canonical(old))
    legacy = read_manifest(EID, old["packageId"])
    assert legacy["schemaVersion"] == "1.0.0" and "contract" not in legacy
    assert download(EID, old["packageId"])
