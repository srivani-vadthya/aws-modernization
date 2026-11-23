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
    "requirements",
    "backlog",
    "modernize",
    "tests",
    "failures",
    "artifacts",
]

# Keyword-based fast-path classification (no LLM cost for obvious cases)
_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["graph", "akg", "knowledge graph", "dependency", "call graph", "ast", "relationship"], "graph"),
    (["scope", "module", "capability", "boundary", "partition", "domain", "business module"], "scope"),
    (["requirement", "rule", "spec", "functional", "business rule", "regulation"], "requirements"),
    (["backlog", "story", "epic", "sprint", "ado", "points", "spike", "user story"], "backlog"),
    (["technology", "framework", "modernize", "stack", "architecture", "target"], "modernize"),
    (["test", "playwright", "e2e", "acceptance", "gherkin", "scenario"], "tests"),
    (["discovery", "inventory", "classify", "asset", "scan"], "discovery"),
    (["intake", "upload", "source", "git", "zip", "folder"], "intake"),
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


def rollback_to_phase(engagement: dict, target_phase: str) -> None:
    """Reset all gates from target_phase onwards.

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

    engagement["currentPhase"] = target_phase
    engagement["status"] = f"hitl-{target_phase}"
    logger.info(
        "HITL Orchestrator: rolled back engagement '%s' to phase='%s'",
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
