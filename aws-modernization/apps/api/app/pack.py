from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from fastapi import HTTPException

from . import bedrock_skills, generated_dotnet, playwright_gen, store


def is_dotnet_target(eng: dict) -> bool:
    seed = eng.get("seed") or {}
    target = seed.get("target") or {}
    lang = (target.get("language") or "").lower()
    stack = (target.get("stack") or "").lower()
    arch = (target.get("architecture") or "").lower()
    name = (eng.get("name") or "").lower()
    return any("c#" in s or ".net" in s or "dotnet" in s for s in (lang, stack, arch, name))


def build_pack(eng: dict) -> bytes:
    buf = BytesIO()
    root = store.engagement_dir(eng["id"])
    from .discovery_routes import get_report, read
    report = get_report(eng["id"])
    if report["ai"]["status"] == "Running":
        raise HTTPException(409, "Discovery is running. Download the artifact pack when it completes.")
    approved = read(root / "artifacts" / "discovery-approved.json", None)
    
    # Ensure Playwright suite is written to artifacts/tests/playwright
    pw_dir = root / "artifacts" / "tests" / "playwright"
    playwright_gen.generate_playwright_suite(pw_dir, eng)

    dotnet_engagement = is_dotnet_target(eng)

    # Ensure modernized service skeleton exists in artifacts
    if dotnet_engagement:
        dotnet_gen_dir = root / "artifacts" / "ims-modernized-service"
        generated_dotnet.write_dotnet_generated(dotnet_gen_dir)
    else:
        # For GenApp or default Java engagements
        spring_gen_dir = root / "artifacts" / "motor-policy-service"
        if not spring_gen_dir.exists() and eng.get("sample"):
            from .generated import write_generated
            write_generated(spring_gen_dir)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("engagement.json", json.dumps({k: v for k, v in eng.items() if k != "seed"}, indent=2))
        
        # Golden SRS and Architecture Specifications
        zf.writestr("specifications/SRS.md", bedrock_skills.generate_srs_markdown(eng))
        zf.writestr("architecture/target-architecture.md", bedrock_skills.generate_c4_architecture_markdown(eng))

        if eng.get("seed"):
            zf.writestr("artifacts/discovery.json", json.dumps(report, indent=2))
            zf.writestr("artifacts/discovery-evidence.json", json.dumps({"sourceDigest": report["sourceDigest"], "evidence": report["evidence"], "assets": report["assets"]}, indent=2))
            zf.writestr("artifacts/discovery-comments.json", json.dumps(report.get("comments", []), indent=2))
            zf.writestr("artifacts/discovery-declarations.json", json.dumps({"status": "Lexical declarations; AST not generated", "sourceDigest": report["sourceDigest"], "declarations": report["declarations"]}, indent=2))
            zf.writestr("artifacts/discovery-graph.json", json.dumps(report["graph"], indent=2))
            if approved:
                zf.writestr("artifacts/discovery-approved.json", json.dumps(approved, indent=2))
            zf.writestr("artifacts/discovery-provenance.json", json.dumps({"currentSourceDigest": report["sourceDigest"],
                "approvedSourceDigest": approved.get("sourceDigest") if approved else None,
                "sourceMatchesApproval": bool(approved and approved.get("sourceDigest") == report["sourceDigest"]),
                "downstreamSnapshot": eng.get("sourceDiscovery"), "analysisCoverage": report["analysisCoverage"], "limits": report["limits"]}, indent=2))
            zf.writestr("artifacts/requirements.json", json.dumps(eng["seed"].get("requirements"), indent=2))
            zf.writestr("artifacts/backlog.json", json.dumps(eng["seed"].get("backlog"), indent=2))
            zf.writestr("artifacts/graph.json", json.dumps(approved["graph"] if approved else report["graph"], indent=2))
            zf.writestr("artifacts/target.json", json.dumps(eng["seed"].get("target"), indent=2))
            zf.writestr("artifacts/tests.json", json.dumps(eng["seed"].get("tests"), indent=2))
            zf.writestr("artifacts/failures.json", json.dumps(eng["seed"].get("failures"), indent=2))
        
        # Modernized Target Service (.NET 8 or Spring Boot)
        if dotnet_engagement:
            gen = root / "artifacts" / "ims-modernized-service"
            if gen.exists():
                for path in gen.rglob("*"):
                    if path.is_file():
                        zf.write(path, Path("generated/ims-modernized-service") / path.relative_to(gen))
        else:
            gen = root / "artifacts" / "motor-policy-service"
            if gen.exists():
                for path in gen.rglob("*"):
                    if path.is_file():
                        zf.write(path, Path("generated/motor-policy-service") / path.relative_to(gen))
                    
        # Playwright Automated Test Suite
        if pw_dir.exists():
            for path in pw_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, Path("tests/playwright") / path.relative_to(pw_dir))

        # Infrastructure as Code (Azure WebApps & PostgreSQL Flexible Server) + CI/CD Workflow
        from . import iac_generator
        azure_tf = iac_generator.generate_azure_terraform(eng)
        for tf_path, tf_content in azure_tf.items():
            zf.writestr(tf_path, tf_content)

        gh_actions = iac_generator.generate_github_workflow(target_cloud="azure")
        for wf_path, wf_content in gh_actions.items():
            zf.writestr(wf_path, wf_content)

        generated_service_desc = (
            "- `/generated/ims-modernized-service/`: Cloud-native C# .NET 8 WebAPI & React 18 TypeScript frontend service skeleton.\n"
            if dotnet_engagement
            else "- `/generated/motor-policy-service/`: Cloud-native Spring Boot service skeleton.\n"
        )

        zf.writestr(
            "README.md",
            "# Nexus Modernize Delivery Pack\n\n"
            "This package contains the complete hand-off deliverables:\n"
            "- `/specifications/SRS.md`: Formal business requirements extracted from the legacy estate.\n"
            "- `/architecture/target-architecture.md`: Cloud-native C4 architecture blueprint.\n"
            f"{generated_service_desc}"
            "- `/terraform/azure/`: Production-ready Terraform IaC for Azure Web Apps (Linux) & PostgreSQL Flexible Server.\n"
            "- `/.github/workflows/`: Automated GitHub Actions CI/CD pipeline (tests, parity check, and deploy).\n"
            "- `/tests/playwright/`: Complete Playwright E2E and API contract test suite.\n"
            "- `/artifacts/`: Structured JSON feeds for CI/CD, Azure DevOps, and Jira intake.\n"
            "- `/artifacts/discovery.json`: Current source-backed report with counts, classification and AI interpretation labels.\n"
            "- `/artifacts/discovery-approved.json`: Last approved snapshot, when available; graph.json follows this snapshot.\n"
            "- `/artifacts/discovery-evidence.json`: Source references and per-file classification reasons.\n"
            "- `/artifacts/discovery-comments.json`: Discovery review comments.\n"
            "- `/artifacts/discovery-provenance.json`: Current/approved source fingerprints and analysis limitations.\n\n"
            "Discovery declarations are lexical leads, not a compiler AST. Other generated templates and specifications require validation; this ZIP is not proof of production readiness or passing tests.\n",
        )
    return buf.getvalue()
