from app.target_contract import validate_target_contract
from app.bedrock_skills import synthesize_target_codebase


def test_target_contract_normalizes_csharp_dotnet10():
    target = validate_target_contract({
        "language": "C# (.NET 10)",
        "framework": "aspnetcore",
        "architecture": "Clean Architecture",
        "approved": True,
        "approvedBy": "architect",
    })
    assert target["language"] == "csharp"
    assert target["framework"] == "aspnetcore"
    assert target["approvalStatus"] == "APPROVED"
    assert "configurationDigest" in target


def test_target_contract_rejects_java_csharp_mismatch():
    try:
        validate_target_contract({"language": "csharp", "framework": "spring-boot", "approved": True})
        assert False, "expected validation failure"
    except ValueError:
        pass


def test_target_contract_preserves_structured_architecture_and_data_choices():
    target = validate_target_contract({
        "language": "csharp", "framework": "aspnetcore", "frameworkVersion": "8",
        "runtime": "dotnet", "runtimeVersion": "8", "architecture": "clean-architecture",
        "apiApproach": "controllers", "frontendRequirement": "react", "data": "sql server",
        "dataAccessTechnology": "Entity Framework Core", "orm": "EF Core",
        "migrationStrategy": "versioned migrations", "integrationRequirements": "OIDC and event contracts",
        "approved": True, "approvedBy": "reviewer",
    })
    assert target["apiApproach"] == "controllers"
    assert target["dataAccessTechnology"] == "Entity Framework Core"
    assert target["orm"] == "EF Core"
    assert target["migrationStrategy"] == "versioned migrations"
    assert target["integrationRequirements"] == "OIDC and event contracts"
def test_target_codegen_respects_dotnet10_contract():
    files = synthesize_target_codebase({"name": "Claims"}, {
        "language": "csharp",
        "framework": "aspnetcore",
        "frameworkVersion": "10",
        "architecture": "clean-architecture",
    })
    assert "Policy.csproj" in files
    assert "net10.0" in files["Policy.csproj"]
    assert "spring" not in files["Policy.csproj"].lower()


def test_target_codegen_missing_contract_is_rejected():
    try:
        synthesize_target_codebase({"name": "Claims"}, {})
        assert False, "expected missing target contract failure"
    except ValueError:
        pass
