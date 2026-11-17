import pytest
import sys
from pathlib import Path

# Ensure api root is in python path
API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.bedrock_skills import (
    audit_foundational_readiness,
    analyze_database_invariants,
    simulate_ebcdic_collation_parity,
    get_bidirectional_cdc_status,
)


def test_foundational_readiness_audit_conditional():
    """Verify that Phase 0 gate identifies unmet prerequisites when grammar is missing."""
    mock_engagement = {
        "inventory": {
            "languages": {}
        },
        "seed": {
            "shadow_parity": {"testCases": []},
            "wave_cutover": {}
        },
        "scope": {
            "sharedServices": []
        }
    }
    result = audit_foundational_readiness(mock_engagement)
    assert result["overallStatus"] == "CONDITIONAL_APPROVAL"
    assert result["readinessScore"] < 90
    assert len(result["checks"]) == 4
    
    # Check 1 should fail because no supported grammar was detected
    assert result["checks"][0]["status"] == "FAIL"


def test_foundational_readiness_audit_ready():
    """Verify that Phase 0 gate marks READY when all ground-truth invariants are satisfied."""
    mock_engagement = {
        "inventory": {
            "languages": {"COBOL": 50, "CICS BMS": 12}
        },
        "seed": {
            "shadow_parity": {
                "testCases": [{"id": "TC-01"}]
            },
            "wave_cutover": {
                "waves": [{"id": "wave-1"}]
            }
        },
        "scope": {
            "sharedServices": [{"resourceId": "CUST01"}]
        }
    }
    result = audit_foundational_readiness(mock_engagement)
    assert result["overallStatus"] == "READY"
    assert result["readinessScore"] == 92
    assert all(c["status"] == "PASS" for c in result["checks"])


def test_database_invariant_analyzer():
    """Verify extraction of Db2 triggers and check constraints into modern Spring JPA equivalents."""
    mock_engagement = {"id": "eng-test"}
    invariants = analyze_database_invariants(mock_engagement)
    assert isinstance(invariants, list)
    assert len(invariants) >= 3
    
    names = [inv["name"] for inv in invariants]
    assert "TRIG_POLICY_PREMIUM_AUDIT" in names
    assert "CHK_MOTOR_VEHICLE_AGE" in names
    assert "SP_CALCULATE_NO_CLAIMS_BONUS" in names

    # Assert modernization target mappings
    for inv in invariants:
        assert inv["modernEquivalent"] != ""
        assert inv["targetCloud"] != ""
        assert inv["riskLevel"] != ""


def test_ebcdic_collation_parity_simulator():
    """Verify simulation of EBCDIC IBM-037 vs UTF-8 sort order discrepancies."""
    result = simulate_ebcdic_collation_parity()
    assert "collationScenario" in result
    assert "testCases" in result
    assert len(result["testCases"]) >= 2
    
    coll_case = next(tc for tc in result["testCases"] if tc["id"] == "COLL-01")
    assert coll_case["flaggedDiscrepancy"] is True
    assert coll_case["legacyEbcdicOrder"] != coll_case["naiveAsciiOrder"]


def test_bidirectional_cdc_status():
    """Verify bidirectional active-active CDC telemetry and rollback certification."""
    result = get_bidirectional_cdc_status()
    assert result["status"] == "HEALTHY"
    assert "syncDirection" in result
    assert result["forwardLagMs"] <= 500
    assert result["reverseLagMs"] <= 500
    assert result["safeRollbackCertified"] is True
    assert result["rollbackRecoveryPointSecs"] <= 2.0


def test_llm_gateway_multi_tier_routing():
    """Verify that LLM gateway correctly maps task types to configured model tiers."""
    from app.llm_gateway import gateway

    assert gateway.get_model_for_task("fast") == "amazon.nova-lite-v1:0"
    assert gateway.get_model_for_task("reasoning") == "amazon.nova-pro-v1:0"
    assert gateway.get_model_for_task("code") == "anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert gateway.get_model_for_task("vision") == "amazon.nova-pro-v1:0"


def test_decouple_shared_kernels():
    """Verify Phase 2 skill generates Anti-Corruption Layer OpenAPI specs for shared tables."""
    from app.bedrock_skills import decouple_shared_kernels

    mock_scope = {
        "capabilityId": "motor",
        "name": "Motor Policy Services",
        "sharedServices": [
            {
                "resourceId": "CUSTOMER",
                "kind": "table",
                "resourceName": "CUSTOMER Master Data",
                "consumers": ["Scope 2: Customer Onboarding", "Scope 3: Billing"],
            }
        ],
    }
    result = decouple_shared_kernels(mock_scope)
    assert result["totalSharedKernels"] == 1
    assert result["status"] == "DECOUPLED"
    artifact = result["artifacts"][0]
    assert artifact["resourceId"] == "CUSTOMER"
    assert "openapi: 3.0.3" in artifact["openapiSpec"]
    assert "Anti-Corruption Layer" in artifact["pattern"]


def test_synthesize_functional_rules():
    """Verify Phase 3 skill converts requirements into executable Gherkin feature files."""
    from app.bedrock_skills import synthesize_functional_rules

    mock_scope = {"name": "Claims Assessment"}
    reqs = [
        {"id": "REQ-01", "statement": "Claims over $10,000 require manual senior adjuster approval.", "traces": ["CLAIM01.cbl:140"]}
    ]
    result = synthesize_functional_rules(mock_scope, reqs)
    assert result["totalRulesSynthesized"] == 1
    feat = result["gherkinFeatures"][0]
    assert feat["requirementId"] == "REQ-01"
    assert "Feature: Rule REQ-01" in feat["gherkinFeature"]
    assert "Scenario: Validate compliance for REQ-01" in feat["gherkinFeature"]
    assert "Given a policy request matching requirement" in feat["gherkinFeature"]


def test_run_differential_golden_parity():
    """Verify Phase 6 skill calculates bitwise parity confidence score and PII masking."""
    from app.bedrock_skills import run_differential_golden_parity

    res = run_differential_golden_parity("eng-test-42", sample_size=1000)
    assert res["totalVectorsReplayed"] == 1000
    assert res["identicalMatches"] >= 990
    assert res["parityConfidenceScore"] >= 99.0
    assert res["piiMaskingApplied"] is True
    assert res["status"] in ("CERTIFIED_FOR_PRODUCTION_CUTOVER", "REMEDIATION_REQUIRED")


def test_synthesize_target_codebase_polyglot():
    """Verify Phase 5 skill generates Clean Architecture codebases for both C# .NET 9 and Java 21."""
    from app.bedrock_skills import synthesize_target_codebase

    scope = {"name": "Claims Underwriting", "capabilityId": "claims"}

    # Test C# / .NET 9 Clean Architecture
    csharp_files = synthesize_target_codebase(scope, {"language": "csharp", "framework": "dotnet-9"})
    assert "src/Domain/Entities/Policy.cs" in csharp_files
    assert "src/Application/Commands/CreatePolicyCommand.cs" in csharp_files
    assert "src/Infrastructure/Persistence/ModernDbContext.cs" in csharp_files
    assert "src/Presentation/Program.cs" in csharp_files

    # Test Java 21 / Spring Boot 3 Hexagonal Architecture
    java_files = synthesize_target_codebase(scope, {"language": "java", "framework": "spring-boot-3"})
    assert "src/main/java/com/modernize/domain/model/Policy.java" in java_files
    assert "src/main/java/com/modernize/presentation/PolicyController.java" in java_files


def test_azure_terraform_generation():
    """Verify IaC generator creates Terraform configurations for Azure Web Apps and PostgreSQL."""
    from app.iac_generator import generate_azure_terraform

    mock_engagement = {"scope": {"capabilityId": "motor"}}
    tf_files = generate_azure_terraform(mock_engagement)

    assert "terraform/azure/main.tf" in tf_files
    assert "terraform/azure/postgresql.tf" in tf_files
    assert "terraform/azure/webapp.tf" in tf_files
    assert "terraform/azure/variables.tf" in tf_files
    assert "terraform/azure/outputs.tf" in tf_files

    assert "azurerm_postgresql_flexible_server" in tf_files["terraform/azure/postgresql.tf"]
    assert "azurerm_linux_web_app" in tf_files["terraform/azure/webapp.tf"]


def test_github_workflow_generation():
    """Verify CI/CD workflow generator produces GitHub Actions for parity test and Azure deployment."""
    from app.iac_generator import generate_github_workflow

    wf_files = generate_github_workflow("azure")
    assert ".github/workflows/modernization-ci-cd.yml" in wf_files
    wf = wf_files[".github/workflows/modernization-ci-cd.yml"]
    assert "deploy-azure" in wf
    assert "playwright" in wf.lower()


def test_pii_scrubber_compliance():
    """Verify deterministic zero-trust PII scrubber redacts SSNs, credit cards, and emails."""
    from app.pii_scrubber import scrubber

    raw_text = "Customer John Doe with SSN 123-45-6789 and Card 4532-1234-5678-9012 requested policy email john@test.com"
    scrubbed, count = scrubber.scrub(raw_text)

    assert count >= 3
    assert "123-45-6789" not in scrubbed
    assert "4532-1234-5678-9012" not in scrubbed
    assert "john@test.com" not in scrubbed
    assert "TOK_SSN" in scrubbed or "REDACTED" in scrubbed


def test_batch_modernization_engine():
    """Verify JCL job stream parsing and Spring Batch 5 chunk-oriented pipeline generation."""
    from app.bedrock_skills import modernize_batch_job

    sample_jcl = """//RENEWAL JOB (ACCT),'NIGHTLY RENEWAL',CLASS=A
//STEP01   EXEC PGM=SORT
//STEP02   EXEC PGM=POLRNW01"""
    res = modernize_batch_job(sample_jcl)

    assert res["jobName"] == "RENEWAL"
    assert res["totalStepsModernized"] == 2
    assert "@EnableBatchProcessing" in res["springBatchConfig"]
    assert "StepBuilder" in res["springBatchConfig"]


def test_saga_orchestrator_synthesis():
    """Verify distributed SAGA transaction coordinator generation with compensating rollbacks."""
    from app.bedrock_skills import synthesize_saga_orchestrator

    mock_scope = {"name": "Auto Policy Issuance", "capabilityId": "auto"}
    res = synthesize_saga_orchestrator(mock_scope)

    assert res["totalParticipants"] >= 3
    assert "Orchestrated SAGA" in res["orchestrationPattern"]
    # Verify compensating actions exist for each participant
    for step in res["steps"]:
        assert step["forwardAction"] != ""
        assert step["compensatingAction"] != ""
        assert step["isIdempotent"] is True


def test_canary_routing_and_instant_rollback():
    """Verify active-active canary traffic weighting and instant rollback with CDC drift calculation."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    
    # 1. Create a sample engagement
    res = client.post("/api/engagements/sample")
    assert res.status_code == 200
    eid = res.json()["id"]

    # 2. Shift canary traffic to 25% Cloud
    shift_res = client.post(f"/api/engagements/{eid}/canary-routing", json={"cloudWeight": 25, "targetEngine": "azure"})
    assert shift_res.status_code == 200
    shift_data = shift_res.json()
    assert shift_data["ok"] is True
    assert shift_data["activeRouting"]["cloudWeight"] == 25
    assert shift_data["activeRouting"]["legacyWeight"] == 75
    assert shift_data["cdcStatus"]["safeRollbackCertified"] is True

    # 3. Trigger emergency instant rollback
    rb_res = client.post(f"/api/engagements/{eid}/instant-rollback")
    assert rb_res.status_code == 200
    rb_data = rb_res.json()
    assert rb_data["ok"] is True
    assert rb_data["activeRouting"]["cloudWeight"] == 0
    assert "100% Mainframe" in rb_data["activeRouting"]["mode"]


def test_universal_discovery_engine_and_switcher():
    """Verify dual discovery engines in meta, AST extraction across multi-language, and engine switching."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.as400 import extract_relationships
    from pathlib import Path

    client = TestClient(app)

    # 1. Verify dual discovery engines exposed in /api/meta
    meta_res = client.get("/api/meta")
    assert meta_res.status_code == 200
    engines = meta_res.json().get("discoveryEngines", [])
    engine_ids = [e["id"] for e in engines]
    assert "universal" in engine_ids
    assert "transform" in engine_ids

    # 2. Test local deterministic AST extraction for AS/400 RPGLE, CLLE, and PL/I
    sample_rpgle = """
    DCL-PR CUSTPROC EXTPGM('CUST01');
    END-PR;
    CALLP CUSTPROC();
    CHAIN (CUSTID) CUSTOMERPF;
    WRITE INVOICEPF;
    """
    facts = extract_relationships(Path("ORDER01.rpgle"), sample_rpgle)
    call_facts = [f for f in facts if f["kind"] == "CALLS"]
    read_facts = [f for f in facts if f["kind"] == "READS"]
    write_facts = [f for f in facts if f["kind"] == "WRITES"]
    assert any(f["target"] == "CUST01" for f in call_facts)
    assert any(f["target"] == "CUSTOMERPF" for f in read_facts)
    assert any(f["target"] == "INVOICEPF" for f in write_facts)

    # 3. Test dynamic engine switching endpoint
    eng_res = client.post("/api/engagements/sample")
    eid = eng_res.json()["id"]

    switch_univ = client.post(f"/api/engagements/{eid}/discovery-engine", json={"engineId": "universal"})
    assert switch_univ.status_code == 200
    assert switch_univ.json()["discoveryEngine"] == "universal"

    switch_trans = client.post(f"/api/engagements/{eid}/discovery-engine", json={"engineId": "transform"})
    assert switch_trans.status_code == 200
    assert switch_trans.json()["discoveryEngine"] == "transform"


def test_universal_solution_e2e_with_azure_and_fallback():
    """End-to-End Test for the Universal Solution:
    1. Deterministic AST parsing across AS/400 RPGLE, CLLE, C#, and JCL
    2. Live Azure AI Foundry invocation via Responses API with fallback to Bedrock
    3. Target Clean Hexagonal Architecture synthesis (.NET 9 & Java 21)
    4. Bitwise parity and collation simulation
    """
    from app.as400 import extract_relationships
    from app.llm_gateway import gateway
    from app.bedrock_skills import (
        synthesize_target_codebase,
        simulate_ebcdic_collation_parity,
        get_bidirectional_cdc_status,
    )
    from pathlib import Path

    # Step 1: Ingest polyglot legacy source into AST relationships
    sample_polyglot = """
    // AS/400 RPGLE procedure calling Db2 and CLLE
    DCL-PR POLICY_PROC EXTPGM('POLPGM01');
    END-PR;
    CALLP POLICY_PROC();
    CHAIN (POLID) POLICIESTBL;
    WRITE AUDITLOGTBL;
    """
    facts = extract_relationships(Path("POL01.rpgle"), sample_polyglot)
    assert len(facts) >= 3
    assert any(f["kind"] == "CALLS" and f["target"] == "POLPGM01" for f in facts)
    assert any(f["kind"] == "READS" and f["target"] == "POLICIESTBL" for f in facts)
    assert any(f["kind"] == "WRITES" and f["target"] == "AUDITLOGTBL" for f in facts)

    # Step 2: Live Azure AI Foundry invocation (with automatic Bedrock fallback)
    azure_response = gateway.invoke(
        system_prompt="You are an enterprise cloud modernization assistant.",
        user_prompt="Summarize the modernization goal of legacy COBOL to Java 21 in 5 words.",
        provider="azure",
        max_tokens=30,
        temperature=0.1,
    )
    assert azure_response is not None
    assert len(azure_response.strip()) > 0

    # Step 3: Scaffold Clean Hexagonal Architecture code for Azure (.NET 9 and Java 21)
    mock_scope = {"name": "Motor Policy Domain", "capabilityId": "motor"}
    csharp_code = synthesize_target_codebase(mock_scope, target_tech={"language": "csharp", "framework": "dotnet-9"})
    assert "src/Domain/Entities/Policy.cs" in csharp_code
    assert "src/Infrastructure/Persistence/ModernDbContext.cs" in csharp_code

    java_code = synthesize_target_codebase(mock_scope, target_tech={"language": "java", "framework": "spring-boot-3"})
    assert "src/main/java/com/modernize/domain/model/Policy.java" in java_code
    assert "src/main/java/com/modernize/presentation/PolicyController.java" in java_code

    # Step 4: Verify EBCDIC vs UTF-8 Collation Parity & CDC guardrail
    collation = simulate_ebcdic_collation_parity()
    assert len(collation["testCases"]) > 0
    cdc = get_bidirectional_cdc_status()
    assert cdc["safeRollbackCertified"] is True
