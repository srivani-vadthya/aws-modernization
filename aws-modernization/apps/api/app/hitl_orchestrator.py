"""HITL (Human-in-the-Loop) Governance Orchestrator.

Standalone module — completely decoupled from the gate approval pipeline.
If this module fails, Approve/Reject gates are unaffected.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

PHASE_ORDER = [
    "intake",
    "discovery",
    "graph",
    "scope",
    "semantic-ir",
    "user-stories",
    "modernize",
    "test-scenarios",
    "tests",
    "failures",
    "artifacts",
]

# Keyword-based fast-path classification (no LLM cost for obvious cases)
_KEYWORD_MAP: list[tuple[list[str], str]] = [
    # intake — source upload, git, zip, folder
    (["intake", "upload", "source", "git", "zip", "folder", "ingest", "repository", "repo"], "intake"),

    # discovery — inventory, asset classification, language scan
    (["discovery", "inventory", "classify", "asset", "scan", "language", "loc", "program", "cobol", "rpgle", "clle"], "discovery"),

    # graph — application knowledge graph, AKG, dependencies
    (["graph", "akg", "knowledge graph", "dependency", "call graph", "ast", "relationship", "node", "edge", "cluster", "bounded context"], "graph"),

    # scope — business module selection, capability, wave
    (["scope", "module", "capability", "boundary", "partition", "domain", "business module", "wave", "blast radius", "scope selection", "select module"], "scope"),

    # semantic-ir — SIR generation, contracts, semantic representation
    (["semantic ir", "sir", "semantic", "ir generation", "contract", "interface", "semantic representation", "regenerate sir", "sir generation"], "semantic-ir"),

    # user-stories — user story generation, epics, features, personas, acceptance criteria
    (["user stor", "user-stor", "epic", "feature", "persona", "acceptance criteria", "story point", "backlog", "sprint", "agile", "gherkin", "given when then"], "user-stories"),

    # modernize — target technology, framework, architecture, stack
    (["technology", "framework", "modernize", "stack", "architecture", "target", "dotnet", ".net", "java", "spring", "microservice", "cloud native", "aurora", "postgresql"], "modernize"),

    # test-scenarios — test scenario generation, test cases, playwright scripts
    (["test scenario", "test case", "test script", "playwright", "e2e", "end to end", "automation", "coverage", "test data"], "test-scenarios"),

    # tests — generated tests, xunit, test run
    (["test", "xunit", "unit test", "integration test", "test run", "test result", "failing test"], "tests"),

    # failures — failure analysis, risk, error
    (["failure", "fail", "error", "risk", "issue", "bug", "problem", "residual", "analysis"], "failures"),

    # artifacts — final output, download, github, pack
    (["artifact", "download", "pack", "github", "export", "publish", "final", "output", "deploy"], "artifacts"),
]


def classify_comment(comment: str, current_phase: str) -> tuple[str, str]:
    """Classify the feedback comment to a target phase.

    Returns (target_phase, reasoning).
    Tries keyword matching first; falls back to Bedrock LLM if no match.
    Raises on Bedrock failure so the caller can handle gracefully.
    """
    lower = comment.lower()

    for keywords, phase in _KEYWORD_MAP:
        if any(k in lower for k in keywords):
            reasoning = f"Keyword match — comment references '{phase}' phase concepts."
            logger.info("HITL Orchestrator: keyword classified comment to phase='%s'", phase)
            return phase, reasoning

    # Bedrock LLM fallback
    logger.info("HITL Orchestrator: no keyword match, invoking Bedrock for classification")
    from .bedrock_skills import invoke_bedrock

    prompt = (
        f"You are the AWS Modernization HITL Orchestrator.\n"
        f"The reviewer is currently on the '{current_phase}' phase and submitted this feedback:\n"
        f"\"{comment}\"\n\n"
        f"Which pipeline phase does this feedback most directly require revisiting?\n"
        f"Choose exactly one from: intake, discovery, graph, scope, requirements, backlog, modernize, tests.\n"
        f"Return ONLY valid JSON: {{\"target_phase\": \"<phase>\", \"reasoning\": \"<one sentence>\"}}"
    )

    response = invoke_bedrock(
        "You are a modernization pipeline orchestrator. Respond only with JSON.",
        prompt,
        max_tokens=200,
        task_type="reasoning",
    )

    if not response:
        raise RuntimeError("Bedrock returned empty response during HITL classification")

    clean = response.strip()
    if "```json" in clean:
        clean = clean.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in clean:
        clean = clean.split("```", 1)[1].split("```", 1)[0].strip()

    parsed = json.loads(clean)  # raises json.JSONDecodeError on bad response
    phase = parsed.get("target_phase", "").strip()
    if phase not in PHASE_ORDER:
        raise ValueError(f"Bedrock returned unknown phase: '{phase}'")

    reasoning = parsed.get("reasoning", "LLM-classified phase.")
    logger.info("HITL Orchestrator: Bedrock classified comment to phase='%s'", phase)
    return phase, reasoning


# Data keys to clear per phase and all phases after it
_PHASE_DATA_KEYS: dict[str, list[tuple[str, str | None]]] = {
    # (top-level key, seed sub-key or None)
    "scope":        [("scope", None)],
    "semantic-ir":  [("sirMeta", None), ("seed", "semantic_ir")],
    "user-stories": [("userStories", None)],
    "test-scenarios": [("testScenarios", None)],
    "modernize":    [("seed", "target")],
    "discovery":    [("seed", "applied_graph"), ("seed", "scope_analysis")],
    "graph":        [("seed", "applied_graph"), ("seed", "scope_analysis")],
}


def _clear_phase_data(engagement: dict, phase: str) -> None:
    """Clear the generated data for a specific phase."""
    for top_key, sub_key in _PHASE_DATA_KEYS.get(phase, []):
        if sub_key is None:
            engagement.pop(top_key, None)
        else:
            if top_key in engagement and isinstance(engagement[top_key], dict):
                engagement[top_key].pop(sub_key, None)


def rollback_to_phase(engagement: dict, target_phase: str) -> None:
    """Reset all gates from target_phase onwards and clear generated data.

    Everything before target_phase is preserved intact.
    Mutates engagement in-place.
    """
    if target_phase not in PHASE_ORDER:
        raise ValueError(f"Unknown phase for rollback: '{target_phase}'")

    t_idx = PHASE_ORDER.index(target_phase)
    gates = engagement.get("gates", {})

    for phase in PHASE_ORDER[t_idx:]:
        if phase in gates:
            gates[phase]["decision"] = None
            gates[phase]["status"] = "review-needed" if phase == target_phase else "stale"
            gates[phase]["comment"] = None
        # Clear generated data for this phase
        _clear_phase_data(engagement, phase)

    engagement["currentPhase"] = target_phase
    engagement["status"] = f"hitl-{target_phase}"
    logger.info(
        "HITL Orchestrator: rolled back engagement '%s' to phase='%s' and cleared downstream data",
        engagement.get("id"),
        target_phase,
    )


def run(engagement: dict, comment: str, current_phase: str) -> dict:
    """Entry point for the HITL orchestrator.

    Returns:
        {
            "ok": bool,
            "targetPhase": str,
            "reasoning": str,
            "actionTaken": str,
            "engagement": dict,   # only present on success
            "error": str,         # only present on failure
        }

    On any failure the engagement state is NOT mutated.
    """
    logger.info(
        "HITL Orchestrator: received feedback from phase='%s' | comment='%.80s'",
        current_phase,
        comment,
    )

    # --- 1. Classify ---
    try:
        target_phase, reasoning = classify_comment(comment, current_phase)
    except json.JSONDecodeError as exc:
        logger.error("HITL Orchestrator: Bedrock returned invalid JSON — %s", exc)
        return {"ok": False, "error": "LLM returned malformed response. Pipeline unchanged."}
    except ValueError as exc:
        logger.error("HITL Orchestrator: classification returned invalid phase — %s", exc)
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("HITL Orchestrator: Bedrock classification failed — %s", exc)
        return {"ok": False, "error": "Could not classify comment (LLM unavailable). Pipeline unchanged."}

    # --- 2. Validate rollback is meaningful ---
    current_idx = PHASE_ORDER.index(current_phase) if current_phase in PHASE_ORDER else len(PHASE_ORDER)
    target_idx = PHASE_ORDER.index(target_phase)

    if target_idx >= current_idx:
        action = f"Target phase '{target_phase}' is at or after current phase '{current_phase}'. No rollback needed."
        logger.info("HITL Orchestrator: %s", action)
    else:
        # --- 3. Rollback ---
        try:
            rollback_to_phase(engagement, target_phase)
            action = f"Pipeline rolled back to '{target_phase}'. All downstream gates reset."
        except Exception as exc:
            logger.exception("HITL Orchestrator: rollback failed — %s", exc)
            return {"ok": False, "error": f"Rollback failed: {exc}"}

    # --- 4. Append to feedback history (audit trail) ---
    engagement.setdefault("feedbackHistory", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fromPhase": current_phase,
        "targetPhase": target_phase,
        "comment": comment,
        "reasoning": reasoning,
        "actionTaken": action,
    })

    logger.info("HITL Orchestrator: completed successfully → targetPhase='%s'", target_phase)

    return {
        "ok": True,
        "targetPhase": target_phase,
        "reasoning": reasoning,
        "actionTaken": action,
        "engagement": engagement,
    }
