"""Test Scenarios: user stories + acceptance criteria -> QA assets.

Everything is derived deterministically from the approved backlog, so the result is repeatable and traceable:

  * every acceptance criterion ("Given ..., when ..., then ... (R2, R4)") becomes one scenario, classified as
    positive / negative / validation / edge / exception from its wording;
  * nothing is added beyond the criteria: no canned or default scenarios, so a story with no negative criterion
    simply has no negative test, and the business sees exactly what the stories say;
  * each scenario gets a detailed test case (preconditions, steps, data, expected results);
  * the test cases become a Playwright (TypeScript) project: page object, shared test data, one spec per feature;
  * test data requirements and a story / criterion coverage matrix are built from the same cases.

`run()` has two parts. The quality checks always run (no application needed) and prove each case is complete,
traceable and present in the generated script. A live run executes the Playwright project against a base URL when
Node and the project's dependencies are installed; otherwise it reports exactly what is missing. A live run is
never simulated.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import store

SKILL_SCRIPTS = Path(__file__).resolve().parents[3] / ".agents" / "skills" / "sir-user-story-generator" / "scripts"

CATEGORIES = ("positive", "negative", "validation", "edge", "exception")
MAX_RUNS = 10

_CRITERION = re.compile(r"^\s*given\s+(?P<given>.*?),?\s+when\s+(?P<when>.*?),?\s+then\s+(?P<then>.*?)\s*$", re.I | re.S)
_REFS = re.compile(r"\(([^()]*\bR[-\w]*\d[^()]*)\)\s*\.?\s*$")
_QUOTED = re.compile(r"\"([^\"]+)\"")
_PLACEHOLDER = re.compile(r"<([^<>]+)>")
_WRITES = re.compile(r"\b(saved|added|updated|deleted|created|recorded|stored|removed|submitted)\b", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def out_dir(eid: str) -> Path:
    d = store.engagement_dir(eid) / "artifacts" / "tests" / "test-scenarios"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stories(eng: dict) -> list[tuple[dict, dict, dict]]:
    backlog = (eng.get("userStories") or {}).get("backlog") or {}
    return [(ep, f, s) for ep in backlog.get("epics", []) for f in ep.get("features", []) for s in f.get("stories", [])]


def source_digest(eng: dict) -> str:
    """Changes whenever a story or one of its acceptance criteria changes (so the UI can flag stale tests)."""
    payload = [[s["id"], s.get("title"), list(s.get("acceptanceCriteria", []))] for _, _, s in _stories(eng)]
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- criteria -> scenarios

def parse_criterion(text: str) -> dict:
    """'Given A, when B, then C (R2, R4)' -> {given, when, then, refs}. Gherkin 'Scenario:' lines keep the whole text."""
    t = " ".join(str(text).split())
    refs: list[str] = []
    m = _REFS.search(t)
    if m:
        refs = [r.strip() for r in m.group(1).split(",") if r.strip()]
        t = t[:m.start()].rstrip()
    p = _CRITERION.match(t)
    if p:
        return {"given": p["given"].strip(), "when": p["when"].strip(), "then": p["then"].strip().rstrip("."), "refs": refs}
    return {"given": "the preconditions of the scenario hold", "when": "the user performs the action",
            "then": re.sub(r"^scenario( outline)?:\s*", "", t, flags=re.I).rstrip("."), "refs": refs}


def classify(parts: dict) -> str:
    """Category from the wording of the criterion. Order matters: the most specific signal wins."""
    whole = f"{parts['given']} {parts['when']} {parts['then']}".lower()
    then = parts["then"].lower()
    if re.search(r"anything goes wrong|\bfails?\b|failure|unable to|could not|cannot be saved|unexpected", whole):
        return "exception"
    if re.search(r"not valid|invalid|\bmissing\b|\brequired\b|\bno [\w ]+ (is|are) (given|chosen|entered|provided)\b|"
                 r"details are not|is empty|left blank|not entered", whole):
        return "validation"
    if re.search(r"refused|rejected|\berror\b|not found|denied|not allowed|\bcannot\b|is not permitted|"
                 r"already exists|duplicate|message .* is shown", then):
        return "negative"
    if re.search(r"\bexactly\b|\bat (least|most)\b|more than \d|less than \d|\bone\b.*\bmore than one\b|"
                 r"\bno [\w ]+ exist|\bfirst\b|\blast\b|\bzero\b|\b0\b|\bonly one\b", whole):
        return "edge"
    return "positive"


def _goal(story: dict) -> str:
    i_want = str((story.get("narrative") or {}).get("iWant") or story.get("title") or "complete the use case").strip()
    return re.sub(r"^to\s+", "", i_want, flags=re.I).rstrip(".")


def _persona(story: dict) -> str:
    return str((story.get("narrative") or {}).get("asA") or "business user").strip()


def _numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"(?<![\w.<])(\d{1,6})(?![\w.>])", text) if int(n) < 1_000_000]


def _case_for(case_id: str, scenario: dict, story: dict, feature: dict, parts: dict) -> dict:
    persona = _persona(story)
    given, when, then = [parts["given"]], parts["when"], [parts["then"]]
    source = " ".join([*given, when, *then])
    data: list[dict] = []
    seen: set[str] = set()
    for name in _PLACEHOLDER.findall(source):
        if name not in seen:
            seen.add(name)
            data.append({"name": name, "value": f"<{name}>", "source": "to be supplied"})
    for lit in _QUOTED.findall(source):
        if lit not in seen:
            seen.add(lit)
            data.append({"name": f"value \"{lit[:40]}\"", "value": lit, "source": "from the acceptance criterion"})
    steps = [f"Sign in as a {persona}.",
             f"Open the \"{feature['title']}\" area of the application.",
             *[f"Make sure that {g}." for g in given],
             f"Action: {when[:1].upper() + when[1:]}.",
             *[f"Check that {t}." for t in then]]
    return {
        "id": case_id, "scenarioId": scenario["id"], "storyId": story["id"], "name": scenario["title"],
        "category": scenario["category"], "priority": story.get("priority") or "Should",
        "description": f"Checks the acceptance criterion: {scenario['criterion']}",
        "preconditions": [f"A {persona} account exists and can sign in.", *[g[:1].upper() + g[1:] + "." for g in given]],
        "steps": steps, "testData": data, "expected": [t[:1].upper() + t[1:] + "." for t in then],
        "ruleRefs": scenario["ruleRefs"], "origin": scenario["origin"], "needsReview": scenario["needsReview"],
        "automated": True,
    }


def build(eng: dict) -> dict:
    """Scenarios, cases, test data and coverage for every story of the approved backlog."""
    stories = _stories(eng)
    if not stories:
        raise ValueError("Generate the user stories first: test scenarios are built from their acceptance criteria")
    scenarios: list[dict] = []
    cases: list[dict] = []
    coverage: list[dict] = []
    for epic, feature, story in stories:
        parsed = []
        for i, raw in enumerate(story.get("acceptanceCriteria", [])):
            parts = parse_criterion(raw)
            parsed.append({"index": i, "raw": raw, "parts": parts, "category": classify(parts)})
        cov = {"storyId": story["id"], "title": story["title"], "feature": feature["title"], "epic": epic["title"],
               "criteria": []}
        for c in parsed:
            sid = f"TS-{len(scenarios) + 1:03d}"
            title = c["parts"]["then"][:110]
            scenario = {"id": sid, "storyId": story["id"], "storyTitle": story["title"], "feature": feature["title"],
                        "epic": epic["title"], "title": title[:1].upper() + title[1:], "category": c["category"],
                        "origin": "criterion", "criterionIndex": c["index"], "criterion": c["raw"],
                        "ruleRefs": c["parts"]["refs"], "needsReview": False, "caseIds": []}
            case = _case_for(f"TC-{len(cases) + 1:03d}", scenario, story, feature, c["parts"])
            scenario["caseIds"].append(case["id"])
            scenarios.append(scenario)
            cases.append(case)
            cov["criteria"].append({"index": c["index"], "text": c["raw"], "category": c["category"],
                                    "scenarioIds": [sid]})
        cov["scenarioIds"] = [s["id"] for s in scenarios if s["storyId"] == story["id"]]
        cov["byCategory"] = {k: sum(1 for s in scenarios if s["storyId"] == story["id"] and s["category"] == k)
                             for k in CATEGORIES}
        cov["covered"] = all(c["scenarioIds"] for c in cov["criteria"]) and bool(cov["criteria"])
        coverage.append(cov)
    return {"scenarios": scenarios, "cases": cases, "testData": _test_data(cases), "coverage": coverage}


def _test_data(cases: list[dict]) -> list[dict]:
    """Test data requirements: accounts per role, then every value or placeholder the cases need."""
    items: dict[tuple, dict] = {}
    for c in cases:
        role = re.match(r"Sign in as a (.+?)\.", c["steps"][0])
        entries = [{"kind": "account", "name": f"{role.group(1)} account" if role else "user account",
                    "value": "an active account that can sign in", "source": "to be supplied"}]
        entries += [{"kind": "literal" if d["source"] != "to be supplied" else "input", **d} for d in c["testData"]]
        for e in entries:
            key = (e["kind"], e["name"], e["value"])
            row = items.setdefault(key, {**e, "usedBy": []})
            row["usedBy"].append(c["id"])
    out = list(items.values())
    for i, row in enumerate(out, 1):
        row["id"] = f"TD-{i:03d}"
    return out


# --------------------------------------------------------------------------- Playwright project

def _ts(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:48] or "feature"


def playwright_files(eng: dict, model: dict) -> dict[str, str]:
    """A small Playwright (TypeScript) project: config, page object, shared data and one spec per feature."""
    scope = eng.get("scope") or {}
    name = scope.get("name") or eng.get("name") or "application"
    files: dict[str, str] = {}
    files["package.json"] = json.dumps({
        "name": f"{_slug(name)}-acceptance-tests", "private": True, "version": "1.0.0",
        "scripts": {"test": "playwright test", "test:headed": "playwright test --headed",
                    "test:ui": "playwright test --ui", "report": "playwright show-report"},
        "devDependencies": {"@playwright/test": "^1.49.0", "@types/node": "^22.0.0", "typescript": "^5.6.0"},
    }, indent=2) + "\n"
    files["tsconfig.json"] = json.dumps({"compilerOptions": {
        "target": "ES2022", "module": "ESNext", "moduleResolution": "Bundler", "strict": True,
        "esModuleInterop": True, "skipLibCheck": True, "types": ["node"]}, "include": ["**/*.ts"]}, indent=2) + "\n"
    files["playwright.config.ts"] = """import { defineConfig, devices } from '@playwright/test';

// Set SERVICE_BASE_URL to the application under test (the modernized target, or the legacy system for parity runs).
export default defineConfig({
  testDir: './specs',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: [['list'], ['html', { open: 'never' }], ['json', { outputFile: 'test-results/report.json' }]],
  use: {
    baseURL: process.env.SERVICE_BASE_URL ?? 'http://localhost:8080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
"""
    files["pages/AppPage.ts"] = """import { expect, type Locator, type Page } from '@playwright/test';

/**
 * Page object for the application under test.
 * Locators prefer accessible roles and labels, then data-testid. Adjust them here once, never in the specs.
 */
export class AppPage {
  constructor(private readonly page: Page) {}

  async signInAs(role: string): Promise<void> {
    await this.page.goto('/');
    const user = process.env[`TEST_USER_${role.toUpperCase().replace(/\\W+/g, '_')}`];
    const password = process.env.TEST_PASSWORD;
    if (user && password) {
      await this.page.getByLabel(/user(name)?|email/i).fill(user);
      await this.page.getByLabel(/password/i).fill(password);
      await this.page.getByRole('button', { name: /sign in|log in/i }).click();
    }
  }

  async openArea(area: string): Promise<void> {
    const link = this.page.getByRole('link', { name: area }).or(this.page.getByRole('button', { name: area }));
    await link.first().click();
  }

  /** Fills each field found by its visible label; fields that are not on the page are reported, not ignored. */
  async fillDetails(details: Record<string, string>): Promise<void> {
    for (const [label, value] of Object.entries(details)) {
      const field: Locator = this.page.getByLabel(new RegExp(label, 'i')).first();
      await expect(field, `field "${label}" is on the page`).toBeVisible();
      await field.fill(value);
    }
  }

  async submit(): Promise<void> {
    await this.page.getByRole('button', { name: /save|submit|create|confirm|search|continue/i }).first().click();
  }

  /** The text of a message, a confirmation or a result row. */
  async expectText(text: string): Promise<void> {
    await expect(this.page.getByText(text, { exact: false }).first()).toBeVisible();
  }

  /** For outcomes without quoted text: the application must show an alert or a status message. */
  async expectFeedback(): Promise<void> {
    await expect(this.page.getByRole('alert').or(this.page.getByRole('status')).first()).toBeVisible();
  }
}
"""
    data = {d["id"]: d["value"] for d in model["testData"]}
    files["fixtures/test-data.ts"] = (
        "// Test data requirements. Values wrapped in <> are placeholders: replace them before running.\n"
        f"export const testData: Record<string, string> = {_ts(data)};\n\n"
        "export const roleOf = (label: string): string => label.trim();\n")
    files["fixtures/app.ts"] = (
        "import { test as base } from '@playwright/test';\n"
        "import { AppPage } from '../pages/AppPage';\n\n"
        "export const test = base.extend<{ app: AppPage }>({\n"
        "  app: async ({ page }, use) => { await use(new AppPage(page)); },\n"
        "});\n"
        "export { expect } from '@playwright/test';\n")
    by_story = {}
    for c in model["cases"]:
        by_story.setdefault(c["storyId"], []).append(c)
    by_feature: dict[str, list] = {}
    for epic, feature, story in _stories(eng):
        by_feature.setdefault(feature["title"], []).append(story)
    used: set[str] = set()
    for feature_title, stories in by_feature.items():
        lines = ["import { test } from '../fixtures/app';", "import { testData } from '../fixtures/test-data';", "",
                 f"test.describe({_ts(feature_title)}, () => {{"]
        for story in stories:
            lines += [f"  test.describe({_ts(story['id'] + ' - ' + story['title'])}, () => {{"]
            for c in by_story.get(story["id"], []):
                tags = [f"@{c['category']}"] + (["@needs-review"] if c["needsReview"] else [])
                title = "[" + c["id"] + "] " + c["name"]
                lines += [f"    test({_ts(title)}, {{ tag: {_ts(tags)} }}, async ({{ app }}) => {{",
                          "      // " + (f"Criterion: {c['description'].split(': ', 1)[-1]}" if not c["needsReview"]
                                         else "Derived scenario: confirm the expected result with the business."),
                          f"      // Trace: {c['storyId']} {', '.join(c['ruleRefs'])}".rstrip()]
                role = re.match(r"Sign in as a (.+?)\.", c["steps"][0])
                lines += [f"      await test.step({_ts('Sign in and open ' + feature_title)}, async () => {{",
                          f"        await app.signInAs({_ts(role.group(1) if role else 'user')});",
                          f"        await app.openArea({_ts(feature_title)});", "      });"]
                for pre in c["preconditions"][1:]:
                    lines += [f"      await test.step({_ts('Given: ' + pre)}, async () => {{",
                              "        // Prepare this precondition (test data, API set-up or UI steps).", "      });"]
                inputs = [d for d in c["testData"] if d["source"] == "to be supplied"]
                lines += [f"      await test.step({_ts(c['steps'][-len(c['expected']) - 1])}, async () => {{"]
                if inputs:
                    ids = {d["name"]: next(x["id"] for x in model["testData"]
                                           if x["name"] == d["name"] and x["value"] == d["value"]) for d in inputs}
                    fields = ", ".join(f"{_ts(n)}: testData[{_ts(i)}]" for n, i in ids.items())
                    lines.append(f"        await app.fillDetails({{ {fields} }});")
                lines += ["        await app.submit();", "      });"]
                for exp in c["expected"]:
                    quoted = _QUOTED.findall(exp)
                    lines += [f"      await test.step({_ts('Then: ' + exp)}, async () => {{"]
                    lines += ([f"        await app.expectText({_ts(q)});" for q in quoted] if quoted
                              else ["        await app.expectFeedback();"])
                    lines += ["      });"]
                lines += ["    });", ""]
            lines += ["  });"]
        lines += ["});", ""]
        fname = f"specs/{_slug(feature_title)}.spec.ts"
        n = 2
        while fname in used:
            fname, n = f"specs/{_slug(feature_title)}-{n}.spec.ts", n + 1
        used.add(fname)
        files[fname] = "\n".join(lines)
    files["README.md"] = (
        f"# Acceptance tests: {name}\n\nGenerated from the approved user stories ({len(model['cases'])} test cases, "
        f"{len(model['scenarios'])} scenarios).\n\n```bash\nnpm install\nnpx playwright install chromium\n"
        "SERVICE_BASE_URL=https://your-app npx playwright test\n```\n\nReplace the `<placeholders>` in "
        "`fixtures/test-data.ts`, set `TEST_USER_<ROLE>` / `TEST_PASSWORD` for sign-in and adjust locators in "
        "`pages/AppPage.ts`. Tests tagged `@needs-review` were derived from the stories and need business "
        "confirmation.\n")
    return files


# --------------------------------------------------------------------------- generate / read / export

def generate(eng: dict) -> dict:
    model = build(eng)
    files = playwright_files(eng, model)
    d = out_dir(eng["id"])
    shutil.rmtree(d / "specs", ignore_errors=True)
    for rel, text in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    cases = model["cases"]
    eng["testScenarios"] = {
        "generatedAt": _now(), "sourceDigest": source_digest(eng), "scope": (eng.get("scope") or {}).get("capabilityId"),
        **model, "files": files,
        "counts": counts(model), "runs": [], "runSeq": 0,
    }
    store.save(eng)
    run(eng)   # the related checks run straight away, so the Test Scenarios step opens with results
    return eng


def sync(eng: dict) -> None:
    """Keep the tests in step with the stories: rebuilt and re-checked after the stories are generated or edited.
    Never raises: a failure here must not break user story generation or editing."""
    try:
        if _stories(eng):
            generate(eng)
        else:
            eng.pop("testScenarios", None)
            store.save(eng)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).exception("test scenario sync failed for %s", eng.get("id"))


def counts(model: dict) -> dict:
    sc, cs, cov = model["scenarios"], model["cases"], model["coverage"]
    crit = [c for s in cov for c in s["criteria"]]
    return {
        "scenarios": len(sc), "cases": len(cs), "stories": len(cov), "criteria": len(crit),
        "criteriaCovered": sum(1 for c in crit if c["scenarioIds"]),
        "needsReview": sum(1 for s in sc if s["needsReview"]),
        "byCategory": {k: sum(1 for s in sc if s["category"] == k) for k in CATEGORIES},
    }


def is_stale(eng: dict) -> bool:
    ts = eng.get("testScenarios")
    return bool(ts) and ts.get("sourceDigest") != source_digest(eng)


def export_markdown(eng: dict) -> str:
    ts = eng["testScenarios"]
    lines = [f"# Test scenarios: {eng.get('name', eng['id'])}", "", f"Generated {ts['generatedAt']}", "",
             "## Scenarios", "", "| ID | Story | Category | Scenario | Origin |", "|---|---|---|---|---|"]
    lines += [f"| {s['id']} | {s['storyId']} | {s['category']} | {s['title']} | "
              f"{'needs review' if s['needsReview'] else 'criterion'} |" for s in ts["scenarios"]]
    lines += ["", "## Test cases", ""]
    for c in ts["cases"]:
        lines += [f"### {c['id']} - {c['name']}", "", f"*{c['category']} · story {c['storyId']} · {c['priority']}*", "",
                  c["description"], "", "**Preconditions**", *[f"- {p}" for p in c["preconditions"]], "",
                  "**Steps**", *[f"{i}. {s}" for i, s in enumerate(c["steps"], 1)], "", "**Test data**",
                  *([f"- {d['name']}: `{d['value']}`" for d in c["testData"]] or ["- none"]), "",
                  "**Expected results**", *[f"- {e}" for e in c["expected"]], ""]
    lines += ["## Test data requirements", "", "| ID | Kind | Name | Value | Used by |", "|---|---|---|---|---|"]
    lines += [f"| {d['id']} | {d['kind']} | {d['name']} | `{d['value']}` | {', '.join(d['usedBy'])} |"
              for d in ts["testData"]]
    lines += ["", "## Coverage matrix", "", "| Story | Criterion | Category | Scenarios |", "|---|---|---|---|"]
    for s in ts["coverage"]:
        for c in s["criteria"]:
            lines.append(f"| {s['storyId']} | {c['text'].replace('|', '/')} | {c['category']} | {', '.join(c['scenarioIds'])} |")
    return "\n".join(lines) + "\n"


def export_zip(eng: dict) -> bytes:
    ts = eng["testScenarios"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, text in ts["files"].items():
            z.writestr(f"playwright/{rel}", text)
        z.writestr("test-scenarios.md", export_markdown(eng))
        z.writestr("test-scenarios.json", json.dumps({k: ts[k] for k in ("scenarios", "cases", "testData", "coverage")},
                                                     indent=2, ensure_ascii=False))
    return buf.getvalue()


# --------------------------------------------------------------------------- run

def _quality_checks(case: dict, spec_text: str, data_names: set[str]) -> list[dict]:
    expected_literals = [q for e in case["expected"] for q in _QUOTED.findall(e)]
    has_test = f"[{case['id']}]" in spec_text
    block = spec_text.split(f"[{case['id']}]", 1)[1].split("\n    });", 1)[0] if has_test else ""
    return [
        {"name": "Traceable to a story", "ok": bool(case["storyId"]) and (case["origin"] == "derived" or bool(case["description"])),
         "detail": f"story {case['storyId']}"},
        {"name": "Has preconditions and at least 3 steps", "ok": bool(case["preconditions"]) and len(case["steps"]) >= 3,
         "detail": f"{len(case['steps'])} steps"},
        {"name": "Has an expected result", "ok": bool(case["expected"]), "detail": f"{len(case['expected'])} expected"},
        {"name": "Test data is defined", "ok": all(d["name"] in data_names for d in case["testData"] if d["source"] == "to be supplied"),
         "detail": f"{len(case['testData'])} data item(s)"},
        {"name": "Present in the Playwright script", "ok": has_test and "await app." in block, "detail": "spec file"},
        {"name": "Script checks the quoted values", "ok": all(_ts(q) in block for q in expected_literals) if has_test else False,
         "detail": f"{len(expected_literals)} quoted value(s)"},
    ]


def _live_run(eng: dict, base_url: str, case_ids: set[str]) -> dict:
    """Executes the generated Playwright project. Reports what is missing instead of pretending to have run."""
    d = out_dir(eng["id"])
    npx = shutil.which("npx")
    if not npx:
        return {"status": "unavailable", "reason": "Node.js (npx) was not found on the server.", "results": {}}
    if not (d / "node_modules" / "@playwright").is_dir():
        return {"status": "setup-required", "results": {},
                "reason": "Playwright is not installed for this project. Run once: "
                          f"cd \"{d}\" && npm install && npx playwright install chromium"}
    env = {**os.environ, "SERVICE_BASE_URL": base_url, "CI": "1"}
    grep = "|".join(re.escape(f"[{i}]") for i in sorted(case_ids))
    cmd = [npx, "playwright", "test", "--reporter=json"] + (["--grep", grep] if grep else [])
    try:
        proc = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "The Playwright run took longer than 10 minutes and was stopped.", "results": {}}
    try:
        report = json.loads(proc.stdout)
    except ValueError:
        return {"status": "failed", "results": {},
                "reason": (proc.stderr or proc.stdout or "Playwright produced no report.")[-600:]}
    results: dict[str, dict] = {}

    def walk(suite: dict) -> None:
        for spec in suite.get("specs", []):
            m = re.search(r"\[(TC-\d+)\]", spec.get("title", ""))
            if not m:
                continue
            res = [r for t in spec.get("tests", []) for r in t.get("results", [])]
            last = res[-1] if res else {}
            status = {"passed": "passed", "skipped": "skipped"}.get(last.get("status"), "failed")
            err = (last.get("error") or {}).get("message") or ""
            results[m.group(1)] = {"status": status, "durationMs": int(last.get("duration") or 0),
                                   "message": re.sub(r"\x1b\[[0-9;]*m", "", err).strip()[:500]}
        for child in suite.get("suites", []):
            walk(child)

    for s in report.get("suites", []):
        walk(s)
    return {"status": "completed", "results": results, "reason": None}


def run(eng: dict, base_url: str | None = None, case_ids: list[str] | None = None) -> dict:
    ts = eng.get("testScenarios")
    if not ts:
        raise ValueError("Generate the test scenarios first")
    wanted = set(case_ids or [c["id"] for c in ts["cases"]])
    specs = "\n".join(t for rel, t in ts["files"].items() if rel.startswith("specs/"))
    data_names = {d["name"] for d in ts["testData"]}
    live = _live_run(eng, base_url, wanted) if base_url else {"status": "not-requested", "results": {}, "reason": None}
    rows = []
    for case in ts["cases"]:
        if case["id"] not in wanted:
            continue
        checks = _quality_checks(case, specs, data_names)
        quality_ok = all(c["ok"] for c in checks)
        lv = live["results"].get(case["id"])
        if lv:
            status, message = lv["status"], lv["message"]
        elif not quality_ok:
            status, message = "failed", "; ".join(c["name"] for c in checks if not c["ok"])
        else:
            status, message = ("passed" if not base_url else "not-run"), ""
        rows.append({"caseId": case["id"], "scenarioId": case["scenarioId"], "status": status, "message": message,
                     "durationMs": (lv or {}).get("durationMs"), "checks": checks, "live": bool(lv)})
    summary = {k: sum(1 for r in rows if r["status"] == k) for k in ("passed", "failed", "skipped", "not-run")}
    ts["runSeq"] = ts.get("runSeq", 0) + 1
    record = {"id": f"RUN-{ts['runSeq']:03d}", "at": _now(), "mode": "live" if base_url else "checks",
              "baseUrl": base_url, "liveStatus": live["status"], "liveReason": live["reason"],
              "total": len(rows), "summary": summary, "results": rows}
    ts["runs"] = [record, *ts.get("runs", [])][:MAX_RUNS]
    store.save(eng)
    return record
