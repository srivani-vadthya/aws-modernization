from app.bedrock_skills import (
    generate_human_action_document,
    modernize_scope,
    select_modernization_engine,
    synthesize_target_codebase,
)


def test_select_modernization_engine_prefers_aws_transform_when_supported():
    scope = {
        "name": "Claims Processing",
        "sourceType": "cobol",
        "programs": [{"id": "CLM001", "name": "Policy Renewal"}],
        "files": [{"path": "src/legacy/policy_update.cbl", "file": "policy_update.cbl"}],
    }
    target = {"language": "java", "framework": "spring", "approved": True}

    selection = select_modernization_engine(scope, target, aws_transform_config={"configured": True, "available": True})

    assert selection["engine"] == "aws-transform"
    assert selection["status"] == "READY"
    assert selection["supportedByAwsTransform"] is True


def test_synthesize_target_codebase_is_source_aware_for_legacy_languages():
    scope = {
        "name": "Claims Processing",
        "files": [
            {
                "path": "src/legacy/policy_update.cbl",
                "file": "policy_update.cbl",
                "content": "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. POLICY-UPDATE.\n       PROCEDURE DIVISION.\n           READ POLICY-FILE\n           IF POLICY-STATUS = 'ACTIVE'\n               MOVE 'UPDATED' TO POLICY-STATUS\n               WRITE POLICY-RECORD\n           END-IF\n           CALL 'CUSTOMER-LOOKUP'\n",
            },
            {
                "path": "src/legacy/policy_status.rpgle",
                "file": "policy_status.rpgle",
                "content": "DCL-F POLICYFILE;\nCHAIN (POLICYNO) POLICYFILE;\nIF %FOUND();\n  UPDATE POLICYFILE;\nENDIF;\nCALLP PROCESS_POLICY();\n",
            },
            {
                "path": "src/legacy/run_claims.clle",
                "file": "run_claims.clle",
                "content": "CALL PGM(CLAIMSJOB) PARM('RUN')\nOVRDBF FILE(POLICYFILE) TOFILE(POLICY)\nSBMJOB CMD(CALL PGM(CLAIMSJOB))\n",
            },
        ],
    }
    target = {
        "language": "python",
        "framework": "fastapi",
        "approved": True,
    }

    result = synthesize_target_codebase(scope, target)

    cobol_file = next(value for key, value in result.items() if key.endswith("policy_update.py"))
    rpgle_file = next(value for key, value in result.items() if key.endswith("policy_status.py"))
    clle_file = next(value for key, value in result.items() if key.endswith("run_claims.py"))

    assert "policy_file" in cobol_file.lower() and "customer_lookup" in cobol_file.lower()
    assert "policyfile" in rpgle_file.lower() and "process_policy" in rpgle_file.lower()
    assert "claimsjob" in clle_file.lower() and "sbmjob" in clle_file.lower()


def test_modernize_scope_tracks_every_selected_component():
    scope = {
        "capabilityId": "claims",
        "name": "Claims Processing",
        "programs": [
            {"id": "CLM001", "name": "Policy Renewal"},
            {"id": "CLM002", "name": "Claim Reserve"},
        ],
        "tables": [{"id": "POLICY", "name": "POLICY"}],
        "files": [{"path": "src/legacy/claims.cbl", "file": "claims.cbl"}],
        "sharedServices": [{
            "resourceId": "CUSTOMER",
            "resourceName": "CUSTOMER",
            "consumers": ["Claims Processing"],
        }],
    }
    target = {
        "language": "python",
        "framework": "fastapi",
        "architecture": "clean-architecture",
        "approved": True,
        "approvedBy": "architect",
    }

    result = modernize_scope(scope, target, engagement={"seed": {"target": target}})

    assert result["selection"]["scopeValidated"] is True
    assert result["traceability"]["selectedPrograms"] == ["Policy Renewal", "Claim Reserve"]
    assert result["traceability"]["selectedTables"] == ["POLICY"]
    assert result["traceability"]["selectedFiles"] == ["src/legacy/claims.cbl"]
    assert len(result["traceability"]["coverage"]) == 4
    assert {item["status"] for item in result["traceability"]["coverage"]} <= {
        "Completed and Validated",
        "Generated – Validation Pending",
        "Partially Modernized",
        "Blocked",
        "Failed",
        "Not Started",
    }


def test_synthesize_target_codebase_converts_each_selected_legacy_file():
    scope = {
        "name": "Claims Processing",
        "files": [
            {"path": "src/legacy/claims.cbl", "file": "claims.cbl"},
            {"path": "src/legacy/policy.rpgle", "file": "policy.rpgle"},
        ],
    }
    target = {
        "language": "python",
        "framework": "fastapi",
        "architecture": "clean-architecture",
        "approved": True,
    }

    result = modernize_scope(scope, target, engagement={"seed": {"target": target}})
    generated_paths = set(result["files"].keys())
    assert any("claims" in path.lower() and path.endswith(".py") for path in generated_paths)
    assert any("policy" in path.lower() and path.endswith(".py") for path in generated_paths)
    assert all("src/legacy/" not in path for path in generated_paths)
    assert all("modernized" in path.lower() or "converted" in path.lower() for path in generated_paths)


def test_synthesize_target_codebase_uses_selected_scope_identity_for_each_module():
    scope_a = {
        "name": "Claims Processing",
        "capabilityId": "claims",
        "programs": [{"id": "CLM001", "name": "Policy Renewal", "path": "src/legacy/policy_renewal.cbl"}],
    }
    scope_b = {
        "name": "Billing Processing",
        "capabilityId": "billing",
        "programs": [{"id": "BILL001", "name": "Premium Calculation", "path": "src/legacy/premium_calc.rpgle"}],
    }
    target = {"language": "python", "framework": "fastapi", "approved": True}

    result_a = synthesize_target_codebase(scope_a, target)
    result_b = synthesize_target_codebase(scope_b, target)

    assert result_a != result_b
    assert any("policy_renewal" in path.lower() for path in result_a)
    assert any("premium_calc" in path.lower() for path in result_b)
    assert "claims" in next(iter(result_a.values())).lower() or "policy_renewal" in next(iter(result_a.values())).lower()
    assert "billing" in next(iter(result_b.values())).lower() or "premium_calc" in next(iter(result_b.values())).lower()


def test_generate_human_action_document_includes_todo_fields():
    todo = generate_human_action_document({
        "name": "Claims Processing",
        "sharedServices": [{
            "resourceName": "CUSTOMER",
            "consumers": ["Claims Processing"],
        }],
    })

    action = todo["actions"][0]
    assert "TODO ID" in action
    assert "Source File / Module" in action
    assert "Target Component" in action
    assert "Issue / Dependency" in action
    assert "Reason" in action
    assert "Required Human Action" in action
    assert "Priority" in action
    assert "Suggested Owner" in action
    assert "Status" in action
    assert "Impact" in action
