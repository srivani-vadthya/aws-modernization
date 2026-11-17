#!/usr/bin/env python3
"""Validate a backlog and push its epics / features / stories to Jira, Azure DevOps, Bitbucket or GitHub.

    python push_backlog.py validate backlog.json
    python push_backlog.py status   [--config tracker-config.json] [--env-file .env]
    python push_backlog.py push backlog.json --provider jira --config tracker-config.json \
        [--apply] [--only US-SIR-002-01 ...] [--show-payload] [--allow-template] [--env-file .env]

Without --apply nothing is sent (dry run). Non-secret settings come from the config file, falling back to the
environment; secrets (tokens, PATs, app passwords) come from the environment / --env-file only and are never
written to disk or printed. Re-runs are safe: `<backlog>.push-state.json` records what exists in each target.
Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backlog_model as bm  # noqa: E402

PROVIDERS = ("jira", "ado", "bitbucket", "github")
LABELS = {"jira": "Jira", "ado": "Azure DevOps", "bitbucket": "Bitbucket", "github": "GitHub"}

# setting -> environment variable (config file value wins over the environment)
SETTINGS_ENV = {
    "jira": {"baseUrl": "JIRA_BASE_URL", "projectKey": "JIRA_PROJECT_KEY", "email": "JIRA_EMAIL"},
    "ado": {"organization": "ADO_ORG", "project": "ADO_PROJECT"},
    "bitbucket": {"workspace": "BITBUCKET_WORKSPACE", "repository": "BITBUCKET_REPO",
                  "username": "BITBUCKET_USERNAME"},
    "github": {"repository": "GITHUB_REPO"},
}
REQUIRED = {"jira": ("baseUrl", "projectKey", "email"), "ado": ("organization", "project"),
            "bitbucket": ("workspace", "repository"), "github": ("repository",)}
# secrets: environment only. For bitbucket either BITBUCKET_TOKEN, or BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD.
SECRET_ENV = {"jira": ("JIRA_API_TOKEN",), "ado": ("ADO_PAT",), "bitbucket": ("BITBUCKET_APP_PASSWORD", "BITBUCKET_TOKEN"),
              "github": ("GITHUB_TOKEN",)}
OPTIONAL = {
    "jira": {"epicIssueType": "Epic", "storyIssueType": "Story", "featureMode": "label", "topIssueType": "",
             "storyPointsField": ""},
    "ado": {"process": "agile", "baseUrl": "https://dev.azure.com", "areaPath": "", "iterationPath": ""},
    "bitbucket": {"apiUrl": "https://api.bitbucket.org/2.0"},
    "github": {"apiUrl": "https://api.github.com"},
}
HttpFn = Callable[[str, str, dict, "object | None"], "tuple[int, object]"]


class PushError(Exception):
    pass


# --------------------------------------------------------------------------- configuration

def load_env_file(path: str) -> dict:
    env: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip("'\"")
    return env


def resolve(provider: str, config: dict | None, env: dict | None) -> tuple[dict, dict, list[str]]:
    """-> (settings, secrets, missing). `missing` lists what to set (env var names / settings)."""
    env = os.environ if env is None else env
    cfg = (config or {}).get(provider) or {}
    settings: dict[str, str] = {}
    missing: list[str] = []
    for key, env_name in SETTINGS_ENV[provider].items():
        settings[key] = str(cfg.get(key) or env.get(env_name) or "").strip()
    for key, default in OPTIONAL[provider].items():
        settings[key] = str(cfg.get(key) or default).strip()
    secrets = {name: env.get(name, "") for name in SECRET_ENV[provider]}
    for key in REQUIRED[provider]:
        if not settings[key]:
            missing.append(SETTINGS_ENV[provider][key])
    if provider == "bitbucket":
        if not (secrets["BITBUCKET_TOKEN"] or (settings["username"] and secrets["BITBUCKET_APP_PASSWORD"])):
            missing.append("BITBUCKET_TOKEN or (BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD)")
    else:
        for name in SECRET_ENV[provider]:
            if not secrets[name]:
                missing.append(name)
    return settings, secrets, missing


def provider_status(config: dict | None = None, env: dict | None = None) -> list[dict]:
    """Integration status for each tracker, safe to show in a UI: never includes a secret value."""
    out = []
    for p in PROVIDERS:
        settings, secrets, missing = resolve(p, config, env)
        out.append({"id": p, "label": LABELS[p], "configured": not missing, "missing": missing,
                    "settings": settings, "secrets": {k: bool(v) for k, v in secrets.items()},
                    "required": list(REQUIRED[p]),
                    "envVars": {**SETTINGS_ENV[p], **{n: n for n in SECRET_ENV[p]}}})
    return out


def _target_id(provider: str, s: dict) -> str:
    if provider == "jira":
        return f"{s['baseUrl'].rstrip('/')}/{s['projectKey']}"
    if provider == "ado":
        return f"{s['organization']}/{s['project']}"
    if provider == "bitbucket":
        return f"{s['workspace']}/{s['repository']}"
    return s["repository"]


# --------------------------------------------------------------------------- HTTP

def _check_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise PushError(f"refusing to send credentials over a non-https URL: {parsed.scheme}://{parsed.hostname}")


def http_request(method: str, url: str, headers: dict, body=None, timeout: int = 30):
    _check_url(url)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        raise PushError(f"cannot reach {urllib.parse.urlparse(url).hostname}: {exc.reason}") from exc


def _basic(user: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()


def _label(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "-", text).strip("-")


def _error_text(status: int, data) -> str:
    if isinstance(data, dict):
        for key in ("errorMessages", "errors", "message", "error"):
            if data.get(key):
                return f"HTTP {status}: {json.dumps(data[key])[:300]}"
    return f"HTTP {status}: {str(data)[:300]}"


# --------------------------------------------------------------------------- providers
# Each provider answers: does this item become a tracker issue? who is its parent? what request creates it?

class Provider:
    name = ""

    def __init__(self, settings: dict, secrets: dict):
        self.s, self.secrets = settings, secrets

    def creates(self, item: dict) -> bool:
        return True

    def parent_id(self, item: dict) -> str | None:
        return item["parent"]

    def headers(self) -> dict:
        return {}

    def request(self, item: dict, parent: dict | None) -> tuple[str, str, object]:
        raise NotImplementedError

    def ref(self, item: dict, data) -> dict:
        raise NotImplementedError

    def after_create(self, item: dict, ref: dict, parent: dict | None, http: HttpFn) -> list[str]:
        return []


class Jira(Provider):
    name = "jira"

    def creates(self, item):
        if self.s["featureMode"] == "label":      # epics + stories; features become labels on their stories
            return item["level"] != "feature"
        return item["level"] != "epic" or bool(self.s["topIssueType"])   # features are the Epic issues

    def parent_id(self, item):
        if self.s["featureMode"] == "label":
            return item["epic"]["id"] if item["level"] == "story" else None
        if item["level"] == "feature":
            return item["epic"]["id"] if self.s["topIssueType"] else None
        return item["parent"] if item["level"] == "story" else None

    def headers(self):
        return {"Authorization": _basic(self.s["email"], self.secrets["JIRA_API_TOKEN"]),
                "Content-Type": "application/json"}

    def request(self, item, parent):
        lvl, s = item["level"], self.s
        if lvl == "epic":
            itype = s["topIssueType"] if s["featureMode"] == "epic" and s["topIssueType"] else s["epicIssueType"]
        elif lvl == "feature":
            itype = s["epicIssueType"]
        else:
            itype = s["storyIssueType"]
        labels = [_label(x) for x in item["labels"]]
        if lvl == "story":
            labels.append(_label(f"feature-{item['feature']['id']}"))
            labels.append(_label(f"priority-{item['story'].get('priority', '').lower()}"))
        elif s["featureMode"] == "epic" and lvl == "feature" and not s["topIssueType"]:
            labels.append(_label(f"epic-{item['epic']['id']}"))
        fields = {"project": {"key": s["projectKey"]}, "summary": item["title"][:250],
                  "issuetype": {"name": itype}, "description": bm.adf(item), "labels": sorted(set(labels))}
        if parent:
            fields["parent"] = {"key": parent["key"]}
        if lvl == "story" and s["storyPointsField"]:
            fields[s["storyPointsField"]] = item["story"].get("storyPoints")
        return "POST", f"{s['baseUrl'].rstrip('/')}/rest/api/3/issue", {"fields": fields}

    def ref(self, item, data):
        key = data["key"]
        return {"key": key, "id": data.get("id"), "url": f"{self.s['baseUrl'].rstrip('/')}/browse/{key}"}


class Ado(Provider):
    name = "ado"
    TYPES = {"agile": ("Epic", "Feature", "User Story"), "scrum": ("Epic", "Feature", "Product Backlog Item"),
             "cmmi": ("Epic", "Feature", "Requirement")}
    POINTS = {"agile": "Microsoft.VSTS.Scheduling.StoryPoints", "scrum": "Microsoft.VSTS.Scheduling.Effort",
              "cmmi": "Microsoft.VSTS.Scheduling.Size"}
    PRIORITY = {"Must": 1, "Should": 2, "Could": 3, "Won't": 4}

    def headers(self):
        return {"Authorization": _basic("", self.secrets["ADO_PAT"]), "Content-Type": "application/json-patch+json"}

    def request(self, item, parent):
        s = self.s
        proc = s["process"] if s["process"] in self.TYPES else "agile"
        wi_type = {"epic": 0, "feature": 1, "story": 2}[item["level"]]
        wi_type = self.TYPES[proc][wi_type]
        if item["level"] == "story":
            story = item["story"]
            desc, ac = bm.story_html(story), bm.acceptance_html(story)
        else:
            src = item["epic"] if item["level"] == "epic" else item["feature"]
            desc, ac = f"<p>{bm.html.escape(src.get('description') or src['title'])}</p>", ""
            if src.get("businessOutcome"):
                desc += f"<p><b>Business outcome:</b> {bm.html.escape(src['businessOutcome'])}</p>"
        ops = [{"op": "add", "path": "/fields/System.Title", "value": item["title"][:250]},
               {"op": "add", "path": "/fields/System.Description", "value": desc},
               {"op": "add", "path": "/fields/System.Tags", "value": "; ".join(sorted(set(item["labels"])))}]
        if item["level"] == "story":
            story = item["story"]
            ops += [{"op": "add", "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria", "value": ac},
                    {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority",
                     "value": self.PRIORITY.get(story.get("priority"), 2)},
                    {"op": "add", "path": f"/fields/{self.POINTS[proc]}", "value": story.get("storyPoints")}]
        for field, key in (("System.AreaPath", "areaPath"), ("System.IterationPath", "iterationPath")):
            if s[key]:
                ops.append({"op": "add", "path": f"/fields/{field}", "value": s[key]})
        if parent:
            ops.append({"op": "add", "path": "/relations/-", "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse", "url": parent.get("api", "")}})
        base = s["baseUrl"].rstrip("/")
        url = (f"{base}/{urllib.parse.quote(s['organization'])}/{urllib.parse.quote(s['project'])}"
               f"/_apis/wit/workitems/${urllib.parse.quote(wi_type)}?api-version=7.1")
        return "POST", url, ops

    def ref(self, item, data):
        s, wid = self.s, data["id"]
        return {"key": str(wid), "id": wid, "api": data.get("url", ""),
                "url": f"{s['baseUrl'].rstrip('/')}/{s['organization']}/{s['project']}/_workitems/edit/{wid}"}


class Bitbucket(Provider):
    name = "bitbucket"
    KIND = {"epic": "proposal", "feature": "enhancement", "story": "task"}
    PRIORITY = {"Must": "critical", "Should": "major", "Could": "minor", "Won't": "trivial"}

    def headers(self):
        if self.secrets["BITBUCKET_TOKEN"]:
            auth = "Bearer " + self.secrets["BITBUCKET_TOKEN"]
        else:
            auth = _basic(self.s["username"], self.secrets["BITBUCKET_APP_PASSWORD"])
        return {"Authorization": auth, "Content-Type": "application/json"}

    def request(self, item, parent):
        prefix = {"epic": "[Epic] ", "feature": "[Feature] ", "story": ""}[item["level"]]
        body = bm.item_markdown(item)
        if parent:
            body = f"Parent: {parent['key']}\n\n{body}"
        payload = {"title": (prefix + item["title"])[:250], "content": {"raw": body, "markup": "markdown"},
                   "kind": self.KIND[item["level"]]}
        if item["level"] == "story":
            payload["priority"] = self.PRIORITY.get(item["story"].get("priority"), "major")
        s = self.s
        return "POST", f"{s['apiUrl'].rstrip('/')}/repositories/{s['workspace']}/{s['repository']}/issues", payload

    def ref(self, item, data):
        return {"key": f"#{data['id']}", "id": data["id"],
                "url": (data.get("links", {}).get("html") or {}).get("href", "")}


class GitHub(Provider):
    name = "github"
    LEVEL_LABEL = {"epic": "epic", "feature": "feature", "story": "user-story"}

    def headers(self):
        return {"Authorization": "Bearer " + self.secrets["GITHUB_TOKEN"], "Content-Type": "application/json",
                "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    def request(self, item, parent):
        body = bm.item_markdown(item)
        if parent:
            body = f"Parent: {parent['key']}\n\n{body}"
        labels = sorted({self.LEVEL_LABEL[item["level"]], *[_label(x) for x in item["labels"]]})
        return "POST", f"{self.s['apiUrl'].rstrip('/')}/repos/{self.s['repository']}/issues", {
            "title": item["title"][:250], "body": body, "labels": labels}

    def ref(self, item, data):
        return {"key": f"#{data['number']}", "id": data["id"], "number": data["number"], "url": data["html_url"]}

    def after_create(self, item, ref, parent, http):
        if not parent or not parent.get("number"):
            return []
        url = f"{self.s['apiUrl'].rstrip('/')}/repos/{self.s['repository']}/issues/{parent['number']}/sub_issues"
        status, data = http("POST", url, self.headers(), {"sub_issue_id": ref["id"]})
        if status in (200, 201):
            return []
        return [f"{item['id']}: created, but could not link as sub-issue of {parent['key']} ({_error_text(status, data)}); "
                f"the body still names its parent"]


PROVIDER_CLASSES = {"jira": Jira, "ado": Ado, "bitbucket": Bitbucket, "github": GitHub}


# --------------------------------------------------------------------------- push

def _select(items: list[dict], only: list[str] | None) -> list[dict]:
    if not only:
        return items
    by_id = {i["id"]: i for i in items}
    unknown = [o for o in only if o not in by_id]
    if unknown:
        raise PushError(f"unknown item id(s) in --only: {', '.join(unknown)}")
    keep: set[str] = set()
    for o in only:
        cur = by_id[o]
        while cur:
            keep.add(cur["id"])
            cur = by_id.get(cur["parent"])
    return [i for i in items if i["id"] in keep]


def push(backlog: dict, provider: str, config: dict | None = None, env: dict | None = None, *,
         apply: bool = False, only: list[str] | None = None, allow_template: bool = False,
         state: dict | None = None, http: HttpFn | None = None, show_payload: bool = False,
         on_state: Callable[[dict], None] | None = None) -> dict:
    if provider not in PROVIDERS:
        raise PushError(f"unknown provider {provider!r}; choose one of {', '.join(PROVIDERS)}")
    problems = [m for lvl, m in bm.validate(backlog) if lvl == "ERROR"]
    if problems and apply:
        raise PushError("backlog has validation errors; fix them first: " + "; ".join(problems[:3]))
    settings, secrets, missing = resolve(provider, config, env)
    if apply and missing:
        raise PushError(f"{LABELS[provider]} is not configured; set: {', '.join(missing)}")
    if provider == "jira" and settings["featureMode"] not in ("label", "epic"):
        raise PushError("jira featureMode must be 'label' or 'epic'")
    prov = PROVIDER_CLASSES[provider](settings, secrets)
    call = http or http_request
    state = state if state is not None else {}
    target = f"{provider}:{_target_id(provider, settings) if not missing else 'unconfigured'}"
    known: dict = state.setdefault("targets", {}).setdefault(target, {})

    items = _select(bm.flatten(backlog), only)
    refs: dict[str, dict] = {}
    failed: set[str] = set()
    rows, warnings = [], []
    for item in items:
        iid = item["id"]
        row = {"id": iid, "level": item["level"], "title": item["title"], "parent": item["parent"]}
        rows.append(row)
        if not prov.creates(item):
            row["action"] = "folded"
            row["note"] = ("represented as labels on its stories" if item["level"] == "feature"
                           else "no top-level issue type configured")
            continue
        if iid in known:
            refs[iid] = known[iid]
            row.update(action="exists", key=known[iid].get("key"), url=known[iid].get("url"))
            continue
        pid = prov.parent_id(item)
        if pid and pid in failed:
            row.update(action="skipped", note=f"parent {pid} did not get created")
            failed.add(iid)
            continue
        if item["level"] == "story" and item["story"].get("narrativeSource") == "template" and not allow_template:
            row.update(action="blocked", note="template wording; refine the story or pass allow_template")
            continue
        parent_ref = refs.get(pid) if pid else None
        if pid and parent_ref is None:  # parent exists only as a plan item (dry run)
            parent_ref = {"key": f"<{pid}>", "id": f"<{pid}>", "api": f"<{pid}>", "number": None}
        method, url, payload = prov.request(item, parent_ref)
        if show_payload:
            row["payload"] = {"method": method, "url": url, "body": payload}
        if not apply:
            row["action"] = "create"
            refs[iid] = {"key": f"<{iid}>", "id": f"<{iid}>", "api": f"<{iid}>", "number": None, "url": ""}
            continue
        try:
            status, data = call(method, url, prov.headers(), payload)
        except PushError as exc:
            status, data = 0, str(exc)
        if status in (200, 201) and isinstance(data, dict):
            ref = prov.ref(item, data)
            known[iid] = ref
            refs[iid] = ref
            row.update(action="created", key=ref.get("key"), url=ref.get("url"))
            warnings += prov.after_create(item, ref, parent_ref, call)
            if on_state:
                on_state(state)
        else:
            failed.add(iid)
            row.update(action="failed", error=_error_text(status, data) if status else str(data))
    summary: dict[str, int] = {}
    for r in rows:
        summary[r["action"]] = summary.get(r["action"], 0) + 1
    return {"provider": provider, "label": LABELS[provider], "target": target, "apply": apply, "ready": not missing,
            "missing": missing, "rows": rows, "summary": summary, "warnings": warnings, "state": state}


# --------------------------------------------------------------------------- CLI

def _print_report(rep: dict) -> None:
    mode = "APPLIED" if rep["apply"] else "DRY RUN (nothing sent)"
    print(f"{rep['label']} · {rep['target']} · {mode}")
    if rep["missing"]:
        print("  not configured, missing: " + ", ".join(rep["missing"]))
    for r in rep["rows"]:
        tail = r.get("url") or r.get("note") or r.get("error") or ""
        print(f"  {r['action']:<8} {r['level']:<8} {r['id']:<22} {r.get('key') or ''} {tail}")
    for w in rep["warnings"]:
        print("  WARN " + w)
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(rep["summary"].items())))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("backlog")
    st = sub.add_parser("status")
    p = sub.add_parser("push")
    p.add_argument("backlog")
    p.add_argument("--provider", required=True, choices=PROVIDERS)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--only", nargs="*")
    p.add_argument("--show-payload", action="store_true")
    p.add_argument("--allow-template", action="store_true")
    p.add_argument("--state", help="push-state file (default: <backlog>.push-state.json)")
    for sp in (st, p):
        sp.add_argument("--config")
        sp.add_argument("--env-file")
    args = ap.parse_args(argv)

    if args.cmd == "validate":
        with open(args.backlog, encoding="utf-8") as fh:
            issues = bm.validate(json.load(fh))
        for lvl, msg in issues:
            print(f"{lvl}: {msg}")
        errors = sum(1 for lvl, _ in issues if lvl == "ERROR")
        print(f"{errors} error(s), {len(issues) - errors} warning(s)")
        return 1 if errors else 0

    config = json.load(open(args.config, encoding="utf-8")) if args.config else None
    env = {**os.environ, **(load_env_file(args.env_file) if args.env_file else {})}
    if args.cmd == "status":
        for s in provider_status(config, env):
            print(f"{s['label']:<13} {'configured' if s['configured'] else 'missing: ' + ', '.join(s['missing'])}")
        return 0

    with open(args.backlog, encoding="utf-8") as fh:
        backlog = json.load(fh)
    state_path = args.state or re.sub(r"\.json$", "", args.backlog) + ".push-state.json"
    state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}

    def save_state(s: dict) -> None:
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=2)

    try:
        rep = push(backlog, args.provider, config, env, apply=args.apply, only=args.only,
                   allow_template=args.allow_template, state=state, show_payload=args.show_payload,
                   on_state=save_state)
    except PushError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.apply:
        save_state(rep["state"])
    _print_report(rep)
    if args.show_payload:
        for r in rep["rows"]:
            if "payload" in r:
                print(json.dumps({r["id"]: r["payload"]}, indent=2))
    return 1 if rep["summary"].get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
