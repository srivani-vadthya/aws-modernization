import { useEffect, useState } from "react";
import { api, type PushReport, type PushRow, type TrackerProvider, type UserStoriesState } from "../api";

/** Which settings the user may edit per provider (non-secret). Values default from the server's environment. */
const FIELDS: Record<string, { key: string; label: string; placeholder?: string; options?: string[] }[]> = {
  jira: [
    { key: "baseUrl", label: "Site URL", placeholder: "https://your-org.atlassian.net" },
    { key: "projectKey", label: "Project key", placeholder: "MOD" },
    { key: "email", label: "Account email" },
    { key: "featureMode", label: "Features as", options: ["label", "epic"] },
    { key: "storyPointsField", label: "Story-points field", placeholder: "customfield_10016" },
  ],
  ado: [
    { key: "organization", label: "Organization" },
    { key: "project", label: "Project" },
    { key: "process", label: "Process", options: ["agile", "scrum", "cmmi"] },
  ],
  bitbucket: [
    { key: "workspace", label: "Workspace" },
    { key: "repository", label: "Repository" },
    { key: "username", label: "Username" },
  ],
  github: [{ key: "repository", label: "Repository", placeholder: "owner/repo" }],
};

const ACTION_CLS: Record<string, string> = {
  create: "bg-blue-100 text-blue-700",
  created: "bg-emerald-100 text-emerald-700",
  exists: "bg-slate-100 text-slate-600",
  folded: "bg-slate-100 text-slate-500",
  skipped: "bg-amber-100 text-amber-800",
  blocked: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-700",
};

export function TrackerIntegration({
  engagementId,
  stories,
  onPushed,
  only,
}: {
  engagementId: string;
  stories: UserStoriesState;
  onPushed: () => void;
  /** Story ids ticked on their cards: push only these (with their epic and feature). Empty = everything. */
  only?: string[];
}) {
  const [providers, setProviders] = useState<TrackerProvider[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [active, setActive] = useState<string>("jira");
  const [config, setConfig] = useState<Record<string, Record<string, string>>>({});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [report, setReport] = useState<PushReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [allowTemplate, setAllowTemplate] = useState(false);

  useEffect(() => {
    api
      .integrations()
      .then((r) => {
        setProviders(r.providers);
        const first = r.providers.find((p) => p.configured) ?? r.providers[0];
        if (first) setActive(first.id);
      })
      .catch((err: Error) => setLoadError(err.message));
  }, []);

  const selectionKey = (only ?? []).join(",");
  useEffect(() => setReport(null), [selectionKey]);   // a dry run is only valid for the selection it was made with

  const provider = providers?.find((p) => p.id === active);
  const templateCount = stories.counts.template;
  const settings = (key: string) => config[active]?.[key] ?? provider?.settings[key] ?? "";
  const effectiveConfig = () =>
    Object.fromEntries((FIELDS[active] ?? []).map((f) => [f.key, settings(f.key)]).filter(([, v]) => v));
  const credentials = () => Object.fromEntries(Object.entries(secrets).filter(([, v]) => v));

  async function run(apply: boolean) {
    setBusy(true);
    setError(null);
    try {
      const r = await api.pushUserStories(engagementId, {
        provider: active,
        apply,
        confirm: apply && confirm,
        only: only && only.length > 0 ? only : undefined,
        allowTemplate,
        config: effectiveConfig(),
        credentials: credentials(),
      });
      setReport(r);
      if (apply) {
        setSecrets({});
        setConfirm(false);
        onPushed();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const hasSecret = provider && provider.missing.length === 0;
  const secretNames = provider ? Object.keys(provider.secrets) : [];
  const canApply = !!report && !report.apply && confirm && !busy && (report.summary.create ?? 0) > 0;

  return (
    <details className="group rounded-xl border border-slate-200 bg-white shadow-xs">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <div>
          <h3 className="text-sm font-bold text-slate-900">
            Push to a tracker <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-500">Optional</span>
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Send the epic, features and stories to Jira, Azure DevOps, Bitbucket or GitHub. Connection details are read from the
            server environment. Nothing is sent without a preview and your confirmation.
          </p>
        </div>
        <span className="text-slate-400 transition group-open:rotate-180">▾</span>
      </summary>

      <div className="space-y-4 border-t border-slate-100 px-5 py-4">
        {loadError && <p role="alert" className="text-xs text-red-700">Could not read integration settings: {loadError}</p>}
        {!providers && !loadError && <p className="text-xs text-slate-500">Reading integration settings…</p>}

        {providers && (
          <>
            <div role="tablist" className="flex flex-wrap gap-2">
              {providers.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  role="tab"
                  aria-selected={p.id === active}
                  onClick={() => {
                    setActive(p.id);
                    setReport(null);
                    setError(null);
                    setConfirm(false);
                  }}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                    p.id === active ? "border-blue-500 bg-blue-50 text-blue-800" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {p.label}
                  <span className={`h-2 w-2 rounded-full ${p.configured ? "bg-emerald-500" : "bg-slate-300"}`} title={p.configured ? "Configured in environment" : "Not configured"} />
                </button>
              ))}
            </div>

            {provider && (
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-3">
                  <p className={`rounded-lg border px-3 py-2 text-xs ${hasSecret ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-slate-50 text-slate-600"}`}>
                    {hasSecret
                      ? `${provider.label} is fully configured from the environment.`
                      : `Not fully configured. Set in the server environment (or fill in below for this session): ${provider.missing.join(", ")}`}
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {(FIELDS[active] ?? []).map((f) => (
                      <label key={f.key} className="block text-[11px] font-semibold text-slate-600">
                        {f.label}
                        {f.options ? (
                          <select
                            value={settings(f.key) || f.options[0]}
                            onChange={(ev) => setConfig((c) => ({ ...c, [active]: { ...c[active], [f.key]: ev.target.value } }))}
                            className="mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-normal"
                          >
                            {f.options.map((o) => <option key={o}>{o}</option>)}
                          </select>
                        ) : (
                          <input
                            value={settings(f.key)}
                            placeholder={f.placeholder}
                            onChange={(ev) => setConfig((c) => ({ ...c, [active]: { ...c[active], [f.key]: ev.target.value } }))}
                            className="mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-normal focus:border-blue-500 focus:bg-white focus:outline-none"
                          />
                        )}
                      </label>
                    ))}
                  </div>
                  <div className="space-y-2">
                    {secretNames.map((name) => (
                      <label key={name} className="block text-[11px] font-semibold text-slate-600">
                        <span className="font-mono">{name}</span>{" "}
                        <span className={provider.secrets[name] ? "text-emerald-600" : "text-slate-400"}>
                          {provider.secrets[name] ? "✓ set in environment" : "not set"}
                        </span>
                        <input
                          type="password"
                          autoComplete="off"
                          value={secrets[name] ?? ""}
                          placeholder="Override for this session only (never stored)"
                          onChange={(ev) => setSecrets((s) => ({ ...s, [name]: ev.target.value }))}
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-normal focus:border-blue-500 focus:bg-white focus:outline-none"
                        />
                      </label>
                    ))}
                  </div>
                </div>

                <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">What will be created</h4>
                  <p className="text-xs text-slate-600">
                    {only && only.length > 0
                      ? `${only.length} selected stor${only.length === 1 ? "y" : "ies"}, with their epic and feature`
                      : `${stories.counts.epics} epic · ${stories.counts.features} feature${stories.counts.features !== 1 ? "s" : ""} · ${stories.counts.stories} stories (tick story cards to push only those)`}
                    {active === "jira" && settings("featureMode") !== "epic" && " (features become labels on their stories)"}
                  </p>
                  {templateCount > 0 && (
                    <label className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] text-amber-900">
                      <input type="checkbox" checked={allowTemplate} onChange={(ev) => { setAllowTemplate(ev.target.checked); setReport(null); }} className="mt-0.5" />
                      <span>
                        {templateCount} stories still use template wording (the LLM did not refine them). They are blocked unless you tick this.
                      </span>
                    </label>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void run(false)}
                      className="rounded-lg border border-blue-300 bg-white px-3.5 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                    >
                      {busy && !report?.apply ? "Working…" : "Preview (dry run)"}
                    </button>
                  </div>
                  {report && !report.apply && (
                    <div className="space-y-2 border-t border-slate-200 pt-3">
                      <label className="flex items-start gap-2 text-[11px] text-slate-700">
                        <input type="checkbox" checked={confirm} onChange={(ev) => setConfirm(ev.target.checked)} className="mt-0.5" />
                        <span>
                          I understand this creates {report.summary.create ?? 0} work item(s) in <strong>{report.target}</strong>, visible to other people and hard to undo.
                        </span>
                      </label>
                      <button
                        type="button"
                        disabled={!canApply || !report.ready && !Object.keys(credentials()).length}
                        onClick={() => void run(true)}
                        className="rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-500 disabled:opacity-40"
                      >
                        {busy ? "Pushing…" : `Push to ${report.label}`}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</p>}
            {report && <PushResult report={report} />}
            {!report && stories.lastPush && (
              <p className="text-[11px] text-slate-500">
                Last push: {stories.lastPush.label} · {stories.lastPush.target} ·{" "}
                {Object.entries(stories.lastPush.summary).map(([k, v]) => `${v} ${k}`).join(", ")} ·{" "}
                {new Date(stories.lastPush.at).toLocaleString()}
              </p>
            )}
          </>
        )}
      </div>
    </details>
  );
}

function PushResult({ report }: { report: PushReport }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="rounded-lg border border-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-4 py-2 text-xs">
        <span className="font-bold text-slate-800">
          {report.apply ? "Pushed to" : "Dry run for"} {report.label}
          <span className="ml-2 font-mono font-normal text-slate-500">{report.target}</span>
        </span>
        <span className="flex gap-2 text-[10px] font-semibold">
          {Object.entries(report.summary).map(([k, v]) => (
            <span key={k} className={`rounded px-2 py-0.5 ${ACTION_CLS[k] ?? "bg-slate-100"}`}>{v} {k}</span>
          ))}
        </span>
      </div>
      {!report.ready && !report.apply && (
        <p className="border-b border-amber-100 bg-amber-50 px-4 py-2 text-[11px] text-amber-800">
          Preview only: not configured yet, missing {report.missing.join(", ")}.
        </p>
      )}
      {report.warnings.map((w) => <p key={w} className="border-b border-amber-100 bg-amber-50 px-4 py-2 text-[11px] text-amber-800">{w}</p>)}
      <ul className="max-h-72 divide-y divide-slate-100 overflow-auto text-xs">
        {report.rows.map((r: PushRow) => (
          <li key={r.id} className="px-4 py-2">
            <div className="flex items-center gap-2">
              <span className={`w-16 shrink-0 rounded px-1.5 py-0.5 text-center text-[10px] font-bold ${ACTION_CLS[r.action] ?? ""}`}>{r.action}</span>
              <span className="w-14 shrink-0 text-[10px] uppercase text-slate-400">{r.level}</span>
              <span className="shrink-0 font-mono text-[11px] text-slate-500">{r.id}</span>
              <span className="min-w-0 flex-1 truncate text-slate-800">{r.title}</span>
              {r.url ? (
                <a href={r.url} target="_blank" rel="noreferrer" className="shrink-0 font-mono text-[11px] text-blue-600 hover:underline">{r.key ?? "open"}</a>
              ) : r.payload ? (
                <button type="button" onClick={() => setOpen(open === r.id ? null : r.id)} className="shrink-0 text-[10px] font-semibold text-slate-500 hover:text-slate-800">
                  {open === r.id ? "hide payload" : "payload"}
                </button>
              ) : null}
            </div>
            {(r.note || r.error) && <p className={`mt-0.5 pl-[8.5rem] text-[11px] ${r.error ? "text-red-700" : "text-slate-500"}`}>{r.error ?? r.note}</p>}
            {open === r.id && r.payload && (
              <pre className="mt-2 max-h-56 overflow-auto rounded bg-slate-900 p-3 font-mono text-[10px] text-emerald-300">
                {r.payload.method} {r.payload.url}
                {"\n"}
                {JSON.stringify(r.payload.body, null, 2)}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
