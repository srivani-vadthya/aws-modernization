"""Documentation generator service.

Each section gets a tailored prompt asking the LLM to return Markdown.
Markdown is then converted to rich HTML (Doxygen-like with sidebar nav)
and a structured .docx with proper tables, lists, and code blocks.
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from .llm_gateway import gateway
from . import store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section definitions
# ---------------------------------------------------------------------------
SECTIONS = [
    "Project Name",
    "Version",
    "Overview",
    "Project Structure",
    "Libraries Used",
    "Technologies Used",
    "Summary",
    "Page Routing Logic",
    "Error Handling and Logging",
    "Important Integrations",
    "Database Information",
    "API Endpoints",
    "Component Diagram",
    "File Dependencies Diagram",
    "How to Run the Project",
]

SECTION_IDS = {s: s.lower().replace(" ", "_") for s in SECTIONS}

# ---------------------------------------------------------------------------
# Section-specific prompts
# ---------------------------------------------------------------------------
SECTION_PROMPTS: dict[str, str] = {
    "Project Name": (
        "Return only the project name as a single line of plain text. "
        "Extract it from the source code (README, config files, or folder name)."
    ),
    "Version": (
        "Return only the version number as a single line (e.g. 1.0.0). "
        "Look in package.json, pom.xml, setup.py, README, or any config file."
    ),
    "Overview": (
        "Write 2-3 plain English paragraphs describing what this project does, "
        "who uses it, and what problem it solves. Write as if explaining to a "
        "non-technical business stakeholder. No jargon. No bullet points."
    ),
    "Project Structure": (
        "Show the project folder and file structure as a tree using box-drawing "
        "characters (├──, └──, │). Then write 1-2 sentences explaining what the "
        "main entry point file is and what it does. "
        "Format:\n```\n<tree here>\n```\n<explanation sentence>"
    ),
    "Libraries Used": (
        "List every third-party library or framework used in this project. "
        "Return a Markdown table with columns: Library Name | What It Does (in plain English) | Why It Is Used In This Project. "
        "Explain each library as if the reader has never heard of it. "
        "Example row: jQuery | A tool that makes it easier to write JavaScript code | Used to handle button clicks and page updates without reloading."
    ),
    "Technologies Used": (
        "List every technology, programming language, and platform used. "
        "Return a Markdown table with columns: Technology | Version | Plain English Description. "
        "Describe each technology simply — what it is and what role it plays in this project."
    ),
    "Summary": (
        "Write a 3-4 paragraph executive summary of the entire project. "
        "Cover: what the system does, how it is organized, what technologies power it, "
        "and any notable patterns or integrations. "
        "Write for a non-technical manager or business owner. Avoid all technical jargon."
    ),
    "Page Routing Logic": (
        "Explain how users navigate through this application — which pages or screens exist, "
        "how they connect to each other, and what happens when a user takes an action. "
        "Use a simple numbered or bulleted list. Write in plain English as if explaining "
        "to someone who has never seen the code."
    ),
    "Error Handling and Logging": (
        "Explain how this application handles errors and records activity logs. "
        "Use the following sub-sections:\n"
        "## Error Handling\n"
        "Explain what happens when something goes wrong — how errors are caught, "
        "what messages are shown, and where errors are managed globally vs per-file.\n"
        "### Key Points\n"
        "Numbered list of the most important error handling mechanisms found in the code.\n"
        "## Logging\n"
        "Explain what gets recorded in logs, where logs are stored, and how to read them. "
        "If no logging exists, explain what approaches could be added.\n"
        "### Recommendations\n"
        "Bullet list of logging best practices for this project.\n"
        "Write everything in plain English for a non-technical reader."
    ),
    "Important Integrations": (
        "List all external systems, services, APIs, or databases this project connects to. "
        "For each integration explain: what it is, why the project needs it, and how it connects. "
        "Use a bulleted list. Write in plain English."
    ),
    "Database Information": (
        "Explain the database used in this project. Cover: what database system is used, "
        "what data is stored, which files handle database operations, and how the connection "
        "is configured. Use bullet points and plain English. "
        "If there are SQL files, mention what tables they create."
    ),
    "API Endpoints": (
        "List every API endpoint or URL route in this project. "
        "Return a Markdown table with columns: Endpoint | Method | What It Does | Input Parameters | Response. "
        "Describe each endpoint in plain English — what a user or system sends and what they get back. "
        "After the table add a numbered 'Key Notes' section with important things to know about these endpoints."
    ),
    "Component Diagram": (
        "Describe the main components (modules, pages, services, databases) of this project "
        "and how they relate to each other. "
        "First write a Mermaid diagram in a ```mermaid code block showing the relationships. "
        "Then write a plain English explanation of the diagram — what each component does "
        "and how data flows between them. Write for a non-technical reader."
    ),
    "File Dependencies Diagram": (
        "Show which files depend on or import other files in this project. "
        "First write a Mermaid diagram in a ```mermaid code block. "
        "Then write a Markdown table with columns: Category | Description | Files. "
        "Group files by their purpose (e.g. Forms, Database, Sessions). "
        "Write descriptions in plain English."
    ),
    "How to Run the Project": (
        "Write a step-by-step guide for setting up and running this project from scratch. "
        "Number each major step. Use nested bullet points for sub-steps. "
        "Include: environment setup, dependency installation, configuration, database setup, "
        "starting the application, and how to verify it is working. "
        "Write as if the reader is not a developer — be very clear and specific."
    ),
}

# ---------------------------------------------------------------------------
# Source context collector
# ---------------------------------------------------------------------------

def _collect_source_context(source_dir: Path, max_chars: int = 24_000) -> str:
    parts: list[str] = []
    total = 0
    extensions = {
        ".cs", ".py", ".ts", ".tsx", ".js", ".jsx", ".java",
        ".go", ".rb", ".php", ".asp", ".vb", ".sql", ".json",
        ".xml", ".yaml", ".yml", ".md", ".txt", ".config", ".csproj",
        ".sln", ".aspx", ".ascx", ".ashx", ".cbl", ".cob", ".rpg",
        ".pls", ".pkb", ".pks", ".vbs",
    }
    skip_dirs = {"node_modules", ".git", "__pycache__", "bin", "obj", ".venv"}

    for path in sorted(source_dir.rglob("*")):
        if path.is_dir() or any(p in skip_dirs for p in path.parts):
            continue
        if path.suffix.lower() not in extensions:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            snippet = text[:1000]
            rel = str(path.relative_to(source_dir))
            chunk = f"\n--- FILE: {rel} ---\n{snippet}\n"
            if total + len(chunk) > max_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        except Exception:
            continue
    return "".join(parts) or "(no readable source files found)"


def _file_tree(source_dir: Path) -> str:
    """Build a simple file tree string from the source directory."""
    lines = [source_dir.name + "/"]
    skip_dirs = {"node_modules", ".git", "__pycache__", "bin", "obj", ".venv"}

    def _walk(directory: Path, prefix: str) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        entries = [e for e in entries if e.name not in skip_dirs]
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            lines.append(prefix + connector + entry.name + ("/" if entry.is_dir() else ""))
            if entry.is_dir():
                extension = "    " if i == len(entries) - 1 else "│   "
                _walk(entry, prefix + extension)

    _walk(source_dir, "")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# LLM section generator
# ---------------------------------------------------------------------------

def _llm_section(section: str, source_context: str, eng: dict, file_tree: str) -> str:
    eng_name = eng.get("name", "Unknown Project")
    section_instruction = SECTION_PROMPTS.get(section, f"Write the '{section}' section in plain English.")

    system = (
        "You are a technical writer creating project documentation for a legacy codebase. "
        "Your audience includes both technical developers AND non-technical business stakeholders. "
        "Write clearly, avoid unexplained jargon, and base every statement strictly on the source code provided. "
        "Do NOT invent details not present in the code. Return valid Markdown only."
    )

    user = (
        f"Project: {eng_name}\n\n"
        f"File tree:\n{file_tree}\n\n"
        f"Source code snapshot:\n{source_context}\n\n"
        f"Task: {section_instruction}\n\n"
        "Important: Return only the section content in Markdown. "
        "Do not include the section heading itself. Keep it under 400 words."
    )

    result = gateway.invoke(
        system_prompt=system,
        user_prompt=user,
        task_type="reasoning",
        max_tokens=900,
        temperature=0.2,
    )
    return result or f"_(Could not generate content for '{section}' — LLM unavailable)_"

# ---------------------------------------------------------------------------
# Markdown → HTML converter (no external deps)
# ---------------------------------------------------------------------------

def _md_to_html(md: str) -> str:
    """Convert Markdown to HTML supporting tables, code blocks, lists, headings, bold."""
    lines = md.split("\n")
    html_parts: list[str] = []
    i = 0
    in_ul = False
    in_ol = False
    in_table = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            html_parts.append("</ul>")
            in_ul = False
        if in_ol:
            html_parts.append("</ol>")
            in_ol = False

    def close_table():
        nonlocal in_table
        if in_table:
            html_parts.append("</tbody></table>")
            in_table = False

    def inline(text: str) -> str:
        # bold
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
        # italic
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        # inline code
        text = re.sub(r"`([^`]+)`", r'<code class="inline-code">\1</code>', text)
        # links
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
        return text

    while i < len(lines):
        line = lines[i]

        # fenced code block
        if line.strip().startswith("```"):
            close_lists()
            close_table()
            lang = line.strip()[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code_content = "\n".join(code_lines)
            if lang == "mermaid":
                html_parts.append(
                    f'<div class="mermaid">{code_content}</div>'
                )
            else:
                escaped = code_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append(f'<div class="fragment"><pre><code>{escaped}</code></pre></div>')
            i += 1
            continue

        # headings
        if line.startswith("### "):
            close_lists(); close_table()
            html_parts.append(f'<h3 class="doxsection">{inline(line[4:])}</h3>')
            i += 1; continue
        if line.startswith("## "):
            close_lists(); close_table()
            html_parts.append(f'<h2 class="doxsection">{inline(line[3:])}</h2>')
            i += 1; continue
        if line.startswith("# "):
            close_lists(); close_table()
            html_parts.append(f'<h2 class="doxsection">{inline(line[2:])}</h2>')
            i += 1; continue

        # horizontal rule
        if re.match(r"^[-*_]{3,}$", line.strip()):
            close_lists(); close_table()
            html_parts.append("<hr/>")
            i += 1; continue

        # table
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[-| :]+\|$", lines[i + 1].strip()):
            close_lists()
            if not in_table:
                html_parts.append('<table class="markdownTable"><thead><tr>')
                headers = [h.strip() for h in line.strip().strip("|").split("|")]
                for h in headers:
                    html_parts.append(f'<th class="markdownTableHeadNone">{inline(h)}</th>')
                html_parts.append("</tr></thead><tbody>")
                in_table = True
                i += 2  # skip separator
                continue
        if in_table and "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            html_parts.append('<tr class="markdownTableRowOdd"><td class="markdownTableBodyNone">' +
                              '</td><td class="markdownTableBodyNone">'.join(inline(c) for c in cells) +
                              "</td></tr>")
            i += 1; continue
        elif in_table:
            close_table()

        # unordered list
        if re.match(r"^(\s*)[-*+] ", line):
            close_table()
            indent = len(line) - len(line.lstrip())
            text = re.sub(r"^\s*[-*+] ", "", line)
            if not in_ul:
                html_parts.append("<ul>")
                in_ul = True
            html_parts.append(f"<li>{inline(text)}</li>")
            i += 1; continue

        # ordered list
        if re.match(r"^\d+\. ", line):
            close_lists(); close_table()
            if not in_ol:
                html_parts.append('<ol type="1">')
                in_ol = True
            text = re.sub(r"^\d+\. ", "", line)
            html_parts.append(f"<li>{inline(text)}</li>")
            i += 1; continue

        # blank line
        if line.strip() == "":
            close_lists(); close_table()
            html_parts.append("")
            i += 1; continue

        # paragraph
        close_lists(); close_table()
        html_parts.append(f"<p>{inline(line)}</p>")
        i += 1

    close_lists()
    close_table()
    return "\n".join(html_parts)

# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _build_html(sections_content: dict[str, str], eng_name: str) -> str:
    # sidebar nav
    nav_items = ""
    for section in SECTIONS:
        sid = SECTION_IDS[section]
        nav_items += f'<li><a href="#{sid}">{section}</a></li>\n'

    # section bodies
    body_html = ""
    for section in SECTIONS:
        sid = SECTION_IDS[section]
        md = sections_content.get(section, "")
        content_html = _md_to_html(md)
        body_html += f"""
        <div class="section" id="{sid}">
            <h1 class="doxsection"><a class="anchor" id="{sid}"></a>{section}</h1>
            <div class="contents">{content_html}</div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{eng_name}: Project Documentation</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; display: flex; color: #1e293b; background: #f8fafc; }}
  #side-nav {{
    width: 260px; min-height: 100vh; background: #1e293b; color: #cbd5e1;
    position: fixed; top: 0; left: 0; overflow-y: auto; padding: 20px 0;
  }}
  #side-nav .nav-title {{
    font-size: 0.8rem; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.08em;
    padding: 0 20px 12px 20px; border-bottom: 1px solid #334155;
  }}
  #side-nav ul {{ list-style: none; padding: 12px 0; }}
  #side-nav ul li a {{
    display: block; padding: 7px 20px; color: #cbd5e1;
    text-decoration: none; font-size: 0.85rem; transition: background 0.15s;
  }}
  #side-nav ul li a:hover {{ background: #334155; color: #f1f5f9; }}
  #doc-content {{
    margin-left: 260px; padding: 40px 48px; max-width: 1100px; width: 100%;
  }}
  .title {{ color: #1e40af; font-size: 2rem; font-weight: 700; margin-bottom: 4px; }}
  .subtitle {{ color: #64748b; font-size: 0.9rem; margin-bottom: 40px; }}
  .section {{ margin-bottom: 48px; scroll-margin-top: 24px; }}
  h1.doxsection {{
    color: #1e40af; font-size: 1.35rem; font-weight: 700;
    border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 16px;
  }}
  h2.doxsection {{ color: #1e40af; font-size: 1.1rem; margin: 20px 0 10px; }}
  h3.doxsection {{ color: #334155; font-size: 0.95rem; margin: 14px 0 8px; }}
  p {{ line-height: 1.75; font-size: 0.95rem; margin-bottom: 10px; color: #334155; }}
  ul, ol {{ padding-left: 24px; margin-bottom: 12px; }}
  li {{ line-height: 1.75; font-size: 0.95rem; color: #334155; margin-bottom: 4px; }}
  table.markdownTable {{
    width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 0.9rem;
  }}
  table.markdownTable th {{
    background: #1e40af; color: #fff; padding: 10px 14px; text-align: left; font-weight: 600;
  }}
  table.markdownTable td {{
    padding: 9px 14px; border-bottom: 1px solid #e2e8f0; color: #334155;
  }}
  table.markdownTable tr:nth-child(even) td {{ background: #f1f5f9; }}
  .fragment {{ background: #1e293b; border-radius: 8px; padding: 16px; margin: 12px 0; overflow-x: auto; }}
  .fragment pre {{ margin: 0; }}
  .fragment code {{ color: #e2e8f0; font-family: 'Courier New', monospace; font-size: 0.85rem; white-space: pre; }}
  code.inline-code {{ background: #f1f5f9; color: #1e40af; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem; }}
  .mermaid {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin: 12px 0; text-align: center; }}
  hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 20px 0; }}
  a {{ color: #1e40af; }}
  strong {{ color: #1e293b; }}
</style>
</head>
<body>
<div id="side-nav">
  <div class="nav-title">{eng_name}</div>
  <ul>{nav_items}</ul>
</div>
<div id="doc-content">
  <h1 class="title">{eng_name}</h1>
  <p class="subtitle">Auto-generated Project Documentation</p>
  {body_html}
</div>
<script>mermaid.initialize({{startOnLoad: true, theme: 'default'}});</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# DOCX builder
# ---------------------------------------------------------------------------

def _set_cell_bg(cell, hex_color: str) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _parse_md_table(md: str) -> list[list[str]] | None:
    """Extract table rows from Markdown. Returns [headers, row1, row2, ...]."""
    lines = [l for l in md.split("\n") if "|" in l]
    if len(lines) < 2:
        return None
    rows = []
    for line in lines:
        if re.match(r"^\|[-| :]+\|$", line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows if len(rows) >= 1 else None


def _add_md_to_docx(doc: Document, md: str) -> None:
    """Parse Markdown and add content to docx with proper formatting."""
    lines = md.split("\n")
    i = 0
    in_code = False
    code_lines: list[str] = []

    # Try to render table first if content is mostly a table
    table_data = _parse_md_table(md)
    if table_data and len(table_data) >= 2:
        headers = table_data[0]
        rows = table_data[1:]
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        hdr_row = t.rows[0]
        for j, h in enumerate(headers):
            cell = hdr_row.cells[j]
            cell.text = h
            _set_cell_bg(cell, "1E40AF")
            run = cell.paragraphs[0].runs[0]
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            run.font.bold = True
            run.font.size = Pt(9)
        for row_data in rows:
            row = t.add_row()
            for j, val in enumerate(row_data):
                if j < len(row.cells):
                    row.cells[j].text = val
                    row.cells[j].paragraphs[0].runs[0].font.size = Pt(9) if row.cells[j].paragraphs[0].runs else None
        doc.add_paragraph()
        return

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                code_lines = []
            else:
                in_code = False
                p = doc.add_paragraph("\n".join(code_lines))
                p.style = "No Spacing"
                for run in p.runs:
                    run.font.name = "Courier New"
                    run.font.size = Pt(8)
                    run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
                doc.add_paragraph()
            i += 1; continue

        if in_code:
            code_lines.append(line)
            i += 1; continue

        if line.startswith("### "):
            h = doc.add_heading(line[4:], level=3)
            if h.runs: h.runs[0].font.color.rgb = RGBColor(0x33, 0x41, 0x55)
        elif line.startswith("## "):
            h = doc.add_heading(line[3:], level=2)
            if h.runs: h.runs[0].font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
        elif line.startswith("# "):
            h = doc.add_heading(line[2:], level=2)
            if h.runs: h.runs[0].font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
        elif re.match(r"^[-*+] ", line):
            p = doc.add_paragraph(style="List Bullet")
            text = re.sub(r"^[-*+] ", "", line)
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            p.add_run(text).font.size = Pt(10)
        elif re.match(r"^\d+\. ", line):
            p = doc.add_paragraph(style="List Number")
            text = re.sub(r"^\d+\. ", "", line)
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            p.add_run(text).font.size = Pt(10)
        elif line.strip():
            text = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            text = re.sub(r"`([^`]+)`", r"\1", text)
            p = doc.add_paragraph(text)
            if p.runs: p.runs[0].font.size = Pt(10)

        i += 1


def _build_docx(sections_content: dict[str, str], eng_name: str) -> bytes:
    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.2)
        section.right_margin = Inches(1.2)

    # Title
    title = doc.add_heading(f"{eng_name} — Project Documentation", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if title.runs:
        title.runs[0].font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)

    doc.add_paragraph()

    for s in SECTIONS:
        md = sections_content.get(s, "")
        h = doc.add_heading(s, level=1)
        if h.runs:
            h.runs[0].font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
        _add_md_to_docx(doc, md)
        doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_docs(eid: str) -> tuple[bytes, str]:
    eng = store.load(eid)
    if not eng:
        raise ValueError(f"Engagement {eid} not found")

    source_dir = store.engagement_dir(eid) / "source"
    source_context = _collect_source_context(source_dir)
    file_tree = _file_tree(source_dir)
    eng_name = eng.get("name", "Unknown Project")

    sections_content: dict[str, str] = {}
    for section in SECTIONS:
        logger.info("Generating section '%s' for engagement %s", section, eid)
        sections_content[section] = _llm_section(section, source_context, eng, file_tree)

    return _build_docx(sections_content, eng_name), _build_html(sections_content, eng_name)
