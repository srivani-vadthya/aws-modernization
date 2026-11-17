"""Offline regressions for evidence, provider failures, and workflow preservation."""
import copy
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch, MagicMock
import uuid
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient
from app import discovery_report as discovery, store, bedrock_skills, pack, ingest
from app.main import app
from app.phases import PHASE_IDS


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parent / "_discovery_runs"
        self.root = self.test_root / uuid.uuid4().hex
        self.eid = "123456abcdef"
        self.eng_root = self.root / self.eid
        self.source = self.eng_root / "source"
        self.source.mkdir(parents=True)
        self.put("App/App.csproj", '<Project><PropertyGroup><TargetFrameworkVersion>v4.5.2</TargetFrameworkVersion></PropertyGroup><ItemGroup><ProjectReference Include="../Data/Data.csproj" /></ItemGroup></Project>')
        self.put("App/packages.config", '<packages>\n<package id="angularjs" version="1.5.3" />\n<package id="EntityFramework" version="6.1.3" />\n</packages>')
        self.put("App/Policy.cs", 'public class Policy {}\nvar client = new HttpClient();\n')
        self.put("App/Scripts/app/policy.ts", 'app.controller("PolicyCtrl", function() {\n$http.get("/api/policy");\n});')
        self.put("App/Scripts/angular.min.js", 'angular.module("vendor", []);')
        self.put("node_modules/ignored.js", 'ignored')
        self.put(".env", 'SECRET_TOKEN=must-never-enter-evidence')
        self.eng = {"id": self.eid, "name": "Test", "sourceType": "git", "currentPhase": "discovery", "status": "discovery",
            "gates": {p: {"decision": "approved" if p == "intake" else None, "status": "ready"} for p in PHASE_IDS},
            "scope": None, "seed": {"capabilities": [{"id": "policy", "name": "Policy", "coupling": "test", "risk": "test"}],
            "programs": [{"id": "policy:App/Policy.cs", "capability": "policy"}], "tables": [], "graph": {"edges": []}}}
        self.path = self.eng_root / "engagement.json"
        self.path.write_text(json.dumps(self.eng), encoding="utf-8")
        self.patcher = patch.object(store, "ENG_DIR", self.root)
        self.patcher.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.patcher.stop()
        target = self.root.resolve()
        assert target.is_relative_to(self.test_root.resolve()) and target != self.test_root.resolve()
        shutil.rmtree(target)

    def put(self, name, text):
        p = self.source / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def scan(self):
        return discovery.scan(self.source, self.eng)

    def test_measured_source_and_frontend_evidence(self):
        r = self.scan()
        self.assertEqual(r["projects"][0]["framework"], "v4.5.2")
        self.assertEqual(len(r["dependencies"]), 2)
        self.assertIsNone(r["summary"]["coverage"])
        self.assertEqual(len(r["integrations"]), 2)
        self.assertTrue(any(d["name"] == "controller PolicyCtrl" for d in r["declarations"]))
        self.assertFalse(any("vendor" in d["name"] for d in r["declarations"]))
        self.assertNotIn("must-never-enter-evidence", json.dumps(r))
        for e in r["evidence"]:
            self.assertTrue((self.source / e["path"]).is_file())
            self.assertGreaterEqual(e["line"], 1)

    def mock_response(self, content, status=200):
        response = MagicMock(status_code=status)
        response.json.return_value = {"output": {"message": {"content": [{"text": json.dumps(content)}]}},
                                      "usage": {"inputTokens": 120, "outputTokens": 40}}
        client = MagicMock()
        client.__enter__.return_value.post.return_value = response
        return client

    def test_ai_rejects_fabricated_evidence_and_records_usage(self):
        r = self.scan()
        eid = r["evidence"][0]["id"]
        client = self.mock_response({"interpretations": [{"title": "Source declares a supported framework lead", "evidenceIds": [eid]},
            {"title": "short cautious finding", "evidenceIds": [eid]},
            {"title": "Invented", "evidenceIds": ["E99999"]}]})
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test-only"}), patch.object(discovery.httpx, "Client", return_value=client):
            discovery.interpret(r)
        self.assertEqual(len(r["ai"]["interpretations"]), 1)
        self.assertEqual(r["telemetry"][0]["inputTokens"], 120)
        self.assertIsNone(r["telemetry"][0]["costUsd"])

    def test_bedrock_failure_keeps_facts_and_no_fallback(self):
        r = self.scan()
        facts = copy.deepcopy(r["dependencies"])
        client = self.mock_response({}, 403)
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test-only"}), patch.object(discovery.httpx, "Client", return_value=client):
            discovery.interpret(r)
        self.assertEqual(r["dependencies"], facts)
        self.assertEqual(r["telemetry"][0]["status"], "HTTP 403")
        self.assertEqual(client.__enter__.return_value.post.call_count, 1)

    def test_reports_and_comments_do_not_mutate_engagement(self):
        original = self.path.read_bytes()
        base = f"/api/engagements/{self.eid}"
        self.assertEqual(self.client.get(base+"/discovery-report").status_code, 200)
        self.assertEqual(self.client.post(base+"/discovery-comments", json={"section": "modules", "text": "Review policy"}).status_code, 200)
        r = self.client.post(base+"/discovery-report", json={"useBedrock": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["comments"][0]["text"], "Review policy")
        self.assertEqual(self.path.read_bytes(), original)

    def test_changed_source_invalidates_ai(self):
        base = f"/api/engagements/{self.eid}/discovery-report"
        self.client.get(base)
        path = self.eng_root / "discovery-report.json"
        r = json.loads(path.read_text())
        r["ai"] = {"status": "Completed", "interpretations": [{"title": "Old interpretation"}]}
        path.write_text(json.dumps(r), encoding="utf-8")
        self.put("App/New.cs", "public class NewType {}")
        changed = self.client.get(base).json()
        self.assertNotEqual(changed["sourceDigest"], r["sourceDigest"])
        self.assertEqual(changed["ai"]["status"], "Not run")

    def test_approval_sequence_is_preserved(self):
        base = f"/api/engagements/{self.eid}"
        self.client.get(base+"/discovery-report")
        self.assertEqual(self.client.post(base+"/gates/discovery", json={"decision": "approved"}).status_code, 200)
        self.assertEqual(self.client.post(base+"/gates/scope", json={"decision": "approved"}).status_code, 400)
        with patch.object(bedrock_skills, "extract_dynamic_requirements", return_value=None), patch("app.main.playwright_gen.generate_playwright_suite"):
            self.assertEqual(self.client.post(base+"/scope", json={"capabilityId": "policy"}).status_code, 200)
            response = self.client.post(base+"/gates/scope", json={"decision": "approved"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["currentPhase"], "semantic-ir")

    def test_missing_source_and_invalid_engagement_are_clear(self):
        self.assertEqual(self.client.get('/api/engagements/not-an-id/discovery-report').status_code, 404)
        empty = self.root / "empty"
        with self.assertRaises(ValueError):
            discovery.scan(empty, self.eng)

    def test_classification_keeps_totals_and_requires_evidence(self):
        self.put("App/Scripts/angular.min.js", "/*! AngularJS v1.5.3 License MIT */\nangular.module('vendor', []);")
        self.put("App/Scripts/app/policy.js", "app.controller('PolicyCtrl',function(){});")
        self.put("App/Scripts/app/policy.js.map", json.dumps({"sources": ["policy.ts"]}))
        r = self.scan()
        assets = {a["path"]: a for a in r["assets"]}
        self.assertEqual(assets["App/Scripts/angular.min.js"]["category"], "vendor")
        self.assertEqual(assets["App/Scripts/app/policy.js"]["category"], "generated")
        self.assertEqual(sum(v["files"] for v in r["summary"]["breakdown"].values()), r["summary"]["files"])
        self.assertEqual(sum(v["loc"] for v in r["summary"]["breakdown"].values()), r["summary"]["loc"])
        self.assertLess(r["summary"]["applicationFiles"], r["summary"]["files"])

    def test_integration_grouping_preserves_evidence(self):
        self.put("App/Another.cs", "var http = new HttpClient();")
        r = self.scan()
        self.assertEqual(len(r["integrations"]), 3)
        self.assertEqual(len(r["integrationGroups"]), 2)
        self.assertEqual(sum(g["referenceCount"] for g in r["integrationGroups"]), 3)
        self.assertEqual(set(e for g in r["integrationGroups"] for e in g["evidenceIds"]),
                         set(e for g in r["integrations"] for e in g["evidenceIds"]))

    def test_automatic_review_is_cached_but_comments_trigger_new_review(self):
        url = f"/api/engagements/{self.eid}/discovery-report"
        def fake(report, comments):
            report["ai"] = {"status": "Completed", "interpretations": []}
            return report
        with patch.object(discovery, "interpret", side_effect=fake) as invoke:
            for _ in range(2):
                self.assertEqual(self.client.post(url, json={"useBedrock": True, "onlyIfNeeded": True}).status_code, 200)
                self.client.get(url)
            self.assertEqual(invoke.call_count, 1)
            self.client.post(f"/api/engagements/{self.eid}/discovery-comments", json={"section":"overview", "text":"Review updated evidence"})
            self.client.post(url, json={"useBedrock": True, "onlyIfNeeded": True})
            self.assertEqual(invoke.call_count, 2)

    def test_approval_projects_real_files_and_pack_exports_json(self):
        self.put("App/extra/detail.ts", "class Detail {}")
        base = f"/api/engagements/{self.eid}"
        self.client.post(base+"/discovery-comments", json={"section": "overview", "text": "Checked"})
        response = self.client.post(base+"/gates/discovery", json={"decision": "approved"})
        self.assertEqual(response.status_code, 200)
        eng = response.json()
        self.assertIn("sourceDiscovery", eng)
        self.assertTrue(any(p.get("path") == "App/extra/detail.ts" for p in eng["seed"]["programs"]))
        node_ids = {n["id"] for n in eng["seed"]["graph"]["nodes"]}
        self.assertTrue(all(e["source"] in node_ids and e["target"] in node_ids for e in eng["seed"]["graph"]["edges"]))
        self.assertTrue(eng["seed"]["semantic_ir"])
        self.assertTrue(any(sir.get("rules") for sir in eng["seed"]["semantic_ir"]))
        with patch.object(pack.playwright_gen, "generate_playwright_suite"), patch.object(pack.bedrock_skills, "generate_srs_markdown", return_value="Test"), patch.object(pack.bedrock_skills, "generate_c4_architecture_markdown", return_value="Test"):
            data = pack.build_pack(eng)
        with zipfile.ZipFile(BytesIO(data)) as z:
            for name in ["discovery", "discovery-approved", "discovery-evidence", "discovery-comments", "discovery-declarations", "discovery-graph", "discovery-provenance", "graph"]:
                json.loads(z.read(f"artifacts/{name}.json"))
            self.assertEqual(json.loads(z.read("artifacts/discovery-comments.json"))[0]["text"], "Checked")
            self.assertEqual(json.loads(z.read("artifacts/graph.json")), eng["seed"]["graph"])
            self.assertTrue(json.loads(z.read("artifacts/discovery-provenance.json"))["sourceMatchesApproval"])

    def test_other_repository_inventory_is_not_presented_as_dotnet_analysis(self):
        self.put("service/main.py", "def main():\n    return 1\n")
        self.put("service/package.json", '{"dependencies":{"react":"18.3.1"}}')
        r = self.scan()
        self.assertIn("Python", r["analysisCoverage"]["unsupportedLanguages"])
        self.assertTrue(any(d["name"] == "react" for d in r["dependencies"]))
        self.assertFalse(any(d["path"] == "service/main.py" for d in r["declarations"]))

    def test_clone_opens_discovery_without_manual_intake_approval(self):
        def clone(cmd, **kwargs):
            dest = Path(cmd[-1])
            self.assertTrue(dest.resolve().is_relative_to(self.root.resolve()))
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "Policy.java").write_text("public class Policy {}", encoding="utf-8")
        with patch.object(ingest.subprocess, "run", side_effect=clone):
            response = self.client.post("/api/engagements/git", json={"url": "https://example.com/test.git"})
        self.assertEqual(response.status_code, 200)
        eng = response.json()
        self.assertEqual(eng["currentPhase"], "discovery")
        self.assertEqual(eng["status"], "discovery")
        self.assertEqual(eng["inventory"]["assetCount"], 1)
        self.assertEqual(eng["gates"]["intake"]["status"], "completed")
        self.assertIsNone(eng["gates"]["intake"]["decision"])
        self.assertEqual(eng["gates"]["discovery"]["status"], "ready")
        base = f"/api/engagements/{eng['id']}"
        self.assertEqual(self.client.post(base+"/gates/scope", json={"decision":"approved"}).status_code, 400)
        approved = self.client.post(base+"/gates/discovery", json={"decision":"approved", "comment":"Source checked"})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["currentPhase"], "scope")
        self.assertEqual(approved.json()["gates"]["discovery"]["comment"], "Source checked")

    def test_legacy_intake_engagement_can_approve_discovery(self):
        eng = copy.deepcopy(self.eng)
        eng["inventory"] = {"assets": [], "assetCount": 0}
        eng["currentPhase"] = "intake"
        eng["gates"]["intake"] = {"status":"ready", "decision":None}
        self.path.write_text(json.dumps(eng), encoding="utf-8")
        response = self.client.post(f"/api/engagements/{self.eid}/gates/discovery", json={"decision":"approved"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["currentPhase"], "scope")

    def test_discovery_still_requires_successful_inventory(self):
        eng = copy.deepcopy(self.eng)
        eng["inventory"] = None
        eng["gates"]["intake"]["decision"] = None
        self.path.write_text(json.dumps(eng), encoding="utf-8")
        response = self.client.post(f"/api/engagements/{self.eid}/gates/discovery", json={"decision":"approved"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
