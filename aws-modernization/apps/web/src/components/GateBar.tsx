import { useState } from "react";
import { api, type Engagement } from "../api";
import { ClarificationModal } from "./ClarificationModal";

type Props = {
  engagement: Engagement;
  phase: string;
  onDecide: (decision: "approved" | "rejected", comment: string, actor: string) => Promise<void>;
  onFeedback?: (comment: string) => Promise<void>;
  extraHint?: string;
};

export function GateBar({ engagement, phase, onDecide, onFeedback, extraHint }: Props) {
  const [comment, setComment] = useState("");
  const [actor, setActor] = useState("lead-architect");
  const [busy, setBusy] = useState(false);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const gate = engagement.gates[phase];
  const lockedPrev = isLocked(engagement, phase);

  const questions = engagement.seed?.clarifications?.[phase] || [];

  async function handleApproveClick() {
    if (questions.length > 0 && gate?.decision !== "approved") {
      setShowModal(true);
      return;
    }
    await go("approved");
  }

  async function go(decision: "approved" | "rejected") {
    setBusy(true);
    setError(null);
    try {
      await onDecide(decision, comment, actor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the gate decision. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  async function handleFeedbackTrigger() {
    if (!comment.trim() || !onFeedback) return;
    setBusy(true);
    setError(null);
    try {
      await onFeedback(comment);
      setFeedbackSuccess("Feedback sent to AgentCore Orchestrator. Upstream artifacts refreshed!");
      setComment("");
      setTimeout(() => setFeedbackSuccess(null), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not process feedback. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  async function handleClarificationSubmit(answers: Record<string, string>) {
    setBusy(true);
    setError(null);
    try {
      await api.clarifications(engagement.id, phase, answers);
      await onDecide("approved", comment || "Approved with AI clarification decisions", actor);
      setShowModal(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not approve this phase. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {showModal && (
        <ClarificationModal
          phase={phase}
          questions={questions}
          busy={busy}
          error={error}
          onCancel={() => setShowModal(false)}
          onSubmit={handleClarificationSubmit}
        />
      )}
      <div className="sticky bottom-0 mt-8 rounded-xl border border-slate-200 bg-white/95 px-5 py-4 shadow-lg backdrop-blur">
        {error && <p role="alert" className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        {feedbackSuccess && (
          <div className="mb-3 rounded-lg border border-purple-200 bg-purple-50 p-2.5 text-xs text-purple-900 font-semibold flex items-center justify-between">
            <span>⚡ {feedbackSuccess}</span>
          </div>
        )}
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[14rem] flex-1">
            <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">HITL Governance Comment & Feedback</label>
            <input
              className="mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-3.5 py-2 text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:border-blue-500 focus:outline-none transition shadow-2xs"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="e.g. 'AKG missed shared claims table', 'Scope boundary should include PolicySearch', or sign-off criteria…"
            />
          </div>
          <div>
            <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Sign-Off Persona &amp; Council Role</label>
            <select
              className="mt-1 w-52 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-800 focus:bg-white focus:border-blue-500 focus:outline-none transition shadow-2xs"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
            >
              <option value="Enterprise Solution Architect (Lead)">🏛️ Enterprise Architect</option>
              <option value="Chief Information Security Officer (InfoSec)">🛡️ InfoSec &amp; Compliance</option>
              <option value="Business Domain SME / Product Owner">💼 Business Domain SME</option>
              <option value="Lead Cloud Operations / SRE">⚙️ Cloud Platform SRE</option>
            </select>
          </div>
          
          {onFeedback && (
            <button
              type="button"
              disabled={busy || !comment.trim()}
              onClick={() => void handleFeedbackTrigger()}
              className="rounded-lg border border-purple-300 bg-purple-50 px-4 py-2 text-xs font-bold text-purple-700 hover:bg-purple-100 disabled:opacity-40 transition shadow-2xs flex items-center gap-1.5"
              title="AgentCore Orchestrator analyzes comment and regenerates impacted upstream phases (AKG, Scope, Requirements)"
            >
              <span>⚡ Route &amp; Regenerate</span>
            </button>
          )}

          <button
            type="button"
            disabled={busy || lockedPrev || gate?.decision === "approved"}
            onClick={() => void go("rejected")}
            className="rounded-lg border border-red-300 bg-red-50/80 px-4 py-2 text-xs font-bold text-red-700 hover:bg-red-100 disabled:opacity-40 transition shadow-2xs"
          >
            Reject Gate
          </button>
          <button
            type="button"
            disabled={busy || lockedPrev || gate?.decision === "approved"}
            onClick={() => void handleApproveClick()}
            className="relative rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-500 disabled:opacity-40 transition"
          >
            {questions.length > 0 && gate?.decision !== "approved" && (
              <span className="absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-amber-400 text-[10px] font-black text-slate-900 ring-2 ring-white">
                {questions.length}
              </span>
            )}
            Approve {phase.toUpperCase()}
          </button>
        </div>
        <p className="mt-2.5 text-xs text-slate-500 flex items-center gap-1.5">
          {lockedPrev ? (
            <span className="text-amber-800 font-medium">Complete and approve the prior phase before this gate can be unlocked.</span>
          ) : gate?.decision ? (
            <span className="text-emerald-700 font-semibold">Phase gate {gate.decision} by {gate.actor}.</span>
          ) : questions.length > 0 ? (
            <span className="text-blue-700 font-medium">Approving will present {questions.length} architectural decisions for human-in-the-loop review.</span>
          ) : (
            <span>{extraHint || "Every phase requires a human sign-off before downstream artifacts are frozen. You can also provide feedback to automatically re-route and regenerate upstream."}</span>
          )}
        </p>
      </div>
    </>
  );

}

function isLocked(engagement: Engagement, phase: string) {
  if (phase === "discovery") {
    return !engagement.inventory && engagement.gates.intake?.decision !== "approved";
  }
  // Clustered steps mapping:
  // - 'scope' requires 'discovery' (or 'graph') to be approved
  // - 'modernize' requires 'requirements' (or 'backlog') to be approved
  if (phase === "scope") {
    const disc = engagement.gates["discovery"]?.decision === "approved";
    const grph = engagement.gates["graph"]?.decision === "approved";
    return !(disc || grph);
  }
  if (phase === "modernize") {
    const reqs = engagement.gates["requirements"]?.decision === "approved";
    const bklg = engagement.gates["backlog"]?.decision === "approved";
    return !(reqs || bklg);
  }

  const order = [
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
  ];
  const i = order.indexOf(phase);
  if (i <= 0) return false;
  return engagement.gates[order[i - 1]]?.decision !== "approved";
}
