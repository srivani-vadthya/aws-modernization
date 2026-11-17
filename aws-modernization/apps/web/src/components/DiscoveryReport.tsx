import { useEffect, useState, type ReactNode } from "react";
import { AppliedKnowledgeGraph } from "./AppliedKnowledgeGraph";

type Evidence = { id: string; path: string; line: number; kind: string; value: string };
type Finding = { title: string; status: string; evidenceIds: string[] };
type Comment = { id: string; section: string; text: string; at: string };
type Report = {
  generatedAt: string; sourceDigest: string; engine: string;
  summary: { files: number; loc: number; locFiles: number; vendorFiles: number; projects: number; coverage: null;
    applicationFiles: number; applicationLoc: number; proposedModules: number; technicalGroups: number;
    integrationGroups: number; integrationReferences: number; breakdown: Record<string, { files: number; loc: number }> };
  languages: Record<string, number>;
  applicationLanguages: Record<string, number>;
  analysisCoverage: { unsupportedLanguages: string[]; ast: string };
  projects: { path: string; framework: string; evidenceIds: string[] }[];
  dependencies: { name: string; version: string; ecosystem: string; status: string; license: string; evidenceIds: string[] }[];
  modules: { id: string; name: string; type: string; description: string; files: string[]; loc: number; complexity: string; dependsOn: string; evidenceIds: string[] }[];
  references: { source: string; target: string; kind: string; evidenceIds: string[] }[];
  integrations: { name: string; path: string; direction: string; implementation: string; status: string; evidenceIds: string[] }[];
  integrationGroups: { id: string; name: string; project: string; paths: string[]; referenceCount: number; status: string; groupingBasis: string; evidenceIds: string[] }[];
  declarations: { name: string; kind: string; evidenceIds: string[] }[];
  findings: Finding[]; evidence: Evidence[]; limits: string[]; skipped: string[];
  ai: { status: string; model?: string; message?: string; evidenceSampleSize?: number; totalEvidence?: number; interpretations: Finding[] };
  telemetry: { at: string; provider: string; model: string; status: string; inputTokens: number | null; outputTokens: number | null; durationMs: number; costUsd: null }[];
  comments: Comment[];
};
const tabs = [
  ["overview", "Overview"], ["modules", "Modules"], ["dependencies", "Dependencies"],
  ["integrations", "Integrations"], ["findings", "Findings"], ["akg", "Knowledge Graph"], ["telemetry", "AIOps Telemetry"],
] as const;
type Tab = typeof tabs[number][0];
const button = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50";

async function request<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

// Share pending work across React StrictMode mounts; the API also deduplicates by snapshot.
const pending = new Map<string, Promise<Report>>();
function loadDiscovery(url: string, retry = false): Promise<Report> {
  const existing = pending.get(url);
  if (existing) return existing;
  const work = (async () => {
    let result = await request<Report>(url, { useBedrock: true, onlyIfNeeded: !retry });
    for (let i = 0; result.ai.status === "Running" && i < 45; i++) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      result = await request<Report>(url);
    }
    return result;
  })().finally(() => pending.delete(url));
  pending.set(url, work);
  return work;
}

function Table({ headers, rows, empty = "No matching source evidence found. This does not prove absence." }: { headers: string[]; rows: ReactNode[][]; empty?: string }) {
  return <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
    <table className="w-full text-left text-xs">
      <thead className="bg-slate-100 text-slate-600"><tr>{headers.map(h => <th key={h} className="px-4 py-3 font-semibold">{h}</th>)}</tr></thead>
      <tbody>{rows.map((row, i) => <tr key={i} className="border-t border-slate-100 align-top">{row.map((cell, j) => <td key={j} className="px-4 py-3">{cell}</td>)}</tr>)}</tbody>
    </table>
    {!rows.length && <p className="p-5 text-sm text-slate-500">{empty}</p>}
  </div>;
}

export function DiscoveryReport({ engagementId }: { engagementId: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const endpoint = `/api/engagements/${engagementId}/discovery-report`;
  useEffect(() => {
    let alive = true;
    setBusy(true);
    loadDiscovery(endpoint).then(r => { if (alive) setReport(r); }).catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [endpoint]);

  async function run() {
    setBusy(true); setError(null);
    try { setReport(await loadDiscovery(endpoint, report?.ai.status === "Unavailable")); }
    catch (e) { setError(e instanceof Error ? e.message : "Discovery failed. Please retry."); }
    finally { setBusy(false); }
  }
  function evidence(ids: string[]) {
    const rows = ids.map(id => report?.evidence.find(e => e.id === id)).filter((e): e is Evidence => !!e);
    return <details className="min-w-36 text-slate-600"><summary className="cursor-pointer text-blue-700">{rows.length} source reference{rows.length === 1 ? "" : "s"}</summary>
      <ul className="mt-2 max-h-64 space-y-2 overflow-auto">{rows.map(e => <li key={e.id} className="break-all"><span className="font-mono">{e.path}:{e.line}</span><br />{e.kind}: {e.value}</li>)}</ul>
    </details>;
  }
  const matches = (value: string) => value.toLowerCase().includes(query.toLowerCase());
  const findings = report ? [...report.findings, ...report.ai.interpretations] : [];
  const counts: Partial<Record<Tab, number>> = report ? { modules: report.summary.proposedModules, dependencies: report.dependencies.length, integrations: report.integrationGroups.length, findings: findings.length, telemetry: report.telemetry.length } : {};
  const moduleRows = (kind: string) => report?.modules.filter(m => m.type === kind && matches(m.name)).map(m => [<div className="min-w-48"><strong>{m.name}</strong><p className="mt-1 text-slate-500">{m.description}</p></div>, m.files.length, m.loc.toLocaleString(), m.complexity, m.dependsOn, evidence(m.evidenceIds)]) || [];

  return <div className="space-y-5">
    <div className="flex flex-wrap gap-1 border-b border-slate-200" role="tablist" aria-label="Discovery views">
      {tabs.map(([id, label]) => <button key={id} id={`tab-${id}`} role="tab" aria-selected={tab === id} aria-controls="discovery-panel" onClick={() => { setTab(id); setQuery(""); }}
        className={`border-b-2 px-4 py-3 text-sm ${tab === id ? "border-blue-600 font-semibold text-blue-700" : "border-transparent text-slate-500 hover:text-slate-900"}`}>
        {label}{counts[id] !== undefined && <span className="ml-2 text-xs text-slate-400">{counts[id]}</span>}
      </button>)}
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="text-sm font-semibold text-slate-800">Source evidence first</p><p className="text-xs text-slate-500">Bedrock reviews new source snapshots automatically; saved results are reused.</p></div>
      <button disabled={busy} className={button} onClick={() => void run()}>{busy ? "Preparing discovery…" : "Refresh discovery"}</button>
    </div>
    {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {!report && !error && <p role="status" className="p-8 text-sm text-slate-500">Inspecting source and preparing the saved review…</p>}
    {report && <>
      <div role="tabpanel" id="discovery-panel" aria-labelledby={`tab-${tab}`} className="space-y-4">
        {tab !== "overview" && tab !== "telemetry" && <input aria-label="Search discovery" placeholder="Search this view…" className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm" value={query} onChange={e => setQuery(e.target.value)} />}
        {tab === "overview" && <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[
            ["Application source files", report.summary.applicationFiles.toLocaleString()], ["Application lines", report.summary.applicationLoc.toLocaleString()],
            ["Proposed business modules", report.summary.proposedModules], ["Integration reference groups", report.summary.integrationGroups],
          ].map(([label, value]) => <div key={label} className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-xl font-semibold text-slate-900">{value}</p></div>)}</div>
          <details className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600"><summary className="cursor-pointer">Counting details · {report.summary.files.toLocaleString()} total scanned files · {report.summary.technicalGroups} technical groups · {report.summary.integrationReferences} integration references</summary>
            <p className="my-3">Application ownership is provisional. Vendor and generated files require banner/source-map evidence; uncertain library paths remain unclassified. Lines include comments and blanks. No totals are discarded.</p>
            <Table headers={["Classification", "Files", "Physical lines"]} rows={Object.entries(report.summary.breakdown).map(([name, count]) => [name, count.files.toLocaleString(), count.loc.toLocaleString()])} />
          </details>
          <div className="grid gap-4 xl:grid-cols-2">
            <section className="space-y-5 rounded-xl border border-slate-200 bg-white p-5">
              <div><h3 className="font-semibold">Application languages</h3><p className="mt-1 text-xs text-slate-500">Source files by extension, excluding identified vendor/generated files and unclassified library candidates.</p>
                <div className="mt-3 flex flex-wrap gap-2">{Object.entries(report.applicationLanguages).sort((a,b) => b[1]-a[1]).map(([name,count]) => <span key={name} className="rounded bg-blue-50 px-2 py-1 text-xs text-blue-800">{name} · {count} files</span>)}</div></div>
              <div><h3 className="font-semibold">Build and framework declarations</h3>{report.projects.map(p => <div key={p.path} className="mt-3 text-xs"><p className="font-medium">{p.path} · {p.framework}</p>{evidence(p.evidenceIds)}</div>)}{!report.projects.length && <p className="text-sm text-slate-500">No .NET project declarations found.</p>}</div>
              <p className="text-xs text-slate-500">Lines measured across {report.summary.locFiles} recognized text files. Blank and comment lines are included.</p>
            </section>
            <section className="rounded-xl border border-slate-200 bg-white p-5"><h3 className="font-semibold">Analysis status</h3>
              <p className="mt-3 text-xs text-slate-600">Source facts are measured; modules and AI interpretations need review. Coverage, runtime behavior and a full AST are not verified.</p>
              <p className="mt-4 text-xs">Bedrock: {report.ai.status}{report.ai.model ? ` · ${report.ai.model}` : ""}</p><p className="mt-1 text-xs">{report.ai.message}</p>
              {report.ai.evidenceSampleSize !== undefined && <p className="mt-1 text-xs">AI reviewed {report.ai.evidenceSampleSize} of {report.ai.totalEvidence} evidence records; this is a bounded review, not full-repository semantic analysis.</p>}
              <p className="mt-3 text-xs">{report.skipped.length} unreadable, oversized, linked, or invalid files reported.</p>
              {!!report.skipped.length && <details className="mt-2 text-xs"><summary className="cursor-pointer">Inspect skipped files</summary><ul className="mt-2 max-h-40 overflow-auto">{report.skipped.map(p => <li key={p} className="break-all">{p}</li>)}</ul></details>}
              <details className="mt-3 text-xs text-slate-500"><summary className="cursor-pointer">Analysis coverage and limitations</summary><ul className="mt-2 list-disc space-y-1 pl-4">{report.limits.map(l => <li key={l}>{l}</li>)}</ul><p className="mt-2">No language-specific declaration analysis for: {report.analysisCoverage.unsupportedLanguages.join(", ") || "none of the recognized application languages listed"}. Even supported-language matches are partial lexical leads.</p></details>
            </section>
          </div>
          <h3 className="font-semibold">Observed framework findings</h3>
          <Table headers={["Finding", "Basis", "Evidence"]} rows={report.findings.map(f => [f.title, f.status, evidence(f.evidenceIds)])} />
        </>}
        {tab === "modules" && <>
          <p className="text-xs text-slate-500">Business boundaries remain suggestions. Approval saves this source snapshot for graph and future scope selection; existing selected scope is preserved.</p>
          <Table headers={["Proposed module", "Files", "LOC", "Complexity", "Depends on", "Evidence"]} rows={moduleRows("Inferred grouping")} empty="No business modules inferred. Review the technical groups below; no business boundaries have been invented." />
          <details className="rounded-xl border border-slate-200 bg-white p-4"><summary className="cursor-pointer text-sm font-semibold">Technical groups ({report.summary.technicalGroups})</summary><div className="mt-3"><Table headers={["Project / folder", "Files", "LOC", "Complexity", "Depends on", "Evidence"]} rows={moduleRows("Technical folder")} /></div></details>
          <h3 className="font-semibold">Declared project dependencies</h3><Table headers={["Project", "Reference", "Evidence"]} rows={report.references.map(r => [r.source, r.target, evidence(r.evidenceIds)])} />
          <details className="rounded-xl border border-slate-200 bg-white p-4"><summary className="cursor-pointer text-sm font-semibold">Source declarations ({report.declarations.length} lexical matches)</summary><div className="mt-3"><Table headers={["Declaration", "Kind", "Evidence"]} rows={report.declarations.filter(d => matches(d.name)).map(d => [d.name, d.kind, evidence(d.evidenceIds)])} /></div></details>
        </>}
        {tab === "dependencies" && <><p className="text-xs text-slate-500">Declared versions only. Security, license and lifecycle checks have not been performed.</p><Table headers={["Library", "Version", "Ecosystem", "License", "Security / EOL", "Evidence"]} rows={report.dependencies.filter(d => matches(d.name)).map(d => [<strong>{d.name}</strong>, d.version, d.ecosystem, d.license, d.status, evidence(d.evidenceIds)])} /></>}
        {tab === "integrations" && <><p className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600">Repeated matches are grouped by API family and owning project. These groups are not verified external systems; expand evidence to see every reference.</p><Table headers={["Reference group", "Project", "References", "Files", "Basis", "Evidence"]} rows={report.integrationGroups.filter(i => matches(i.name + i.project)).map(i => [i.name, i.project, i.referenceCount, i.paths.length, i.groupingBasis, evidence(i.evidenceIds)])} /></>}
        {tab === "findings" && <><p className="text-xs text-slate-500">AI findings cite known evidence IDs, but their interpretation still requires human review. Source comments are inputs, not verified facts.</p><Table headers={["Finding", "Basis", "Evidence"]} rows={findings.filter(f => matches(f.title)).map(f => [f.title, <span className={f.status === "Observed" ? "text-emerald-700" : "text-amber-800"}>{f.status}</span>, evidence(f.evidenceIds)])} /></>}
        {tab === "akg" && <AppliedKnowledgeGraph engagementId={engagementId} />}
        {tab === "telemetry" && <>
          <p className="text-xs text-slate-500">Only review attempts made by this discovery feature are recorded here. Tokens are returned by Bedrock; duration is measured locally. Cost is unavailable without verified pricing. Historical demo telemetry is excluded.</p>
          <Table headers={["Time", "Provider / model", "Result", "Input tokens", "Output tokens", "Duration", "Cost"]} rows={report.telemetry.map(t => [new Date(t.at).toLocaleString(), `${t.provider} / ${t.model}`, t.status, t.inputTokens ?? "Unavailable", t.outputTokens ?? "Unavailable", `${(t.durationMs / 1000).toFixed(2)} s`, "Not calculated"])} empty="No Bedrock discovery calls recorded. Run a Bedrock review to collect actual usage." />
        </>}
      </div>
      <p className="break-all text-[11px] text-slate-400">Inspected {new Date(report.generatedAt).toLocaleString()} · Source fingerprint {report.sourceDigest.slice(0,16)} · Existing approval controls remain below.</p>
    </>}
  </div>;
}
