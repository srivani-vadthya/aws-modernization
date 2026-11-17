import { useState } from "react";
import type { ClarificationQuestion } from "../api";

type Props = {
  phase: string;
  questions: ClarificationQuestion[];
  onCancel: () => void;
  onSubmit: (answers: Record<string, string>) => Promise<void>;
  busy?: boolean;
  error?: string | null;
};

export function ClarificationModal({ phase, questions, onCancel, onSubmit, busy, error }: Props) {
  const [vals, setVals] = useState<Record<string, string>>(() =>
    Object.fromEntries(questions.map((q) => [q.id, q.recommended ?? (q.options?.[0] || "")]))
  );
  const [otherText, setOtherText] = useState<Record<string, string>>({});

  const resolveAnswer = (qId: string) => {
    if (vals[qId] === "__other") {
      return otherText[qId]?.trim() || "Custom answer";
    }
    return vals[qId] || questions.find((q) => q.id === qId)?.recommended || "";
  };

  const handleConfirm = async () => {
    const answers = Object.fromEntries(questions.map((q) => [q.id, resolveAnswer(q.id)]));
    await onSubmit(answers);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-2xl">
        {/* Header */}
        <div className="border-b border-slate-200 p-6 bg-slate-50/70">
          <div className="flex items-center gap-2.5">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-100 text-xs font-bold text-blue-700">
              HITL
            </span>
            <h3 className="text-base font-bold text-slate-900">
              AI Clarifying Decisions Required: {phase.toUpperCase()}
            </h3>
          </div>
          <p className="mt-1.5 text-xs text-slate-600 leading-relaxed">
            The modernization agent requires human-in-the-loop decisions before proceeding. Your answers will be recorded into the compliance audit trail.
          </p>
        </div>

        {/* Body */}
        <div className="space-y-6 p-6">
          {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          {questions.map((q, idx) => (
            <div key={q.id} className="rounded-xl border border-slate-200 bg-slate-50/50 p-5">
              <div className="flex items-start justify-between gap-2">
                <h4 className="text-sm font-bold text-slate-900">
                  {idx + 1}. {q.text}
                </h4>
              </div>

              {/* Rationale */}
              <p className="mt-1.5 text-xs text-amber-800 bg-amber-50 rounded-md p-2.5 border border-amber-200/80">
                <span className="font-bold text-amber-900">Why the AI is asking:</span> {q.why}
              </p>

              {/* Options */}
              <div className="mt-4 space-y-2">
                {(q.options || []).map((opt) => {
                  const isRec = opt === q.recommended;
                  const checked = vals[q.id] === opt;
                  return (
                    <label
                      key={opt}
                      className={`flex cursor-pointer items-center justify-between rounded-lg border p-3 text-xs transition ${
                        checked
                          ? "border-blue-600 bg-blue-50/90 text-blue-900 font-semibold"
                          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <input
                          type="radio"
                          name={`q-${q.id}`}
                          value={opt}
                          checked={checked}
                          onChange={() => setVals((prev) => ({ ...prev, [q.id]: opt }))}
                          className="text-blue-600 focus:ring-blue-500 h-4 w-4"
                        />
                        <span>{opt}</span>
                      </div>
                      {isRec && (
                        <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-700 uppercase">
                          AI Recommended
                        </span>
                      )}
                    </label>
                  );
                })}

                {/* Other/Custom Answer */}
                <label
                  className={`flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 text-xs transition ${
                    vals[q.id] === "__other"
                      ? "border-blue-600 bg-blue-50/90 text-blue-900"
                      : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="radio"
                    name={`q-${q.id}`}
                    value="__other"
                    checked={vals[q.id] === "__other"}
                    onChange={() => setVals((prev) => ({ ...prev, [q.id]: "__other" }))}
                    className="mt-0.5 text-blue-600 focus:ring-blue-500 h-4 w-4"
                  />
                  <div className="flex-1">
                    <span className="font-semibold">Other / Provide specific guidance</span>
                    {vals[q.id] === "__other" && (
                      <textarea
                        rows={2}
                        className="mt-2 w-full rounded border border-slate-300 bg-white p-2 text-xs text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none"
                        placeholder="Type custom instructions for this architectural choice..."
                        value={otherText[q.id] || ""}
                        onChange={(e) =>
                          setOtherText((prev) => ({ ...prev, [q.id]: e.target.value }))
                        }
                      />
                    )}
                  </div>
                </label>
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50 p-5">
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 disabled:opacity-50 transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void handleConfirm()}
            className="rounded-lg bg-blue-600 px-5 py-2 text-xs font-bold text-white shadow-sm hover:bg-blue-500 disabled:opacity-50 transition"
          >
            {busy ? "Saving Decisions…" : "Save Decisions & Approve Gate"}
          </button>
        </div>
      </div>
    </div>
  );
}
