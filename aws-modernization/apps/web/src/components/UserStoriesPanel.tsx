import { useEffect, useRef, useState } from "react";
import { api, type Engagement, type Epic, type Feature, type Story, type StoryEdit } from "../api";
import { TrackerIntegration } from "./TrackerIntegration";

export function UserStoriesPanel({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const scopeId = e.scope?.capabilityId ?? null;
  const sirCount = (e.seed?.semantic_ir ?? []).filter((s) => s.module === scopeId).length;
  const us = e.userStories && e.userStories.scope === scopeId ? e.userStories : null;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refine, setRefine] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adoBusy, setAdoBusy] = useState(false);
  const [adoResult, setAdoResult] = useState<{ ok: boolean; text: string; details?: string[] } | null>(null);
  const attempted = useRef<string | null>(null);

  /** Push every generated story (with its epic and features) to Azure DevOps, using the ADO_* settings on the server. */
  async function pushToAdo() {
    const total = e.userStories?.counts.stories ?? 0;
    if (!window.confirm(`Create work items in Azure DevOps for all ${total} user stories, with their epic and features?\n\n` +
                        "Items pushed before are not created again.")) return;
    setAdoBusy(true);
    setAdoResult(null);
    try {
      const r = await api.pushUserStories(e.id, { provider: "ado", apply: true, confirm: true, allowTemplate: true });
      const created = r.summary.created ?? 0;
      const existing = r.summary.exists ?? 0;
      const problems = r.rows.filter((row) => row.action === "failed" || row.action === "skipped");
      if (problems.length > 0) {
        setAdoResult({
          ok: false,
          text: `Push to Azure DevOps (${r.target}) finished with ${problems.length} error${problems.length > 1 ? "s" : ""}` +
                (created ? `; ${created} item${created > 1 ? "s were" : " was"} created` : "") + ".",
          details: problems.slice(0, 5).map((row) => `${row.title}: ${row.error ?? row.note ?? row.action}`),
        });
      } else {
        setAdoResult({
          ok: true,
          text: `Pushed to Azure DevOps (${r.target}): ${created} work item${created === 1 ? "" : "s"} created` +
                (existing ? `, ${existing} already there` : "") + ".",
        });
      }
      onChange(await api.get(e.id));   // refresh "last push" and the tracker panel
    } catch (err) {
      setAdoResult({ ok: false, text: `Push to Azure DevOps failed: ${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setAdoBusy(false);
    }
  }

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
  const allStories = us.backlog.epics.flatMap((ep) => ep.features.flatMap((f) => f.stories));
  const storyTitles = new Map(allStories.map((s) => [s.id, s.title] as const));
  const refStory = us.backlog.estimationModel?.reference;
  const live = [...selected].filter((id) => storyTitles.has(id));   // drop ids of removed / regenerated stories
  const ctx: CardCtx = {
    engagementId: e.id,
    selected: new Set(live),
    order: new Map(allStories.map((s, i) => [s.id, i + 1] as const)),
    onChange,
    toggle: (id) =>
      setSelected((cur) => {
        const next = new Set(cur);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }),
  };

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 to-slate-50 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-xs font-bold text-white shadow-sm">US</span>
            <div>
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900">Epic → Feature → User Story backlog</h3>
              <p className="mt-0.5 text-xs text-slate-500">
                Each card is one user story: edit its title, description, acceptance criteria and labels in place (saved when you leave a
                field). Story points are sized on business complexity only, not on technical details.
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
            <button
              type="button"
              disabled={adoBusy || busy}
              onClick={() => void pushToAdo()}
              className="rounded-lg bg-blue-600 px-3 py-1.5 font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {adoBusy ? "Pushing to ADO…" : "Push to ADO"}
            </button>
          </div>
        </div>
        {error && <p role="alert" className="mt-2 text-xs text-red-700">Regeneration failed: {error}</p>}
        {adoResult && (
          <div
            role={adoResult.ok ? "status" : "alert"}
            className={`mt-3 flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-xs ${
              adoResult.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-800"
            }`}
          >
            <div>
              <p className="font-semibold">{adoResult.text}</p>
              {adoResult.details && (
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  {adoResult.details.map((d) => <li key={d}>{d}</li>)}
                </ul>
              )}
            </div>
            <button type="button" onClick={() => setAdoResult(null)} aria-label="Dismiss" className="font-bold opacity-60 hover:opacity-100">
              ×
            </button>
          </div>
        )}

        <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {(
            [
              ["Epics", us.counts.epics],
              ["Features", us.counts.features],
              ["Stories", us.counts.stories],
              ["Story points", us.counts.storyPoints],
              ["Open questions", us.counts.openQuestions],
            ] as [string, number][]
          ).map(([label, value]) => (
            <div key={label} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</dt>
              <dd className="text-lg font-bold text-slate-900">{value}</dd>
            </div>
          ))}
        </dl>
        {refStory?.storyId && (
          <p className="mt-2 text-[11px] text-slate-500">
            Sized relative to the reference story{" "}
            <span className="font-semibold text-slate-700">{storyTitles.get(refStory.storyId) ?? refStory.title}</span> = {refStory.points} pts
            (confirm in Q-EST-02).
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

      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
        <span>{live.length > 0 ? `${live.length} of ${allStories.length} stories selected for the tracker push` : "Tick stories to push only those to a tracker"}</span>
        <button type="button" onClick={() => setSelected(new Set(allStories.map((s) => s.id)))} className="font-semibold text-blue-700 hover:underline">
          Select all
        </button>
        {live.length > 0 && (
          <button type="button" onClick={() => setSelected(new Set())} className="font-semibold text-blue-700 hover:underline">
            Clear
          </button>
        )}
      </div>

      {us.backlog.epics.map((epic) => (
        <EpicBlock key={epic.id} epic={epic} ctx={ctx} />
      ))}

      {us.backlog.openQuestions.length > 0 && (
        <section className="rounded-xl border border-amber-200 bg-amber-50/70 p-5">
          <h4 className="text-xs font-bold uppercase tracking-wider text-amber-900">Open questions for the business</h4>
          <ul className="mt-2 space-y-1.5 text-xs text-amber-900">
            {us.backlog.openQuestions.map((q) => (
              <li key={q.id}>
                <span className="font-bold">{(q.storyId && storyTitles.get(q.storyId)) || "General"}:</span> {q.question}
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
        only={live}
      />
    </div>
  );
}

type CardCtx = {
  engagementId: string;
  selected: Set<string>;
  toggle: (id: string) => void;
  order: Map<string, number>;
  onChange: (eng: Engagement) => void;
};

const POINTS = [1, 2, 3, 5, 8, 13];

function EpicBlock({ epic, ctx }: { epic: Epic; ctx: CardCtx }) {
  const points = epic.features.reduce((n, f) => n + f.stories.reduce((m, s) => m + s.storyPoints, 0), 0);
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-xs">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-4">
        <span className="rounded bg-indigo-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">Epic</span>
        <h4 className="text-base font-bold text-slate-900">{epic.title}</h4>
        <span className="ml-auto font-mono text-[10px] text-slate-500">{points} pts</span>
      </div>
      <div className="space-y-3 p-4">
        {epic.features.map((f, i) => (
          <FeatureBlock key={f.id} feature={f} defaultOpen={i === 0} ctx={ctx} />
        ))}
      </div>
    </section>
  );
}

function FeatureBlock({ feature, defaultOpen, ctx }: { feature: Feature; defaultOpen: boolean; ctx: CardCtx }) {
  const points = feature.stories.reduce((n, s) => n + s.storyPoints, 0);
  return (
    <details open={defaultOpen} className="rounded-lg border border-slate-200 bg-slate-50/60">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-3">
        <span className="rounded bg-sky-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">Feature</span>
        <span className="text-sm font-semibold text-slate-900">{feature.title}</span>
        <span className="ml-auto font-mono text-[10px] text-slate-500">
          {feature.stories.length} {feature.stories.length === 1 ? "story" : "stories"} · {points} pts
        </span>
      </summary>
      <div className="space-y-3 border-t border-slate-200 p-3">
        {feature.stories.map((s) => (
          <StoryCard key={s.id} story={s} ctx={ctx} />
        ))}
      </div>
    </details>
  );
}

/** "SIR-001.R1".."SIR-001.R6", "SIR-001.R9" -> "R1–R6, R9" (same as the backend's citation format). */
function citeRules(ids: string[]): string {
  const short = [...new Set(ids.map((r) => r.split(".").pop() ?? r))];
  const nums = short.map((r) => /^R(\d+)$/.exec(r)).map((m) => (m ? Number(m[1]) : NaN));
  if (nums.some(Number.isNaN)) return short.join(", ");
  const sorted = [...new Set(nums)].sort((a, b) => a - b);
  const parts: string[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const start = sorted[i];
    while (i + 1 < sorted.length && sorted[i + 1] === sorted[i] + 1) i++;
    parts.push(start === sorted[i] ? `R${start}` : `R${start}–R${sorted[i]}`);
  }
  return parts.join(", ");
}

/** Older backlogs stored multi-line Gherkin scenarios: show each as one line so "one per line" holds. */
const oneLine = (a: string) => a.replace(/^\s*Scenario:[^\n]*\n/, "").replace(/\s*\n\s*/g, ", ").replace(/,\s*(When|Then|And)\b/g, (_, w: string) => `, ${w.toLowerCase()}`);

type Draft = { title: string; description: string; criteria: string; labels: string };

const draftOf = (s: Story): Draft => ({
  title: s.title,
  description: s.description ?? "",
  criteria: s.acceptanceCriteria.map(oneLine).join("\n"),
  labels: s.labels.join(", "),
});

const FIELD = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100";
const LABEL = "mb-1 block text-sm text-slate-600";

/** One user story, as an editable card: Title, Description, Acceptance criteria (one per line), Labels. */
function StoryCard({ story, ctx }: { story: Story; ctx: CardCtx }) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(story));
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const saved = useRef<Draft>(draftOf(story));

  // The server's copy changed (regenerate, or a save came back): take it, unless the field is mid-edit.
  useEffect(() => {
    const next = draftOf(story);
    setDraft((d) => ({
      title: d.title === saved.current.title ? next.title : d.title,
      description: d.description === saved.current.description ? next.description : d.description,
      criteria: d.criteria === saved.current.criteria ? next.criteria : d.criteria,
      labels: d.labels === saved.current.labels ? next.labels : d.labels,
    }));
    saved.current = next;
  }, [story]);

  async function save(changes: StoryEdit) {
    setStatus("saving");
    setError(null);
    try {
      ctx.onChange(await api.updateStory(ctx.engagementId, story.id, changes));
      setStatus("saved");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function commit(field: keyof Draft) {
    if (draft[field] === saved.current[field]) return;
    if (field === "title") void save({ title: draft.title });
    if (field === "description") void save({ description: draft.description });
    if (field === "criteria") void save({ acceptanceCriteria: draft.criteria.split("\n").map((l) => l.trim()).filter(Boolean) });
    if (field === "labels") void save({ labels: draft.labels.split(",").map((l) => l.trim()).filter(Boolean) });
  }

  async function remove() {
    if (!window.confirm(`Remove ${story.id} from the backlog?`)) return;
    try {
      ctx.onChange(await api.removeStory(ctx.engagementId, story.id));
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const rules = citeRules((story.trace.ruleIds ?? [story.trace.ruleId]).filter((r): r is string => !!r));
  const id = `US-${String(ctx.order.get(story.id) ?? 0).padStart(3, "0")}`;
  const bind = (field: keyof Draft) => ({
    value: draft[field],
    onChange: (ev: { target: { value: string } }) => setDraft((d) => ({ ...d, [field]: ev.target.value })),
    onBlur: () => commit(field),
  });

  return (
    <article className="rounded-xl border border-slate-200 bg-white shadow-xs">
      <header className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-5 py-3.5">
        <input
          type="checkbox"
          checked={ctx.selected.has(story.id)}
          onChange={() => ctx.toggle(story.id)}
          aria-label={`Select ${id}`}
          className="h-4 w-4 rounded border-slate-300"
        />
        <span className="text-sm font-bold text-slate-900" title={story.id}>{id}</span>
        <span className="min-w-0 flex-1 truncate text-sm text-slate-500">
          {rules && `covers ${rules}`}
          {story.behaviour && `${rules ? " · " : ""}${story.behaviour}`}
        </span>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          <select
            value={story.storyPoints}
            onChange={(ev) => void save({ storyPoints: Number(ev.target.value) })}
            aria-label="Story points"
            className="rounded border border-slate-300 bg-white px-1.5 py-0.5 font-mono text-xs text-slate-800"
          >
            {(POINTS.includes(story.storyPoints) ? POINTS : [...POINTS, story.storyPoints]).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          pts
        </label>
        <span className="w-12 text-right text-[11px] text-slate-400" aria-live="polite">
          {status === "saving" ? "Saving…" : status === "saved" ? "Saved" : ""}
        </span>
        <button type="button" onClick={() => void remove()} className="text-sm font-semibold text-blue-700 hover:underline">
          Remove
        </button>
      </header>
      <div className="space-y-4 px-5 py-4">
        <div>
          <label htmlFor={`${story.id}-title`} className={LABEL}>Title</label>
          <input id={`${story.id}-title`} {...bind("title")} className={FIELD} />
        </div>
        <div>
          <label htmlFor={`${story.id}-desc`} className={LABEL}>Description</label>
          <textarea id={`${story.id}-desc`} rows={3} {...bind("description")} className={`${FIELD} resize-y leading-relaxed`} />
        </div>
        <div>
          <label htmlFor={`${story.id}-ac`} className={LABEL}>Acceptance criteria (one per line)</label>
          <textarea id={`${story.id}-ac`} rows={4} {...bind("criteria")} className={`${FIELD} resize-y leading-relaxed`} />
        </div>
        <div>
          <label htmlFor={`${story.id}-labels`} className={LABEL}>Labels (comma separated)</label>
          <input id={`${story.id}-labels`} {...bind("labels")} className={FIELD} />
        </div>
        {error && <p role="alert" className="text-xs text-red-700">Not saved: {error}</p>}
      </div>
    </article>
  );
}
