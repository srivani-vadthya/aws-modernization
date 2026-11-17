"""Load a .NET workspace the way MSBuild sees it: .sln -> .csproj -> item lists.

The project files are the source of truth for which files belong to the
application. A folder walk is only a fallback for SDK-style projects (which
include **/*.cs implicitly) or trees with no project files at all.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

_SLN_PROJECT = re.compile(
    r'^Project\("\{(?P<kind>[0-9A-Fa-f-]+)\}"\)\s*=\s*"(?P<name>[^"]+)",\s*"(?P<path>[^"]+)"', re.M)
_CSHARP_PROJECT_KINDS = {"FAE04EC0-301F-11D3-BF4B-00C04F79EFBC", "9A19103F-16F7-4668-BE54-9A1E7A4F7556"}
_SKIP_DIRS = {"bin", "obj", "packages", "node_modules", ".git", ".vs"}


@dataclass
class Project:
    name: str
    path: str                       # repo-relative posix path of the .csproj
    sdk_style: bool = False
    compile: list[str] = field(default_factory=list)       # .cs files
    typescript: list[str] = field(default_factory=list)    # .ts files
    views: list[str] = field(default_factory=list)         # .cshtml files
    configs: list[str] = field(default_factory=list)       # Web.config / App.config
    resources: list[str] = field(default_factory=list)     # .resx (EF migration snapshots)
    project_refs: list[tuple[str, int]] = field(default_factory=list)  # (target csproj, line)
    missing: list[str] = field(default_factory=list)       # listed in csproj but absent on disk


@dataclass
class Workspace:
    root: Path
    solution: str | None
    projects: list[Project]
    unlisted: list[str] = field(default_factory=list)      # source on disk that no project compiles
    frontend: list[str] = field(default_factory=list)      # .ts/.tsx outside every project (SPA folders)


def _rel(root: Path, p: Path) -> str:
    return p.resolve().relative_to(root.resolve()).as_posix()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _line_of(text: str, needle: str) -> int:
    idx = text.find(needle)
    return text.count("\n", 0, idx) + 1 if idx >= 0 else 1


def _walk(base: Path, suffixes: tuple[str, ...]) -> list[Path]:
    out = []
    for p in base.rglob("*"):
        if p.is_file() and p.name.lower().endswith(suffixes) and not (_SKIP_DIRS & set(p.relative_to(base).parts)):
            out.append(p)
    return sorted(out)


def load_project(root: Path, csproj: Path) -> Project:
    text = csproj.read_text(encoding="utf-8-sig", errors="ignore")
    proj = Project(name=csproj.stem, path=_rel(root, csproj))
    base = csproj.parent
    try:
        xml = ET.fromstring(text)
    except ET.ParseError:
        xml = None
    proj.sdk_style = bool(xml is not None and xml.get("Sdk"))

    def add(bucket: list[str], include: str) -> None:
        include = include.replace("\\", "/")
        if "*" in include:
            for hit in sorted(base.glob(include)):
                if hit.is_file():
                    bucket.append(_rel(root, hit))
            return
        target = (base / include)
        if target.is_file():
            bucket.append(_rel(root, target))
        else:
            proj.missing.append(PurePosixPath(proj.path).parent.joinpath(include).as_posix())

    if xml is not None:
        for el in xml.iter():
            tag, inc = _local(el.tag), el.get("Include")
            if not inc:
                continue
            low = inc.lower()
            if tag == "Compile" and low.endswith(".cs"):
                add(proj.compile, inc)
            elif tag == "TypeScriptCompile" and low.endswith(".ts") and not low.endswith(".d.ts"):
                add(proj.typescript, inc)
            elif tag in {"Content", "None"} and low.endswith(".cshtml"):
                add(proj.views, inc)
            elif tag in {"Content", "None"} and low.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] in {"web.config", "app.config"}:
                add(proj.configs, inc)
            elif tag == "EmbeddedResource" and low.endswith(".resx"):
                add(proj.resources, inc)
            elif tag == "ProjectReference":
                target = (base / inc.replace("\\", "/")).resolve()
                try:
                    proj.project_refs.append((_rel(root, target), _line_of(text, inc)))
                except ValueError:
                    pass

    # SDK-style projects compile **/*.cs implicitly; old-style may still omit some item kinds.
    if proj.sdk_style or not proj.compile:
        proj.compile = sorted(set(proj.compile) | {_rel(root, p) for p in _walk(base, (".cs",))})
    if not proj.typescript:
        proj.typescript = [_rel(root, p) for p in _walk(base, (".ts",)) if not p.name.endswith(".d.ts")]
    if not proj.views:
        proj.views = [_rel(root, p) for p in _walk(base, (".cshtml",))]
    if not proj.configs:
        proj.configs = [_rel(root, p) for p in _walk(base, ("web.config", "app.config"))
                        if p.name.lower() in {"web.config", "app.config"}]
    if not proj.resources:
        proj.resources = [_rel(root, p) for p in _walk(base, (".resx",))]
    # Exclude TypeScript declaration/typing folders: they describe libraries, not the app.
    proj.typescript = [t for t in proj.typescript if "/typings/" not in f"/{t}"]
    return proj


def load_workspace(root: Path) -> Workspace:
    root = root.resolve()
    slns = sorted(p for p in root.rglob("*.sln") if not (_SKIP_DIRS & set(p.relative_to(root).parts)))
    csprojs: list[Path] = []
    solution = None
    if slns:
        sln = slns[0]
        solution = _rel(root, sln)
        text = sln.read_text(encoding="utf-8-sig", errors="ignore")
        for m in _SLN_PROJECT.finditer(text):
            if m["kind"].upper() not in _CSHARP_PROJECT_KINDS:
                continue
            p = (sln.parent / m["path"].replace("\\", "/"))
            if p.is_file():
                csprojs.append(p)
    if not csprojs:
        csprojs = sorted(p for p in root.rglob("*.csproj") if not (_SKIP_DIRS & set(p.relative_to(root).parts)))

    projects = [load_project(root, p) for p in csprojs]
    if not projects:
        # No MSBuild metadata at all: treat the tree as one implicit project.
        proj = Project(name=root.name, path=".", sdk_style=True)
        proj.compile = [_rel(root, p) for p in _walk(root, (".cs",))]
        proj.typescript = [_rel(root, p) for p in _walk(root, (".ts",)) if not p.name.endswith(".d.ts")
                           and "/typings/" not in f"/{_rel(root, p)}"]
        proj.views = [_rel(root, p) for p in _walk(root, (".cshtml",))]
        proj.configs = [_rel(root, p) for p in _walk(root, ("web.config", "app.config"))]
        proj.resources = [_rel(root, p) for p in _walk(root, (".resx",))]
        projects = [proj]

    compiled = {f for p in projects for f in p.compile}
    unlisted = [_rel(root, p) for p in _walk(root, (".cs",)) if _rel(root, p) not in compiled]
    in_projects = {f for p in projects for f in p.typescript}
    project_dirs = [PurePosixPath(p.path).parent.as_posix() for p in projects if p.path != "."]
    frontend = []
    for p in _walk(root, (".ts", ".tsx")):
        rel = _rel(root, p)
        if rel in in_projects or rel.endswith(".d.ts") or "/typings/" in f"/{rel}" or "/dist/" in f"/{rel}":
            continue
        if any(rel.startswith(d + "/") for d in project_dirs if d != "."):
            continue  # inside a project folder but excluded by its csproj
        frontend.append(rel)
    return Workspace(root=root, solution=solution, projects=projects, unlisted=unlisted, frontend=frontend)
