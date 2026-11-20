"""
push_to_github.py
-----------------
Pushes backend (FastAPI) and frontend (React/Vite) source to:
  Backend  : https://github.com/Hari-var/Insurance-Management-System
  Frontend : https://github.com/Hari-var/IMS-FrontEnd

PAT resolution order:
  1. First CLI argument:  python push_to_github.py <PAT>
  2. Env var HARIVAR_PAT in .env
  3. Env var GITHUB_TOKEN in .env  (fallback)
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ── Load .env ────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

# PAT: CLI arg > HARIVAR_PAT > GITHUB_TOKEN
PAT = (
    (sys.argv[1] if len(sys.argv) > 1 else None)
    or os.getenv("HARIVAR_PAT")
    or os.getenv("GITHUB_TOKEN")
    or os.getenv("GITHUB_PAT")
)

if not PAT:
    sys.exit(
        "ERROR: No GitHub PAT found.\n"
        "  Pass it as:  python push_to_github.py <PAT>\n"
        "  Or set HARIVAR_PAT in apps/api/.env"
    )

OWNER         = "Hari-var"
BACKEND_REPO  = "Insurance-Management-System"
FRONTEND_REPO = "IMS-FrontEnd"

HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ── Source roots ─────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT  = REPO_ROOT / "aws-modernization" / "apps" / "api"
WEB_ROOT  = REPO_ROOT / "aws-modernization" / "apps" / "web"

# ── What to include ───────────────────────────────────────────────────────────
BACKEND_INCLUDE_EXTS = {
    ".py", ".txt", ".md", ".toml", ".cfg", ".ini",
    ".yml", ".yaml", ".json", ".xml", ".sql",
    ".java", ".kt", ".properties", ".sh",
}

FRONTEND_INCLUDE_EXTS = {
    ".ts", ".tsx", ".js", ".jsx", ".json",
    ".css", ".html", ".md", ".yml", ".yaml",
}

SKIP_DIRS  = {
    "__pycache__", ".git", "node_modules", ".vite",
    ".mypy_cache", ".pytest_cache", "dist", "build",
    ".agents", "data",
}
SKIP_FILES = {".env", ".env.example"}

# Limit to app source only — skip tests/data/scripts to stay well under API limits
BACKEND_INCLUDE_DIRS = {"app", "scripts"}   # relative to API_ROOT


def collect_files(root: Path, include_exts: set[str],
                  include_dirs: set[str] | None = None) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in include_exts:
            continue
        rel = path.relative_to(root).as_posix()
        # For backend, only include files inside allowed top-level dirs
        if include_dirs:
            top = rel.split("/")[0]
            if top not in include_dirs and path.parent == root:
                pass  # root-level files (requirements.txt, README) are fine
            elif top not in include_dirs and path.parent != root:
                continue
        try:
            files[rel] = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            print(f"  [WARN] Could not read {rel}: {exc}")
    return files


# ── GitHub helpers ────────────────────────────────────────────────────────────

def verify_token(client: httpx.Client) -> str:
    res = client.get("https://api.github.com/user", headers=HEADERS)
    if res.status_code != 200:
        sys.exit(f"ERROR: Token rejected by GitHub ({res.status_code}): {res.text[:200]}")
    login = res.json()["login"]
    print(f"  Authenticated as : {login}")
    return login


def check_repo_access(client: httpx.Client, owner: str, repo: str) -> bool:
    res = client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=HEADERS)
    if res.status_code == 200:
        print(f"  Repo accessible : https://github.com/{owner}/{repo}")
        return True
    sys.exit(
        f"ERROR: Cannot access https://github.com/{owner}/{repo} "
        f"({res.status_code}).\n"
        f"  Make sure the PAT belongs to '{owner}' or a collaborator with push access.\n"
        f"  Response: {res.text[:200]}"
    )


def get_default_branch(client: httpx.Client, owner: str, repo: str) -> str:
    res = client.get(f"https://api.github.com/repos/{owner}/{repo}", headers=HEADERS)
    return res.json().get("default_branch", "main")


def ensure_branch_exists(client: httpx.Client, owner: str, repo: str, branch: str) -> None:
    """If the repo is completely empty (no commits), seed it with a README so the branch exists."""
    ref_res = client.get(
        f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{branch}",
        headers=HEADERS,
    )
    if ref_res.status_code == 200:
        return  # branch already exists

    # Repo is empty -- create an initial commit via the contents API
    readme = base64.b64encode(b"# Modernized Service\n\nGenerated by Nexus Modernize.").decode()
    init = client.put(
        f"https://api.github.com/repos/{owner}/{repo}/contents/README.md",
        headers=HEADERS,
        json={"message": "chore: initialize repository", "content": readme},
    )
    if init.status_code in (200, 201):
        print(f"  Initialized empty repo with first commit on '{branch}'")
    else:
        sys.exit(f"ERROR: Could not initialize repo branch '{branch}': {init.text[:200]}")


def push_files(client: httpx.Client, owner: str, repo: str,
               files: dict[str, str]) -> int:
    branch = get_default_branch(client, owner, repo)
    ensure_branch_exists(client, owner, repo, branch)

    committed = 0
    total = len(files)
    for i, (rel_path, content) in enumerate(files.items(), 1):
        b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        file_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{rel_path}"

        sha = None
        check = client.get(file_url, headers=HEADERS)
        if check.status_code == 200:
            sha = check.json().get("sha")

        body: dict = {
            "message": f"feat: modernize {rel_path}",
            "content": b64,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha

        put = client.put(file_url, headers=HEADERS, json=body)
        if put.status_code in (200, 201):
            committed += 1
            print(f"  [{i:>3}/{total}] OK  {rel_path}")
        else:
            print(f"  [{i:>3}/{total}] ERR {rel_path}  "
                  f"({put.status_code}: {put.text[:100]})")

    return committed


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    sep = "=" * 62

    with httpx.Client(timeout=60.0) as client:
        print(f"\n{sep}")
        print("Nexus Modernize -- GitHub Push")
        print(f"  Token : {PAT[:8]}...{PAT[-4:]}")
        print(sep)
        verify_token(client)

        # ── BACKEND ──────────────────────────────────────────────────────────
        print(f"\n{sep}")
        print(f"BACKEND  ->  https://github.com/{OWNER}/{BACKEND_REPO}")
        print(f"Source   :   {API_ROOT}")
        print(sep)

        check_repo_access(client, OWNER, BACKEND_REPO)
        backend_files = collect_files(API_ROOT, BACKEND_INCLUDE_EXTS,
                                      include_dirs=BACKEND_INCLUDE_DIRS)
        print(f"  Collected {len(backend_files)} backend files\n")
        backend_committed = push_files(client, OWNER, BACKEND_REPO, backend_files)
        print(f"\n  [DONE] Backend: {backend_committed}/{len(backend_files)} files committed")
        print(f"  https://github.com/{OWNER}/{BACKEND_REPO}")

        # ── FRONTEND ─────────────────────────────────────────────────────────
        print(f"\n{sep}")
        print(f"FRONTEND ->  https://github.com/{OWNER}/{FRONTEND_REPO}")
        print(f"Source   :   {WEB_ROOT}")
        print(sep)

        check_repo_access(client, OWNER, FRONTEND_REPO)
        frontend_files = collect_files(WEB_ROOT, FRONTEND_INCLUDE_EXTS)
        print(f"  Collected {len(frontend_files)} frontend files\n")
        frontend_committed = push_files(client, OWNER, FRONTEND_REPO, frontend_files)
        print(f"\n  [DONE] Frontend: {frontend_committed}/{len(frontend_files)} files committed")
        print(f"  https://github.com/{OWNER}/{FRONTEND_REPO}")

        # ── Summary ───────────────────────────────────────────────────────────
        print(f"\n{sep}")
        print("PUSH COMPLETE")
        print(f"  Backend  : https://github.com/{OWNER}/{BACKEND_REPO}")
        print(f"  Frontend : https://github.com/{OWNER}/{FRONTEND_REPO}")
        print(sep)


if __name__ == "__main__":
    main()
