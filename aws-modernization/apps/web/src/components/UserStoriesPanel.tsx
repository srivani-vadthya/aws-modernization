import { useEffect, useRef, useState } from "react";
import { api, type Engagement, type Epic, type Feature, type Story } from "../api";
import { TrackerIntegration } from "./TrackerIntegration";

const TYPE_CLS: Record<Story["type"], string> = {
  functional: "bg-blue-100 text-blue-700 border-blue-200",
  flow: "bg-violet-100 text-violet-700 border-violet-200",
  enabler: "bg-slate-100 text-slate-600 border-slate-200",
};

const PRIORITY_CLS: Record<string, string> = {
  Must: "bg-red-50 text-red-700 border-red-200",
  Should: "bg-amber-50 text-amber-700 border-amber-200",
  Could: "bg-sky-50 text-sky-700 border-sky-200",
  "Won't": "bg-slate-50 text-slate-500 border-slate-200",
};

export function UserStoriesPanel({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const scopeId = e.scope?.capabilityId ?? null;
  const sirCount = (e.seed?.semantic_ir ?? []).filter((s) => s.module === scopeId).length;
  const us = e.userStories && e.userStories.scope === scopeId ? e.userStories : null;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refine, setRefine] = useState(true);
  const attempted = useRef<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      onChange(await api.generateUserStories(e.id, { refine }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  // First visit with an approved Semantic IR: generate the backlog right away.
  useEffect(() => {
    const key = `${e.id}:${scopeId}`;
    if (!scopeId || sirCount === 0 || us || attempted.current === key) return;
    attempted.current = key;
    void generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e.id, scopeId, sirCount, !!us]);

  if (!scopeId || sirCount === 0) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center text-sm text-amber-800">
        User stories are generated from the Semantic IR. Select a scope and generate its Semantic IR first.
      </div>
    );
  }

  if (!us) {
    return busy || !error ? (
      <div className="flex items-center gap-3 rounded-xl border border-blue-200 bg-blue-50/60 p-6 text-sm text-blue-900">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        <div>
          <p className="font-semibold">Generating the backlog from {sirCount} Semantic IR contract{sirCount !== 1 ? "s" : ""}…</p>
          <p className="mt-0.5 text-xs text-blue-800">
            The skill's Python script builds the Epic → Feature → Story scaffold, then the LLM determines the epic and rewrites each story
            in business language. This can take a minute.
          </p>
        </div>
      </div>
    ) : (
      <div className="space-y-3 rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">
        <p role="alert">User story generation failed: {error}</p>
        <button type="button" onClick={() => void generate()} className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold">
          Try again
        </button>
      </div>
    );
  }

  const errors = us.validation.filter((v) => v.level === "ERROR");
  const ref = us.refinement;

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 to-slate-50 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-xs font-bold text-white shadow-sm">US</span>
            <div>
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900">Epic → Feature → User Story backlog</h3>
              <p className="mt-0.5 text-xs text-slate-500">
                One feature per SIR contract, one story per piece of business behaviour (the rules of one legacy method, each an acceptance
                scenario), plus a flow story and a plumbing enabler. Every rule is traced to the legacy lines it came from.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <label className="flex items-center gap-1.5 text-[11px] text-slate-600">
              <input type="checkbox" checked={refine} onChange={(ev) => setRefine(ev.target.checked)} /> Refine with LLM
            </label>
            <button
              type="button"
              disabled={busy}
              onClick={() => void generate()}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {busy ? "Generating…" : "Regenerate"}
            </button>
            <a href={api.userStoriesExportUrl(e.id, "md")} className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50">
              Markdown
            </a>
            <a href={api.userStoriesExportUrl(e.id, "json")} className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50">
              JSON
            </a>
          </div>
        </div>
        {error && <p role="alert" className="mt-2 text-xs text-red-700">Regeneration failed: {error}</p>}

        <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {(
            [
              ["Epics", us.counts.epics],
              ["Features", us.counts.features],
              ["Stories", us.counts.stories],
              ...(us.counts.humanPoints != null
                ? [
                    ["Story points (AI-assisted)", us.counts.storyPoints, "Effort for the team working with AI from the SIR; this is what to plan with"],
                    ["AI efficiency", `${Math.round((us.counts.aiEfficiency ?? 0) * 100)}%`, "Share of the manual effort that AI removes"],
                  ]
                : [["Story points", us.counts.storyPoints]]),
              ["Open questions", us.counts.openQuestions],
            ] as [string, number | string, string?][]
          ).map(([label, value, hint]) => (
            <div key={label} title={hint} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</dt>
              <dd className="text-lg font-bold text-slate-900">{value}</dd>
            </div>
          ))}
        </dl>
        {us.backlog.estimationModel && (
          <p className="mt-2 text-[11px] text-slate-500">
            Team AI capability: <span className="font-semibold text-slate-700">{us.backlog.estimationModel.capability}</span>
            {us.backlog.estimationModel.assumed && " (assumed, confirm in Q-EST-01)"}. L0 no AI tools · L1 autocomplete/chat · L2 AI agent with
            SIR context · L3 plus an automated parity harness.
            {us.backlog.estimationModel.reference && (
              <>
                {" "}Sized on Complexity + Amount of work + Risk & uncertainty (1–5 each) relative to the reference story{" "}
                <span className="font-semibold text-slate-700">
                  {us.backlog.estimationModel.reference.storyId ?? us.backlog.estimationModel.reference.title}
                </span>{" "}
                = {us.backlog.estimationModel.reference.points} pts (confirm in Q-EST-02).
              </>
            )}
          </p>
        )}
        <p className="mt-3 text-[11px] text-slate-500">
          {ref.status === "skipped"
            ? "Template wording only: LLM refinement was switched off."
            : ref.status === "unavailable"
              ? "The LLM was unavailable, so stories keep their template wording. Regenerate once it is reachable."
              : `${ref.refined} of ${ref.total} stories reworded by ${ref.model ?? "the LLM"}${ref.status === "partial" ? "; the rest keep template wording" : ""}.`}
          {" "}Epic: {us.epicDetermination.status === "llm" ? `determined by ${us.epicDetermination.model}` : "named from the module"}.
        </p>
        {errors.length > 0 && (
          <ul role="alert" className="mt-3 list-disc space-y-0.5 rounded-lg border border-red-200 bg-red-50 py-2 pl-7 pr-3 text-xs text-red-700">
            {errors.map((v) => <li key={v.message}>{v.message}</li>)}
          </ul>
        )}
      </section>

      {us.backlog.epics.map((epic) => (
        <EpicBlock key={epic.id} epic={epic} />
      ))}

      {us.backlog.openQuestions.length > 0 && (
        <section className="rounded-xl border border-amber-200 bg-amber-50/70 p-5">
          <h4 className="text-xs font-bold uppercase tracking-wider text-amber-900">Open questions for the business</h4>
          <ul className="mt-2 space-y-1.5 text-xs text-amber-900">
            {us.backlog.openQuestions.map((q) => (
              <li key={q.id}>
                <span className="font-mono font-bold">{q.storyId ?? q.id}</span> {q.question}
              </li>
            ))}
          </ul>
        </section>
      )}

      <details className="rounded-xl border border-slate-200 bg-white shadow-xs">
        <summary className="cursor-pointer px-5 py-3 text-xs font-bold uppercase tracking-wider text-slate-500">
          Generated Python scripts &amp; artifacts
        </summary>
        <div className="space-y-3 border-t border-slate-100 px-5 py-4 text-xs text-slate-600">
          <p>
            Written to <span className="font-mono">artifacts/user-stories/</span> of this engagement, following the
            <span className="font-mono"> sir-user-story-generator</span> skill, so the backlog can be rebuilt and pushed outside the app:
          </p>
          <ul className="grid gap-1 font-mono text-[11px] sm:grid-cols-2">
            {us.files.map((f) => <li key={f} className="rounded bg-slate-50 px-2 py-1">{f}</li>)}
          </ul>
          <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] text-emerald-300">{us.commands.join("\n")}</pre>
        </div>
      </details>

      <TrackerIntegration
        engagementId={e.id}
        stories={us}
        onPushed={() => void api.get(e.id).then(onChange)}
      />
    </div>
  );
}

function EpicBlock({ epic }: { epic: Epic }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-xs">
      <div className="border-b border-slate-100 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-indigo-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">Epic</span>
          <span className="font-mono text-[11px] text-slate-500">{epic.id}</span>
          <h4 className="text-base font-bold text-slate-900">{epic.title}</h4>
        </div>
        <p className="mt-1 text-xs text-slate-600">{epic.description}</p>
        {epic.businessOutcome && (
          <p className="mt-1.5 text-xs text-emerald-800">
            <span className="font-bold">Business outcome:</span> {epic.businessOutcome}
          </p>
        )}
        {epic.approach && (
          <p className="mt-1.5 text-xs text-slate-600">
            <span className="font-bold text-slate-700">Approach:</span> {epic.approach}
          </p>
        )}
      </div>
      <div className="space-y-3 p-4">
        {epic.features.map((f, i) => (
          <FeatureBlock key={f.id} feature={f} defaultOpen={i === 0} />
        ))}
      </div>
    </section>
  );
}

function FeatureBlock({ feature, defaultOpen }: { feature: Feature; defaultOpen: boolean }) {
  const points = feature.stories.reduce((n, s) => n + s.storyPoints, 0);
  const manual = feature.stories.reduce((n, s) => n + (s.estimation?.humanPoints ?? s.storyPoints), 0);
  return (
    <details open={defaultOpen} className="rounded-lg border border-slate-200 bg-slate-50/60">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-3">
        <span className="rounded bg-sky-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">Feature</span>
        <span className="font-mono text-[11px] text-slate-500">{feature.id}</span>
        <span className="text-sm font-semibold text-slate-900">{feature.title}</span>
        <span className="ml-auto font-mono text-[10px] text-slate-500">
          {feature.stories.length} stories · {points} pts{manual !== points && ` (manual ${manual})`}
        </span>
      </summary>
      <div className="space-y-2 border-t border-slate-200 px-4 py-3">
        <p className="text-xs text-slate-600">{feature.description}</p>
        {feature.stateMachine && (
          <p className="break-words font-mono text-[10px] text-violet-700">{feature.stateMachine}</p>
        )}
        {feature.legacyAssessment && feature.legacyAssessment.factors.length > 0 && (
          <details className="rounded-lg border border-amber-200 bg-amber-50/60">
            <summary className="cursor-pointer px-3 py-2 text-[11px] font-bold text-amber-900">
              Legacy findings (feed the complexity and risk factors) · {feature.legacyAssessment.paradigm}
            </summary>
            <ul className="space-y-1 border-t border-amber-200 px-3 py-2 text-[11px] text-amber-900">
              {feature.legacyAssessment.factors.map((f) => (
                <li key={f.category + f.finding}>
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold uppercase">{f.category}</span>{" "}
                  {f.finding}
                  {f.evidence && <span className="ml-1 break-all font-mono text-[10px] text-amber-700">{f.evidence}</span>}
                </li>
              ))}
              {feature.legacyAssessment.regressionScope.length > 0 && (
                <li className="pt-1 font-semibold">Regression scope: {feature.legacyAssessment.regressionScope.join(", ")}</li>
              )}
            </ul>
          </details>
        )}
        {feature.definitionOfDone && feature.definitionOfDone.length > 0 && (
          <details className="rounded-lg border border-slate-200 bg-white">
            <summary className="cursor-pointer px-3 py-2 text-[11px] font-bold text-slate-600">Definition of done</summary>
            <ul className="list-disc space-y-0.5 border-t border-slate-100 py-2 pl-7 pr-3 text-[11px] text-slate-600">
              {feature.definitionOfDone.map((d) => <li key={d}>{d}</li>)}
            </ul>
          </details>
        )}
        {feature.stories.map((s) => (
          <StoryRow key={s.id} story={s} />
        ))}
      </div>
    </details>
  );
}

function StoryRow({ story }: { story: Story }) {
  const [open, setOpen] = useState(false);
  const t = story.trace;
  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-slate-50">
        <span className="text-[10px] text-slate-400">{open ? "▼" : "▶"}</span>
        <span className="shrink-0 font-mono text-[10px] font-bold text-blue-700">{story.id}</span>
        <span className="min-w-0 flex-1 truncate text-xs text-slate-900">{story.title}</span>
        <span className={`hidden shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase sm:block ${TYPE_CLS[story.type]}`}>{story.type}</span>
        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold ${PRIORITY_CLS[story.priority] ?? ""}`}>{story.priority}</span>
        <span
          className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600"
          title={story.estimation?.humanPoints != null ? `AI-assisted ${story.storyPoints} pts; manual baseline ${story.estimation.humanPoints} pts` : undefined}
        >
          {story.storyPoints} pts
          {story.estimation?.humanPoints != null && story.estimation.humanPoints !== story.storyPoints && (
            <span className="text-slate-400"> / {story.estimation.humanPoints}</span>
          )}
        </span>
        {story.narrativeSource === "template" && (
          <span className="shrink-0 rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[9px] font-bold text-amber-700" title="Mechanical wording, not yet refined">template</span>
        )}
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-100 px-4 py-3 text-xs">
          <p className="leading-relaxed text-slate-800">
            <span className="font-semibold">As a</span> {story.narrative.asA}, <span className="font-semibold">I want</span> {story.narrative.iWant},{" "}
            <span className="font-semibold">so that</span> {story.narrative.soThat}.
          </p>
          {story.description && <p className="text-slate-600">{story.description}</p>}
          {story.estimation?.complexity && <EstimateBlock story={story} />}
          <div>
            <h6 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Acceptance criteria</h6>
            <div className="space-y-1.5">
              {story.acceptanceCriteria.map((a, i) => (
                <pre key={i} className="whitespace-pre-wrap rounded bg-slate-900 px-3 py-2 font-mono text-[11px] text-emerald-300">{a}</pre>
              ))}
            </div>
          </div>
          <div className="grid gap-2 rounded-lg bg-slate-50 p-3 sm:grid-cols-2">
            <div>
              <span className="block text-[10px] font-semibold uppercase text-slate-400">Legacy trace</span>
              <span className="font-mono text-[11px] text-slate-700">{t.sirId} · {t.ruleId ?? (t.ruleIds ?? []).join(", ")}</span>
            </div>
            <div>
              <span className="block text-[10px] font-semibold uppercase text-slate-400">Source lines · AST node</span>
              <span className="break-all font-mono text-[11px] text-blue-700">{t.legacyLines || "n/a"}</span>
              <span className="block break-all font-mono text-[10px] text-purple-700">{t.astNode}</span>
            </div>
            {t.snippet && (
              <pre className="overflow-x-auto rounded bg-slate-800 px-2.5 py-2 font-mono text-[10px] text-slate-300 sm:col-span-2">{t.snippet}</pre>
            )}
          </div>
          {story.trustBoundary?.startsWith("Deterministic") && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-[11px] font-semibold text-red-700">
              🔒 {story.trustBoundary}: wording may not change its numbers, literals or conditions.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

const FACTORS: { key: "complexity" | "work" | "risk"; label: string }[] = [
  { key: "complexity", label: "Complexity" },
  { key: "work", label: "Amount of work" },
  { key: "risk", label: "Risk & uncertainty" },
];

const CONFIDENCE_CLS: Record<string, string> = {
  high: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-red-100 text-red-800",
};

/** Story points from evidence: three 1-5 factors, relative to the reference story, manual vs AI-assisted. */
function EstimateBlock({ story }: { story: Story }) {
  const e = story.estimation!;
  return (
    <div className="space-y-2 rounded-lg border border-slate-200 bg-white p-3 text-[11px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-bold text-slate-900">Estimate</span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-slate-700">
          C{e.complexity!.level} + W{e.work!.level} + R{e.risk!.level} = {e.factorSum} → {e.humanPoints} pts manual
        </span>
        <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-mono text-emerald-800">
          {story.storyPoints} pts AI-assisted ({Math.round((e.aiEfficiency ?? 0) * 100)}% saved, {e.capability})
        </span>
        {e.confidence && (
          <span className={`rounded px-1.5 py-0.5 font-semibold ${CONFIDENCE_CLS[e.confidence] ?? ""}`}>{e.confidence} confidence</span>
        )}
      </div>
      <table className="w-full border-collapse">
        <tbody>
          {FACTORS.map(({ key, label }) => {
            const f = e[key]!;
            return (
              <tr key={key} className="border-t border-slate-100 align-top">
                <td className="w-32 py-1 pr-2 font-semibold text-slate-700">{label}</td>
                <td className="w-28 py-1 pr-2">
                  <span className="font-mono">{f.level}/5</span> <span className="text-slate-500">{f.label}</span>
                  {e.aiFactors && <span className="block text-[10px] text-emerald-700">AI: {e.aiFactors[key]}</span>}
                </td>
                <td className="py-1 text-slate-600">{f.evidence.join("; ")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {e.reference && <p className="text-slate-500">{e.reference}.</p>}
      {e.inputsNeeded && e.inputsNeeded.length > 0 && (
        <p className="text-slate-600">
          <span className="font-semibold">Inputs needed to size it:</span> {e.inputsNeeded.join("; ")}
        </p>
      )}
      {e.notes && e.notes.length > 0 && <p className="text-slate-500">{e.notes.join("; ")}</p>}
    </div>
  );
}
