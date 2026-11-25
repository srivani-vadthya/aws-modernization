import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import store
from app.module_context.models import PackageRequest
from app.module_context.service import generate
from app.modernization_engine import agent_registry, execution, orchestration, package_loader, planner, repository, service
from app.modernization_engine import providers
from app.modernization_engine import provider_execution
from app.modernization_engine.providers import AwsTransformProvider, BedrockProvider
from app.modernization_engine.models import ExecutionStatus, FailureRecord, PlanStatus, RunStatus
from app.modernization_engine.readiness import READINESS_POLICY_VERSION, preview as readiness_preview
from app.modernization_engine.routes import router
from app.module_context.repository import ContextError, package_root, safe_child

EID = "deafbeef1234"


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value, (dict, list)) else value, encoding="utf-8")


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ENG_DIR", tmp_path / "engagements")
    root = store.ENG_DIR / EID
    write(root / "source/Orders.cs", "class Orders {}")
    write(root / "source/App.csproj", "<Project />")
    write(root / "engagement.json", {
        "id": EID,
        "gates": {name: {"status": "approved", "decision": "approved", "comment": "reviewed", "actor": "reviewer", "at": "2026-01-01T00:00:00Z"}
                  for name in ("discovery", "scope", "semantic-ir", "requirements", "user-stories")},
        "scope": {"capabilityId": "orders", "files": [{"path": "Orders.cs"}]},
        "seed": {"graph": {"nodes": [{"id": "Orders", "file": "Orders.cs", "capability": "orders"}], "edges": []},
                 "semantic_ir": [],
                 "target": {"language": "csharp", "framework": "aspnetcore", "frameworkVersion": "8", "runtimeVersion": "8",
                            "architecture": "controllers services repositories", "apiApproach": "controllers", "data": "sql server",
                            "approved": True, "approvalStatus": "APPROVED"}},
        "userStories": {"scope": "orders", "backlog": {"epics": []}},
    })
    return generate(EID, PackageRequest(moduleId="orders"))["manifest"]


def test_loads_schema2_package_and_previews_blockers(package):
    preview = service.readiness_preview(EID, "orders", package["packageId"])
    assert preview.packageSchemaVersion == "2.0.0"
    assert preview.packageIntegrity == "valid"
    assert preview.overallStatus == "NOT_READY"
    assert not preview.executable
    assert any(f.code == "SIR_MISSING" for f in preview.findings)
    assert any(f.code == "ENGINE_APPROVAL_REVISION_UNBOUND" for f in preview.findings)


def test_legacy_quality_risks_are_warnings_but_safe_packaged_input_is_executable():
    manifest = {
        "packageId": "a" * 32,
        "schemaVersion": "2.0.0",
        "readiness": {"findings": [
            {"code": "SENSITIVE_CONTENT_EXCLUDED", "severity": "blocker", "message": "legacy", "evidence": ["Web.config"]},
            {"code": "LIVE_BASELINE_MISSING", "severity": "blocker", "message": "legacy", "evidence": ["tests"]},
            {"code": "TRACE_UNRESOLVED", "severity": "blocker", "message": "legacy", "evidence": []},
        ]},
        "contract": {"target": {"templateIds": ["gold"], "missingFields": []}, "approvals": {"records": []}},
        "templates": [{"id": "gold", "available": True, "compatibility": {"status": "blocked"}}],
    }
    result = readiness_preview(EID, "orders", manifest, {"valid": True})
    assert result.overallStatus == "READY_WITH_WARNINGS" and result.executable
    assert result.policyVersion == READINESS_POLICY_VERSION
    assert not [item for item in result.findings if item.severity == "blocker"]


def test_blocked_run_is_recorded_but_not_queued(package):
    run = service.create_run(EID, "orders", package["packageId"])
    assert run.status is RunStatus.BLOCKED
    assert [event.toStatus for event in run.statusHistory] == [RunStatus.DRAFT, RunStatus.VALIDATING, RunStatus.BLOCKED]
    assert repository.load(EID, run.runId).packageDigest == package["packageDigest"]
    assert repository.list_runs(EID, "orders")[0].runId == run.runId


def test_missing_integrity_and_module_are_rejected(package):
    with pytest.raises(ContextError):
        service.readiness_preview(EID, "other", package["packageId"])
    with pytest.raises(ContextError):
        service.readiness_preview(EID, "orders", "f" * 32)
    path = safe_child(package_root(EID, package["packageId"]), "source/Orders.cs")
    path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ContextError, match="integrity"):
        package_loader.load(EID, package["packageId"], "orders")


def test_unsupported_schema_is_rejected(package, monkeypatch):
    monkeypatch.setattr(package_loader, "SUPPORTED_SCHEMA", set())
    with pytest.raises(ContextError, match="unsupported"):
        package_loader.load(EID, package["packageId"], "orders")


def test_lifecycle_rejects_direct_execution_transition(package):
    run = service.create_run(EID, "orders", package["packageId"])
    with pytest.raises(ValueError, match="Invalid"):
        service.transition(run, RunStatus.RUNNING, "must not execute")


def test_engine_routes(package):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    base = f"/api/engagements/{EID}/modernization-engine"
    preview = client.get(base + f"/packages/{package['packageId']}/readiness?moduleId=orders")
    assert preview.status_code == 200 and preview.json()["preview"]["overallStatus"] == "NOT_READY"
    created = client.post(base + "/runs", json={"moduleId": "orders", "packageId": package["packageId"]})
    assert created.status_code == 200 and created.json()["run"]["status"] == "BLOCKED"
    run_id = created.json()["run"]["runId"]
    assert client.get(base + "/runs?moduleId=orders").json()["runs"][0]["runId"] == run_id
    assert client.get(base + f"/runs/{run_id}/status").json()["run"]["status"] == "BLOCKED"


def test_package_produces_blocked_traceable_planning_preview_and_persisted_plan(package):
    plan = service.planning_preview(EID, "orders", package["packageId"])
    assert plan.status.value == "BLOCKED_PLAN"
    assert not plan.executionAuthorized
    assert plan.strategy.approved is False
    assert plan.tasks and all(task.planningStatus == "blocked" for task in plan.tasks)
    assert all(task.sourceArtifacts for task in plan.tasks)
    saved = service.create_plan(EID, "orders", package["packageId"])
    assert repository.load_plan(EID, saved.planId).packageDigest == package["packageDigest"]
    assert service.get_plan(EID, saved.planId).stale is False


def test_planning_routes(package):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    base = f"/api/engagements/{EID}/modernization-engine"
    preview = client.get(base + f"/packages/{package['packageId']}/planning-preview?moduleId=orders")
    assert preview.status_code == 200
    assert preview.json()["plan"]["status"] == "BLOCKED_PLAN"
    saved = client.post(base + "/plans", json={"moduleId": "orders", "packageId": package["packageId"]})
    assert saved.status_code == 200
    plan_id = saved.json()["plan"]["planId"]
    assert client.get(base + "/plans?moduleId=orders").json()["plans"][0]["planId"] == plan_id
    assert client.get(base + f"/plans/{plan_id}/tasks/task-backend").status_code == 200
    assert client.get(base + f"/plans/{plan_id}/dependency-order").status_code == 200
    assert client.get(base + f"/plans/{plan_id}/risks").status_code == 200


def test_plan_is_marked_stale_when_current_package_digest_changes(package, monkeypatch):
    saved = service.create_plan(EID, "orders", package["packageId"])
    original = package_loader.load
    def changed(*args):
        manifest, integrity = original(*args)
        return {**manifest, "packageDigest": "0" * 64}, integrity
    monkeypatch.setattr(package_loader, "load", changed)
    assert service.get_plan(EID, saved.planId).stale is True


def test_agent_registry_and_blocked_orchestration_preview(package):
    agents = agent_registry.list_agents()
    assert any(agent for agent in agents if "backend" in agent.taskCategories)
    plan = service.create_plan(EID, "orders", package["packageId"])
    preview = service.orchestration_preview(EID, plan.planId)
    assert preview.status == "PREVIEW"
    assert preview.blockedTaskIds
    assert all(item.status.value == "BLOCKED" for item in preview.assignments)
    assert all(item.output.executionStatus == "not-started" for item in preview.assignments)
    assert any(item.agentId == "backend-modernization-agent" for item in preview.assignments)


def test_orchestration_persistence_stale_detection_and_routes(package, monkeypatch):
    plan = service.create_plan(EID, "orders", package["packageId"])
    record = service.create_orchestration(EID, plan.planId)
    assert repository.load_orchestration(EID, record.orchestrationId).planId == plan.planId
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    base = f"/api/engagements/{EID}/modernization-engine"
    assert client.get("/api/modernization-engine/agents").status_code == 200
    assert client.get(base + f"/plans/{plan.planId}/orchestration-preview").status_code == 200
    created = client.post(base + "/orchestrations", json={"planId": plan.planId})
    assert created.status_code == 200 and created.json()["orchestration"]["executionAuthorized"] is False
    original = service.get_plan
    def stale(*args):
        return original(*args).model_copy(update={"stale": True})
    monkeypatch.setattr(service, "get_plan", stale)
    assert service.get_orchestration(EID, record.orchestrationId).stale is True


def test_orchestration_uses_manual_fallback_and_detects_cycles(package):
    plan = service.create_plan(EID, "orders", package["packageId"])
    task = plan.tasks[0].model_copy(update={"category": "unsupported", "dependencies": [plan.tasks[0].taskId]})
    changed = plan.model_copy(update={"tasks": [task, *plan.tasks[1:]]})
    record = orchestration.build(changed, "revision", "a" * 32, repository.now(), preview=True)
    assert record.assignments[0].agentId == "manual-engineering-review"
    assert any(f.code == "CIRCULAR_TASK_DEPENDENCY" for f in record.findings)


def test_execution_preview_is_blocked_and_authorized_creation_is_rejected(package):
    plan = service.create_plan(EID, "orders", package["packageId"])
    orchestration_record = service.create_orchestration(EID, plan.planId)
    preview = service.execution_preview(EID, orchestration_record.orchestrationId)
    assert preview.status is ExecutionStatus.BLOCKED
    assert not preview.executionAuthorized
    assert preview.logs and preview.logs[0].eventType == "execution-preview"
    with pytest.raises(ValueError, match="PLAN_NOT_APPROVED"):
        service.create_authorized_execution(EID, orchestration_record.orchestrationId)


def test_execution_preview_defers_manual_workstreams_from_provider_queue(package):
    plan = service.create_plan(EID, "orders", package["packageId"])
    approved_plan = repository.update_plan(plan.model_copy(update={"status": PlanStatus.APPROVED_PLAN}))
    orchestration_record = service.create_orchestration(EID, approved_plan.planId)
    approved_orchestration = repository.update_orchestration(orchestration_record.model_copy(update={"status": "APPROVED"}))
    preview = service.execution_preview(EID, approved_orchestration.orchestrationId)
    automated = {task.taskId for task in approved_plan.tasks if task.suggestedProvider in {"amazon-bedrock", "aws-transform"}}
    assert {task.taskId for task in preview.tasks} == automated
    assert any(log.eventType == "manual-workstream-deferred" for log in preview.logs)


def test_execution_lifecycle_checkpoint_scheduler_and_retry(package):
    plan = service.create_plan(EID, "orders", package["packageId"])
    orchestration_record = service.create_orchestration(EID, plan.planId)
    record = service.execution_preview(EID, orchestration_record.orchestrationId)
    validating = execution.transition(record, ExecutionStatus.VALIDATING, "recheck", repository.now())
    with pytest.raises(ValueError, match="Invalid"):
        execution.transition(validating, ExecutionStatus.RUNNING, "not queued", repository.now())
    point = execution.checkpoint(record, record.tasks[0].taskId, repository.now())
    assert point.checkpoints and point.checkpoints[0].taskId == record.tasks[0].taskId
    failed = execution.fail_task(record, record.tasks[0].taskId, FailureRecord(classification="transient", message="test", retryable=True), repository.now())
    retryable = failed.model_copy(update={"maxAttempts": 2})
    retried = execution.retry_task(retryable, record.tasks[0].taskId, repository.now())
    assert retried.tasks[0].status is ExecutionStatus.QUEUED
    assert execution.ready_tasks(retried) == [record.tasks[0].taskId]


def test_execution_routes_preview_and_reject_creation(package, monkeypatch):
    plan = service.create_plan(EID, "orders", package["packageId"])
    orchestration_record = service.create_orchestration(EID, plan.planId)
    monkeypatch.setenv("EXECUTION_AUTH_TOKENS", '{"test-token":{"subject":"tester","permissions":["execution:read","execution:control"],"engagements":["deafbeef1234"]}}')
    app = FastAPI(); app.include_router(router); client = TestClient(app)
    client.headers.update({"Authorization": "Bearer test-token"})
    base = f"/api/engagements/{EID}/modernization-engine"
    assert client.get(base + f"/orchestrations/{orchestration_record.orchestrationId}/execution-preview").json()["execution"]["status"] == "BLOCKED"
    assert client.post(base + "/executions", json={"orchestrationId": orchestration_record.orchestrationId}).status_code == 422


def test_execution_routes_require_identity_and_control_permission(package, monkeypatch):
    plan = service.create_plan(EID, "orders", package["packageId"])
    orchestration_record = service.create_orchestration(EID, plan.planId)
    app = FastAPI(); app.include_router(router); client = TestClient(app)
    base = f"/api/engagements/{EID}/modernization-engine"
    assert client.get(base + f"/orchestrations/{orchestration_record.orchestrationId}/execution-preview").status_code == 401
    monkeypatch.setenv("EXECUTION_AUTH_TOKENS", '{"reader":{"subject":"reader","permissions":["execution:read"],"engagements":["deafbeef1234"]}}')
    client.headers.update({"Authorization": "Bearer reader"})
    assert client.get(base + f"/orchestrations/{orchestration_record.orchestrationId}/execution-preview").status_code == 200
    assert client.post(base + "/executions", json={"orchestrationId": orchestration_record.orchestrationId}).status_code == 403


def test_bedrock_provider_reuses_gateway_and_transform_reports_missing_cli():
    class Gateway:
        def invoke(self, system, prompt, **kwargs):
            assert kwargs["provider"] == "bedrock" and kwargs["task_type"] == "code"
            assert kwargs["max_tokens"] == 2000
            return "mock result"
    result = BedrockProvider(Gateway()).invoke("code", "system", "prompt")
    assert result.ok and result.output == "mock result"
    assert not BedrockProvider(Gateway()).invoke("invalid", "", "").ok
    transform = AwsTransformProvider()
    if not transform.cli_available():
        assert not transform.list_definitions().ok


def test_generated_file_parser_accepts_valid_enveloped_file_map_and_rejects_unsafe_path():
    output = json.dumps({"result": {"files": {"backend/OrdersController.cs": "public class OrdersController {}"}}})
    assert provider_execution._files_from_response(output, {"backend"}) == {
        "backend/OrdersController.cs": "public class OrdersController {}"
    }
    with pytest.raises(ValueError):
        provider_execution._files_from_response(json.dumps({"files": {"../escape.cs": "bad"}}))


def test_generated_file_parser_accepts_complete_fenced_multifile_json():
    response = '''```json
{"files":{"backend/One.cs":"public class One {}","backend/Two.cs":"public class Two {}"}}
```'''
    assert set(provider_execution._files_from_response(response, {"backend"})) == {
        "backend/One.cs", "backend/Two.cs"
    }


def test_transform_default_command_is_noninteractive_and_explicitly_trusts_tools():
    assert "--non-interactive" in providers.DEFAULT_TRANSFORM_EXECUTION_ARGUMENTS
    assert "--trust-all-tools" in providers.DEFAULT_TRANSFORM_EXECUTION_ARGUMENTS


def test_transform_cli_path_removes_windows_extended_prefix(monkeypatch):
    monkeypatch.setattr(providers.os, "name", "nt")
    assert providers._cli_path(r"\\?\C:\work\legacy-source") == r"C:\work\legacy-source"


def test_transform_execution_has_short_no_progress_and_bounded_total_timeout():
    assert providers.TRANSFORM_NO_PROGRESS_TIMEOUT_SECONDS == 300
    assert providers.TRANSFORM_TOTAL_TIMEOUT_SECONDS == 7200


def test_transform_host_sdk_preflight_requires_major_version_ten(monkeypatch):
    class Result: stdout = "8.0.428 [C:\\Program Files\\dotnet\\sdk]\n"
    monkeypatch.setattr(providers.subprocess, "run", lambda *args, **kwargs: Result())
    assert providers.transform_host_sdk_ready() is False
    Result.stdout = "8.0.428 [C:\\Program Files\\dotnet\\sdk]\n10.0.100 [C:\\Program Files\\dotnet\\sdk]\n"
    assert providers.transform_host_sdk_ready() is True


def test_transform_scope_uses_selected_project_closure_not_all_inferred_dependencies():
    manifest = {"artifacts": [
        {"id": "selected", "kind": "source", "role": "selected", "path": "source/App/Feature.cs"},
        {"id": "project", "kind": "source", "role": "dependency", "path": "source/App/Related.cs"},
        {"id": "view", "kind": "source", "role": "dependency", "path": "source/App/Views/Feature.cshtml"},
        {"id": "library", "kind": "source", "role": "dependency", "path": "source/App/Scripts/libs/jquery.js"},
        {"id": "other", "kind": "source", "role": "dependency", "path": "source/Other/Unrelated.cs"},
        {"id": "shared", "kind": "source", "role": "shared", "path": "source/Shared/Contract.cs"},
        {"id": "build", "kind": "source", "role": "build-support", "path": "source/App/App.csproj"},
    ]}
    assert {ref.artifactId for ref in planner._transform_refs(manifest)} == {"selected", "project", "view", "build", "shared"}


def test_transform_command_tells_provider_to_honor_the_staged_scope_manifest():
    command_context = " ".join(providers.DEFAULT_TRANSFORM_EXECUTION_ARGUMENTS)
    assert "modernization-scope.json" in command_context
    assert "modernization-template-contract.json" in command_context
    assert ".modernization-templates" in command_context


def test_transform_staging_copies_only_immutable_package_template_snapshots(tmp_path):
    package_root = tmp_path / "package"
    workspace = tmp_path / "execution" / "output"
    write(package_root / "source/App/Orders.cs", "class Orders {}")
    write(package_root / "templates/dotnet8-guidance/dotnet-file-structure/SKILL.md", "# DotNet 8 guidance")
    manifest = {
        "templates": [{"id": "dotnet8-guidance", "revision": "bundle-sha"}],
        "artifacts": [
            {"id": "selected", "kind": "source", "role": "selected", "path": "source/App/Orders.cs"},
            {"id": "template", "kind": "template", "path": "templates/dotnet8-guidance/dotnet-file-structure/SKILL.md"},
        ],
    }
    source, staged = provider_execution._stage_transform_input(
        manifest, package_root, workspace, SimpleNamespace(sourceArtifacts=[SimpleNamespace(artifactId="selected")])
    )
    assert staged == 1
    assert (source / "App/Orders.cs").read_text(encoding="utf-8") == "class Orders {}"
    assert (source / ".modernization-templates/dotnet8-guidance/dotnet-file-structure/SKILL.md").read_text(encoding="utf-8") == "# DotNet 8 guidance"
    assert json.loads((source / "modernization-template-contract.json").read_text(encoding="utf-8"))["bundles"][0]["id"] == "dotnet8-guidance"


def test_prepare_is_idempotent_for_unchanged_package_inputs(package):
    first = service.prepare(EID, "orders")
    second = service.prepare(EID, "orders")
    assert first["package"]["packageId"] == second["package"]["packageId"]
    assert first["run"].runId == second["run"].runId
    assert first["plan"].planId == second["plan"].planId
    assert first["orchestration"].orchestrationId == second["orchestration"].orchestrationId
    assert len(repository.list_runs(EID, "orders")) == 1
    assert len(repository.list_plans(EID, "orders")) == 1


def test_single_start_rejects_readiness_blockers_and_cannot_bypass_approval(package, monkeypatch):
    plan = service.create_plan(EID, "orders", package["packageId"])
    with pytest.raises(ValueError, match="readiness blockers"):
        service.authorize_start(EID, plan.planId)
    monkeypatch.setenv("EXECUTION_AUTH_TOKENS", '{"operator":{"subject":"operator","permissions":["execution:control"],"engagements":["deafbeef1234"]}}')
    app = FastAPI(); app.include_router(router); client = TestClient(app)
    client.headers.update({"Authorization": "Bearer operator"})
    response = client.post(f"/api/engagements/{EID}/modernization-engine/start", json={"planId": plan.planId})
    assert response.status_code == 422
    assert repository.list_executions(EID, "orders") == []


def test_orphaned_execution_is_persisted_as_interrupted(package):
    plan = service.create_plan(EID, "orders", package["packageId"])
    orchestration_record = service.create_orchestration(EID, plan.planId)
    preview = service.execution_preview(EID, orchestration_record.orchestrationId)
    queued = preview.model_copy(update={"status": ExecutionStatus.QUEUED})
    repository.create_execution(queued)
    assert service.interrupt_orphaned_executions(EID) == 1
    recovered = repository.load_execution(EID, queued.executionId)
    assert recovered.status is ExecutionStatus.INTERRUPTED
    assert recovered.logs[-1].status is ExecutionStatus.INTERRUPTED
    assert "Backend restarted" in recovered.logs[-1].message


def test_transform_first_allocation_uses_verified_adapter_capability_not_frontend_backend_split(monkeypatch):
    verified = {
        "aws-transform": {"status": "CONFIGURED", "verifiedDefinitions": ["AWS/dotnet-modernization"]},
        "amazon-bedrock": {"status": "CONFIGURED"},
    }
    monkeypatch.setattr(providers, "provider_readiness", lambda: verified)
    target = {"language": "csharp", "framework": "aspnetcore", "frameworkVersion": "8"}
    assert providers.recommend_provider("backend", target, True)[0] == "aws-transform"
    assert providers.recommend_provider("api", target, True)[0] == "aws-transform"
    # The installed adapter has no verified React definition, so frontend work is
    # allocated to Bedrock rather than pretending Transform supports it.
    assert providers.recommend_provider("frontend", target, True)[0] == "amazon-bedrock"


def test_unverified_transform_definition_falls_back_to_configured_bedrock():
    readiness = {"aws-transform": {"status": "CONFIGURED", "verifiedDefinitions": []},
                 "amazon-bedrock": {"status": "CONFIGURED"}}
    provider, reason, capability, fallback, fallback_provider = providers.allocate_provider(
        "backend", {"language": "csharp", "frameworkVersion": "8"}, True, readiness)
    assert provider == "amazon-bedrock"
    assert "not verified" in reason
    assert capability["transformReason"] == "no verified compatible Transform definition"
    assert not fallback and fallback_provider is None


def test_bedrock_unavailable_and_manual_workstreams_are_not_assigned_to_provider_execution():
    unavailable = {"aws-transform": {"status": "NOT_CONFIGURED", "verifiedDefinitions": []},
                   "amazon-bedrock": {"status": "NOT_CONFIGURED"}}
    provider, _, capability, _, _ = providers.allocate_provider("frontend", {"language": "csharp"}, True, unavailable)
    assert provider == "manual-engineering-review" and capability["reason"] == "provider-unavailable"
    provider, _, capability, _, _ = providers.allocate_provider("database", {"language": "csharp"}, True, unavailable)
    assert provider == "manual-engineering-review" and capability["reason"] == "manual-review-required"


def test_provider_readiness_never_exposes_secret_values(monkeypatch):
    monkeypatch.setenv("BEDROCK_API_KEY", "not-for-output")
    snapshot = providers.provider_readiness()
    assert snapshot["amazon-bedrock"]["apiKeyConfigured"] is True
    assert "not-for-output" not in repr(snapshot)


def test_plan_persists_single_owner_allocation_and_dependency_metadata(package):
    plan = service.create_plan(EID, "orders", package["packageId"])
    assert plan.providerReadiness
    assert len({task.taskId for task in plan.tasks}) == len(plan.tasks)
    assert all(task.expectedOutputFolders and task.capabilityVerification for task in plan.tasks)
    record = service.create_orchestration(EID, plan.planId)
    assignments = {item.taskId: item for item in record.assignments}
    assert all(assignments[task.taskId].prerequisiteTasks == task.dependencies for task in plan.tasks)
