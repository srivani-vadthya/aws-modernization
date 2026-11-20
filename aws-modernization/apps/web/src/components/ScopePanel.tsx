import { useEffect, useMemo, useState } from "react";
import { api, type Engagement, type ScopeModule, type ScopeModules } from "../api";

// Risk badge (low/medium/high) on the module cards is temporarily disabled (not deleted); re-enable with the badge below.
// const RISK_CLS: Record<string, string> = {
//   critical: "bg-red-100 text-red-700 border-red-200",
//   high: "bg-amber-100 text-amber-800 border-amber-200",
//   medium: "bg-yellow-50 text-yellow-700 border-yellow-200",
//   low: "bg-emerald-50 text-emerald-700 border-emerald-200",
// };

const KIND_CLS: Record<string, string> = {
  code: "bg-blue-50 text-blue-700 border-blue-200",
  "data model": "bg-emerald-50 text-emerald-700 border-emerald-200",
  view: "bg-violet-50 text-violet-700 border-violet-200",
  frontend: "bg-sky-50 text-sky-700 border-sky-200",
  config: "bg-slate-100 text-slate-600 border-slate-200",
};

function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      {label}
    </div>
  );
}

export function ScopePanel({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const [data, setData] = useState<ScopeModules | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(e.scope?.capabilityId ?? null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [redescribing, setRedescribing] = useState(false);
  const scopeApproved = e.gates['scope']?.decision === 'approved';

  useEffect(() => {
    let live = true;
    setLoadError(null);
    api
      .scopeModules(e.id, false)
      .then((d) => live && setData(d))
      .catch((err: Error) => live && setLoadError(err.message));
    return () => {
      live = false;
    };
  }, [e.id, reload]);

  const selected = useMemo(() => data?.modules.find((m) => m.id === selectedId) ?? null, [data, selectedId]);

  async function pick(m: ScopeModule) {
    if (scopeApproved) return;
    if (saving || m.id === e.scope?.capabilityId) {
      setSelectedId(m.id);
      return;
    }
    setSelectedId(m.id); // files appear immediately; persisting the scope may take a moment
    setSaving(true);
    setSaveError(null);
    try {
      onChange(await api.scope(e.id, m.id));
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
      setSelectedId(e.scope?.capabilityId ?? null);
    } finally {
      setSaving(false);
    }
  }

  async function redescribe() {
    setRedescribing(true);
    try {
      setData(await api.scopeModules(e.id, true));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setRedescribing(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-blue-200 bg-blue-50/60 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-blue-950">Select the business module to modernize</h3>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-blue-900">
              Modules, use cases and files below are derived from the Applied Knowledge Graph and the parsed AST of this
              source. Nothing is hardcoded and no demo scopes are substituted.
            </p>
          </div>
          {data && (
            <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold">
              <span
                className={`rounded-full border px-2.5 py-1 ${
                  data.enrichment.status === "llm"
                    ? "border-violet-200 bg-violet-50 text-violet-700"
                    : "border-slate-200 bg-white text-slate-600"
                }`}
                title={data.enrichment.note}
              >
                {data.enrichment.status === "llm" ? `Business wording by LLM · ${data.enrichment.model}` : "Graph-derived wording"}
              </span>
              <button
                type="button"
                disabled={redescribing || scopeApproved}
                onClick={() => void redescribe()}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {redescribing ? "Describing…" : "Re-describe with LLM"}
              </button>
            </div>
          )}
        </div>
        {loadError && (
          <p role="alert" className="mt-2 text-xs text-red-700">
            Scope evidence could not be loaded: {loadError}{" "}
            <button type="button" className="font-semibold underline" onClick={() => setReload((n) => n + 1)}>
              Retry
            </button>
          </p>
        )}
        {saveError && (
          <p role="alert" className="mt-2 text-xs text-red-700">
            Scope selection failed: {saveError}
          </p>
        )}
      </section>

      {!data && !loadError && <Spinner label="Analysing the knowledge graph and AST for business modules…" />}

      {data && data.modules.length === 0 && (
        <p className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600">
          No module has operational AST/AKG evidence (calls, reads, writes, entities). Re-run discovery with a source tree
          the parsers support; no demo scopes are substituted.
        </p>
      )}

      {data && data.modules.length > 0 && (
        <section aria-label="Business modules">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              {data.summary.modules} modules · {data.summary.useCases} use cases · {data.summary.files} files
            </h4>
            {saving && <span className="text-xs font-medium text-blue-700">Saving scope…</span>}
            {scopeApproved && (
              <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-bold text-emerald-700">
                🔒 Scope locked — approved
              </span>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" role="radiogroup" aria-label="Business modules">
            {data.modules.map((m) => (
              <ModuleCard key={m.id} m={m} active={m.id === selectedId} disabled={saving || scopeApproved} onPick={() => void pick(m)} />
            ))}
          </div>
        </section>
      )}

      {selected && <ModuleDetail m={selected} sharedServices={e.scope?.capabilityId === selected.id ? e.scope.sharedServices : undefined} />}
    </div>
  );
}

function ModuleCard({ m, active, disabled, onPick }: { m: ScopeModule; active: boolean; disabled: boolean; onPick: () => void }) {
  const title = m.displayName ?? m.name;
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      disabled={disabled}
      onClick={onPick}
      className={`flex flex-col rounded-xl border-2 p-4 text-left transition disabled:cursor-wait disabled:opacity-70 ${
        active
          ? "border-blue-500 bg-blue-50 shadow-md ring-2 ring-blue-400/20"
          : "border-slate-200 bg-white hover:border-blue-300 hover:bg-blue-50/30"
      } ${m.shared ? "border-dashed" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {m.modernization && (
            <span title={`Suggested modernization order: ${m.modernization.reason}`}
                  className="mb-1 inline-block rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[9px] font-bold text-white">
              #{m.modernization.rank}
            </span>
          )}
          <span className={`block truncate text-sm font-bold ${active ? "text-blue-900" : "text-slate-900"}`}>{title}</span>
          {m.displayName && m.displayName !== m.name && (
            <span className="font-mono text-[10px] text-slate-400">{m.name}</span>
          )}
        </div>
        {/* <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase ${RISK_CLS[m.risk] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
          {m.risk}
        </span> */}
      </div>

      <p className="mt-2 text-xs leading-relaxed text-slate-600">{m.businessSummary ?? m.summary}</p>

      <div className="mt-3 flex flex-wrap gap-1.5 font-mono text-[10px]">
        <span className="rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-blue-700">{m.metrics.useCases} use cases</span>
        <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-slate-700">{m.metrics.files} files</span>
        {m.metrics.tables > 0 && (
          <span className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-emerald-700">{m.metrics.tables} entities</span>
        )}
        {m.sharedKernels.length > 0 && (
          <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-amber-700">⇄ {m.sharedKernels.length} shared</span>
        )}
        {m.shared && <span className="rounded border border-slate-300 bg-slate-100 px-1.5 py-0.5 text-slate-600">platform code</span>}
      </div>

      {m.useCases.length > 0 && (
        <ul className="mt-3 space-y-0.5 border-t border-slate-100 pt-2 text-[11px] text-slate-600">
          {m.useCases.slice(0, 3).map((u) => (
            <li key={u.id} className="flex items-center gap-1.5 truncate">
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${u.mutates ? "bg-amber-500" : "bg-sky-400"}`} />
              <span className="truncate">{u.name}</span>
            </li>
          ))}
          {m.useCases.length > 3 && <li className="text-[10px] text-slate-400">+{m.useCases.length - 3} more</li>}
        </ul>
      )}
      {active && <p className="mt-2 text-right text-[10px] font-bold text-blue-700">✓ Selected scope</p>}
    </button>
  );
}

function ModuleDetail({ m, sharedServices }: { m: ScopeModule; sharedServices?: { resourceId: string; kind: string; resourceName?: string; consumers: string[]; recommendedStrategy?: string }[] }) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<string>("all");
  const kinds = useMemo(() => Array.from(new Set(m.files.map((f) => f.kind))).sort(), [m.files]);
  const files = useMemo(() => {
    const q = query.trim().toLowerCase();
    return m.files.filter(
      (f) => (kind === "all" || f.kind === kind) && (!q || f.path.toLowerCase().includes(q) || f.symbols.some((s) => s.toLowerCase().includes(q))),
    );
  }, [m.files, query, kind]);

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Business use cases in {m.displayName ?? m.name}</h3>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Entry points traced through the AST call chain to the data they read and write.
              {m.boundary && <> Suggested boundary: <strong>{m.boundary}</strong>.</>}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-[10px] font-semibold">
            {m.dependsOn.length > 0 && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">Depends on: {m.dependsOn.join(", ")}</span>}
            {m.ownedTables.length > 0 && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-700">Owns: {m.ownedTables.join(", ")}</span>}
          </div>
        </div>
        {m.useCases.length === 0 ? (
          <p className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
            No entry-point flows were traced for this module; the Semantic IR will be derived from its entity and call relationships instead.
          </p>
        ) : (
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {m.useCases.map((u) => (
              <article key={u.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-start justify-between gap-2">
                  <h5 className="text-xs font-semibold text-slate-900">{u.name}</h5>
                  <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${u.mutates ? "bg-amber-100 text-amber-800" : "bg-sky-100 text-sky-800"}`}>
                    {u.mutates ? "Mutates data" : "Read only"}
                  </span>
                </div>
                {u.description && <p className="mt-1 text-[11px] text-slate-600">{u.description}</p>}
                <p className="mt-1 break-all font-mono text-[10px] text-slate-500">{u.entry}</p>
                <p className="mt-1 text-[10px] text-slate-500">
                  Reads: {u.reads.join(", ") || "none"} · Writes: {u.writes.join(", ") || "none"}
                  {u.externals.length > 0 && <> · External: {u.externals.join(", ")}</>}
                </p>
              </article>
            ))}
          </div>
        )}
      </section>

      {sharedServices && sharedServices.length > 0 && (
        <section className="rounded-xl border border-amber-200 bg-amber-50/60 p-4">
          <h4 className="text-xs font-bold uppercase tracking-wider text-amber-900">Assets other modules depend on</h4>
          <ul className="mt-2 space-y-1.5 text-xs text-amber-900">
            {sharedServices.map((s) => (
              <li key={s.resourceId}>
                <strong>{s.resourceName ?? s.resourceId}</strong> ({s.kind}) is used by {s.consumers.join("; ")}.
                {s.recommendedStrategy && <span className="text-amber-800"> {s.recommendedStrategy}.</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-xl border border-slate-200 bg-white shadow-xs" aria-label="Related files">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Related files</h3>
            <p className="text-[11px] text-slate-500">
              {files.length} of {m.files.length} files · {m.metrics.loc.toLocaleString()} lines in {m.displayName ?? m.name}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="search"
              value={query}
              onChange={(ev) => setQuery(ev.target.value)}
              placeholder="Filter by path or symbol"
              aria-label="Filter files"
              className="w-52 rounded-lg border border-slate-300 bg-slate-50 px-3 py-1.5 text-xs focus:border-blue-500 focus:bg-white focus:outline-none"
            />
            {["all", ...kinds].map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold capitalize ${
                  kind === k ? "border-blue-500 bg-blue-600 text-white" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {k}
              </button>
            ))}
          </div>
        </div>
        {files.length === 0 ? (
          <p className="p-5 text-xs text-slate-500">No files match the filter.</p>
        ) : (
          <div className="max-h-[28rem] overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-5 py-2 font-semibold">File</th>
                  <th className="px-3 py-2 font-semibold">Kind</th>
                  <th className="px-3 py-2 font-semibold">Symbols</th>
                  <th className="px-3 py-2 text-right font-semibold">LOC</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {files.map((f) => (
                  <tr key={f.path} className="hover:bg-slate-50">
                    <td className="px-5 py-2 align-top">
                      <span className="break-all font-mono text-[11px] text-slate-800">{f.path}</span>
                      <div className="mt-0.5 flex gap-1.5">
                        {f.inUseCase && <span className="rounded bg-blue-50 px-1.5 text-[9px] font-semibold text-blue-700">in a use case</span>}
                        {f.shared && <span className="rounded bg-amber-50 px-1.5 text-[9px] font-semibold text-amber-700">shared</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${KIND_CLS[f.kind] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>{f.kind}</span>
                      <div className="mt-0.5 text-[10px] text-slate-400">{f.language}</div>
                    </td>
                    <td className="max-w-xs px-3 py-2 align-top text-[11px] text-slate-600">{f.symbols.slice(0, 4).join(", ")}{f.symbols.length > 4 ? ` +${f.symbols.length - 4}` : ""}</td>
                    <td className="px-3 py-2 text-right align-top font-mono text-[11px] text-slate-600">{f.loc || "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
