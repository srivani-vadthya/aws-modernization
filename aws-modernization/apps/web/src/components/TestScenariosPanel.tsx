import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Engagement,
  type TestCase,
  type TestCategory,
  type TestResultStatus,
  type TestRun,
  type TestScenariosState,
} from "../api";

type Tab = "scenarios" | "cases" | "scripts" | "data" | "coverage" | "results";

const TABS: { id: Tab; label: string }[] = [
  { id: "scenarios", label: "Test Scenarios" },
  { id: "cases", label: "Test Cases" },
  { id: "scripts", label: "Playwright Scripts" },
  { id: "data", label: "Test Data" },
  { id: "coverage", label: "Coverage Matrix" },
  { id: "results", label: "Results" },
];

const CATEGORY: Record<TestCategory, { label: string; chip: string }> = {
  positive: { label: "Positive", chip: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  negative: { label: "Negative", chip: "border-red-200 bg-red-50 text-red-700" },
  validation: { label: "Validation", chip: "border-amber-200 bg-amber-50 text-amber-800" },
  edge: { label: "Edge case", chip: "border-violet-200 bg-violet-50 text-violet-700" },
  exception: { label: "Exception", chip: "border-slate-300 bg-slate-100 text-slate-700" },
};

const RESULT: Record<TestResultStatus, { label: string; chip: string }> = {
  passed: { label: "Passed", chip: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  failed: { label: "Failed", chip: "border-red-200 bg-red-50 text-red-700" },
  skipped: { label: "Skipped", chip: "border-slate-300 bg-slate-100 text-slate-600" },
  "not-run": { label: "Not run", chip: "border-slate-200 bg-white text-slate-500" },
};

const BTN = "rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50";
const BTN_PRIMARY = "rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50";

function download(name: string, text: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const csvCell = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
const toCsv = (rows: unknown[][]) => rows.map((r) => r.map(csvCell).join(",")).join("\n");

function Chip({ className, children }: { className: string; children: React.ReactNode }) {
  return <span className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${className}`}>{children}</span>;
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className={BTN}
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1800);
        });
      }}
    >
      {done ? "Copied!" : label}
    </button>
  );
}

export function TestScenariosPanel({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const ts: TestScenariosState | null = e.testScenarios ?? null;
  const hasStories = (e.userStories?.counts.stories ?? 0) > 0;
  const [tab, setTab] = useState<Tab>("scenarios");
  const [busy, setBusy] = useState<"generate" | "run" | "live" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const attempted = useRef<string | null>(null);

  async function refresh() {
    onChange(await api.get(e.id));
  }

  async function generate() {
    setBusy("generate");
    setError(null);
    try {
      const r = await api.generateTestScenarios(e.id);
      setStale(r.stale);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function run(live: boolean) {
    setBusy(live ? "live" : "run");
    setError(null);
    try {
      await api.runTestScenarios(e.id, live ? { baseUrl: baseUrl.trim() } : {});
      await refresh();
      setTab("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  // First visit with approved stories: build the QA assets right away. Otherwise just check whether they are out of date.
  useEffect(() => {
    if (!hasStories || attempted.current === e.id) return;
    attempted.current = e.id;
    if (!ts) void generate();
    else void api.testScenarios(e.id).then((r) => setStale(r.stale)).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e.id, hasStories]);

  if (!hasStories) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center text-sm text-amber-800">
        Test scenarios are generated from the user stories and their acceptance criteria. Generate the user stories first.
      </div>
    );
  }

  if (!ts) {
    return error ? (
      <div className="space-y-3 rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">
        <p role="alert">Test scenario generation failed: {error}</p>
        <button type="button" onClick={() => void generate()} className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold">
          Try again
        </button>
      </div>
    ) : (
      <div className="flex items-center gap-3 rounded-xl border border-blue-200 bg-blue-50/60 p-6 text-sm text-blue-900">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
        <div>
          <p className="font-semibold">Building test scenarios from the acceptance criteria…</p>
          <p className="mt-0.5 text-xs text-blue-800">Scenarios, detailed test cases, Playwright scripts, test data and coverage.</p>
        </div>
      </div>
    );
  }

  const latest = ts.runs[0] ?? null;
  const statusOf = new Map(latest?.results.map((r) => [r.caseId, r.status] as const) ?? []);
  const c = ts.counts;
  const pct = c.criteria ? Math.round((c.criteriaCovered / c.criteria) * 100) : 0;

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 to-slate-50 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-xs font-bold text-white shadow-sm">TS</span>
            <div>
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900">QA assets from the user stories</h3>
              <p className="mt-0.5 max-w-2xl text-xs text-slate-500">
                Built from the acceptance criteria of the generated user stories, nothing else: every criterion becomes a test scenario
                with a detailed test case and a Playwright script. They are rebuilt and re-checked whenever the stories are generated or edited.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={BTN} disabled={busy !== null} onClick={() => void generate()}>
              {busy === "generate" ? "Regenerating…" : "Regenerate"}
            </button>
            <a href={api.testScenariosExportUrl(e.id, "md")} className={BTN}>Markdown</a>
            <a href={api.testScenariosExportUrl(e.id, "zip")} className={BTN}>Download all (.zip)</a>
            <button type="button" className={BTN_PRIMARY} disabled={busy !== null} onClick={() => void run(false)}>
              {busy === "run" ? "Running…" : "Run tests again"}
            </button>
          </div>
        </div>

        {stale && (
          <p role="status" className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            The user stories or acceptance criteria changed after these tests were generated.{" "}
            <button type="button" onClick={() => void generate()} className="font-bold underline">Regenerate now</button>
          </p>
        )}
        {error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}

        <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
          {(
            [
              ["Scenarios", c.scenarios],
              ["Test cases", c.cases],
              ...(Object.keys(CATEGORY) as TestCategory[]).map((k) => [CATEGORY[k].label, c.byCategory[k]] as [string, number]),
              ["Criteria covered", `${pct}%`],
            ] as [string, number | string][]
          ).map(([label, value]) => (
            <div key={label} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</dt>
              <dd className="text-lg font-bold text-slate-900">{value}</dd>
            </div>
          ))}
        </dl>

        {latest ? <RunSummary run={latest} onOpen={() => setTab("results")} /> : (
          <p className="mt-3 text-[11px] text-slate-500">Not run yet. Press “Run tests again” to check every test case.</p>
        )}
      </section>

      <div role="tablist" aria-label="Test assets" className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px rounded-t-lg border border-b-0 px-3.5 py-2 text-xs font-semibold transition ${
              tab === t.id ? "border-slate-200 bg-white text-blue-700" : "border-transparent text-slate-500 hover:text-slate-900"
            }`}
          >
            {t.label}
            {t.id === "scenarios" && <span className="ml-1.5 text-[10px] text-slate-400">{c.scenarios}</span>}
            {t.id === "cases" && <span className="ml-1.5 text-[10px] text-slate-400">{c.cases}</span>}
          </button>
        ))}
      </div>

      {tab === "scenarios" && <ScenariosTab ts={ts} statusOf={statusOf} />}
      {tab === "cases" && <CasesTab ts={ts} statusOf={statusOf} />}
      {tab === "scripts" && <ScriptsTab ts={ts} />}
      {tab === "data" && <DataTab ts={ts} />}
      {tab === "coverage" && <CoverageTab ts={ts} />}
      {tab === "results" && (
        <ResultsTab
          ts={ts}
          baseUrl={baseUrl}
          setBaseUrl={setBaseUrl}
          busy={busy}
          onRun={() => void run(false)}
          onRunLive={() => void run(true)}
        />
      )}
    </div>
  );
}

function RunSummary({ run, onOpen }: { run: TestRun; onOpen: () => void }) {
  const s = run.summary;
  const bad = s.failed > 0;
  return (
    <div className={`mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border px-3 py-2 text-xs ${bad ? "border-red-200 bg-red-50 text-red-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
      <span className="font-bold">{run.id} · {run.mode === "live" ? "Live Playwright run" : "Script checks"}</span>
      <span>{s.passed} passed</span>
      <span>{s.failed} failed</span>
      {s.skipped > 0 && <span>{s.skipped} skipped</span>}
      {s["not-run"] > 0 && <span>{s["not-run"]} not run</span>}
      <span className="text-[11px] opacity-70">{new Date(run.at).toLocaleString()}</span>
      <button type="button" onClick={onOpen} className="ml-auto font-bold underline">View results</button>
    </div>
  );
}

function CategoryFilter({ value, onChange, counts }: { value: TestCategory | "all"; onChange: (v: TestCategory | "all") => void; counts: Record<string, number> }) {
  const all = Object.values(counts).reduce((a, b) => a + b, 0);
  const opts: (TestCategory | "all")[] = ["all", "positive", "negative", "validation", "edge", "exception"];
  return (
    <div className="flex flex-wrap gap-1.5">
      {opts.map((o) => (
        <button
          key={o}
          type="button"
          onClick={() => onChange(o)}
          className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
            value === o ? "border-blue-300 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          }`}
        >
          {o === "all" ? "All" : CATEGORY[o].label} <span className="text-slate-400">{o === "all" ? all : counts[o] ?? 0}</span>
        </button>
      ))}
    </div>
  );
}

function ResultChip({ status }: { status: TestResultStatus | undefined }) {
  if (!status) return null;
  return <Chip className={RESULT[status].chip}>{RESULT[status].label}</Chip>;
}

function Toolbar({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center justify-between gap-2">{children}</div>;
}

// --------------------------------------------------------------------------- Test Scenarios

function ScenariosTab({ ts, statusOf }: { ts: TestScenariosState; statusOf: Map<string, TestResultStatus> }) {
  const [cat, setCat] = useState<TestCategory | "all">("all");
  const rows = ts.scenarios.filter((s) => cat === "all" || s.category === cat);
  const stories = useMemo(() => [...new Set(rows.map((s) => s.storyId))], [rows]);
  const csv = () =>
    toCsv([
      ["ID", "Story", "Category", "Scenario", "Origin", "Rules", "Test cases"],
      ...ts.scenarios.map((s) => [s.id, s.storyId, s.category, s.title, s.origin, s.ruleRefs.join(" "), s.caseIds.join(" ")]),
    ]);
  const text = ts.scenarios.map((s) => `${s.id} [${s.category}] ${s.title} (${s.storyId})`).join("\n");
  return (
    <div className="space-y-4">
      <Toolbar>
        <CategoryFilter value={cat} onChange={setCat} counts={ts.counts.byCategory} />
        <div className="flex gap-2">
          <CopyButton text={text} />
          <button type="button" className={BTN} onClick={() => download("test-scenarios.csv", csv(), "text/csv")}>Download CSV</button>
        </div>
      </Toolbar>
      {stories.map((sid) => {
        const list = rows.filter((s) => s.storyId === sid);
        return (
          <section key={sid} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
            <header className="border-b border-slate-100 bg-slate-50 px-4 py-2.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{list[0].feature} · {sid}</p>
              <h4 className="text-sm font-bold text-slate-900">{list[0].storyTitle}</h4>
            </header>
            <ul className="divide-y divide-slate-100">
              {list.map((s) => (
                <li key={s.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-4 py-2.5 text-xs">
                  <span className="w-14 shrink-0 font-mono text-[11px] font-bold text-slate-500">{s.id}</span>
                  <Chip className={CATEGORY[s.category].chip}>{CATEGORY[s.category].label}</Chip>
                  <span className="min-w-0 flex-1 text-slate-800">
                    {s.title}
                    {s.ruleRefs.length > 0 && <span className="ml-2 font-mono text-[10px] text-slate-400">{s.ruleRefs.join(", ")}</span>}
                  </span>
                  {s.needsReview && <Chip className="border-amber-200 bg-amber-50 text-amber-800">Needs review</Chip>}
                  <span className="font-mono text-[10px] text-slate-400">{s.caseIds.join(", ")}</span>
                  <ResultChip status={statusOf.get(s.caseIds[0])} />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      {rows.length === 0 && <p className="py-6 text-center text-xs text-slate-500">No scenarios in this category.</p>}
    </div>
  );
}

// --------------------------------------------------------------------------- Test Cases

function caseText(c: TestCase): string {
  const list = (items: string[], numbered = false) => items.map((x, i) => `  ${numbered ? `${i + 1}.` : "-"} ${x}`).join("\n");
  return [
    `${c.id} - ${c.name}`,
    `Category: ${c.category} | Story: ${c.storyId} | Priority: ${c.priority}`,
    `Description: ${c.description}`,
    "Preconditions:", list(c.preconditions),
    "Test steps:", list(c.steps, true),
    "Test data:", list(c.testData.map((d) => `${d.name}: ${d.value}`)) || "  - none",
    "Expected results:", list(c.expected),
  ].join("\n");
}

function CasesTab({ ts, statusOf }: { ts: TestScenariosState; statusOf: Map<string, TestResultStatus> }) {
  const [cat, setCat] = useState<TestCategory | "all">("all");
  const [open, setOpen] = useState<string | null>(null);
  const rows = ts.cases.filter((c) => cat === "all" || c.category === cat);
  return (
    <div className="space-y-3">
      <Toolbar>
        <CategoryFilter value={cat} onChange={setCat} counts={ts.counts.byCategory} />
        <div className="flex gap-2">
          <CopyButton text={rows.map(caseText).join("\n\n")} label="Copy all" />
          <button type="button" className={BTN} onClick={() => download("test-cases.txt", ts.cases.map(caseText).join("\n\n"))}>Download</button>
          <button
            type="button"
            className={BTN}
            onClick={() =>
              download(
                "test-cases.csv",
                toCsv([
                  ["ID", "Scenario", "Name", "Category", "Description", "Preconditions", "Steps", "Test data", "Expected results"],
                  ...ts.cases.map((c) => [
                    c.id, c.scenarioId, c.name, c.category, c.description, c.preconditions.join("\n"),
                    c.steps.map((s, i) => `${i + 1}. ${s}`).join("\n"), c.testData.map((d) => `${d.name}: ${d.value}`).join("\n"),
                    c.expected.join("\n"),
                  ]),
                ]),
                "text/csv",
              )
            }
          >
            CSV
          </button>
        </div>
      </Toolbar>
      {rows.map((c) => {
        const isOpen = open === c.id;
        return (
          <article key={c.id} className="rounded-xl border border-slate-200 bg-white shadow-xs">
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => setOpen(isOpen ? null : c.id)}
              className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-left"
            >
              <span className="font-mono text-[11px] font-bold text-slate-500">{c.id}</span>
              <Chip className={CATEGORY[c.category].chip}>{CATEGORY[c.category].label}</Chip>
              <span className="min-w-0 flex-1 text-sm font-semibold text-slate-900">{c.name}</span>
              {c.needsReview && <Chip className="border-amber-200 bg-amber-50 text-amber-800">Needs review</Chip>}
              <ResultChip status={statusOf.get(c.id)} />
              <span className="text-xs text-slate-400">{isOpen ? "▲" : "▼"}</span>
            </button>
            {isOpen && (
              <div className="space-y-4 border-t border-slate-100 px-4 py-4 text-xs text-slate-700">
                <p>{c.description}</p>
                <dl className="grid gap-4 md:grid-cols-2">
                  <Block title="Preconditions"><ul className="list-disc space-y-1 pl-4">{c.preconditions.map((p) => <li key={p}>{p}</li>)}</ul></Block>
                  <Block title="Test steps"><ol className="list-decimal space-y-1 pl-4">{c.steps.map((s) => <li key={s}>{s}</li>)}</ol></Block>
                  <Block title="Test data">
                    {c.testData.length ? (
                      <ul className="space-y-1">{c.testData.map((d) => <li key={d.name}><span className="text-slate-500">{d.name}:</span> <span className="font-mono text-[11px] text-slate-900">{d.value}</span></li>)}</ul>
                    ) : <p className="text-slate-400">No special data needed.</p>}
                  </Block>
                  <Block title="Expected results"><ul className="list-disc space-y-1 pl-4">{c.expected.map((x) => <li key={x}>{x}</li>)}</ul></Block>
                </dl>
                <div className="flex items-center justify-between border-t border-slate-100 pt-3 text-[11px] text-slate-500">
                  <span>Story {c.storyId} · scenario {c.scenarioId} · priority {c.priority}{c.ruleRefs.length ? ` · rules ${c.ruleRefs.join(", ")}` : ""}</span>
                  <CopyButton text={caseText(c)} label="Copy case" />
                </div>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">{title}</dt>
      <dd>{children}</dd>
    </div>
  );
}

// --------------------------------------------------------------------------- Playwright Scripts

function ScriptsTab({ ts }: { ts: TestScenariosState }) {
  const names = Object.keys(ts.files);
  const [file, setFile] = useState(names.find((n) => n.startsWith("specs/")) ?? names[0]);
  const content = ts.files[file] ?? "";
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
      <Toolbar>
        <p className="text-xs text-slate-500">
          Playwright + TypeScript: page object, shared test data, one spec per feature. Run with{" "}
          <span className="font-mono text-slate-700">npm install && npx playwright test</span>.
        </p>
        <div className="flex gap-2">
          <CopyButton text={content} label="Copy file" />
          <button type="button" className={BTN} onClick={() => download(file.split("/").pop() ?? file, content)}>Download file</button>
        </div>
      </Toolbar>
      <div className="mt-3 flex flex-wrap gap-1 border-b border-slate-200 pb-2">
        {names.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setFile(n)}
            className={`rounded px-2.5 py-1 font-mono text-xs transition ${file === n ? "bg-blue-100 font-semibold text-blue-700" : "text-slate-600 hover:bg-slate-100"}`}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="mt-3 max-h-[28rem] overflow-auto rounded-lg border border-slate-700 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-emerald-400 shadow-inner">
        <pre>{content}</pre>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------- Test Data

function DataTab({ ts }: { ts: TestScenariosState }) {
  const rows = ts.testData;
  const csv = () => toCsv([["ID", "Kind", "Name", "Value", "Source", "Used by"], ...rows.map((d) => [d.id, d.kind, d.name, d.value, d.source, d.usedBy.join(" ")])]);
  const toSupply = rows.filter((d) => d.source === "to be supplied").length;
  return (
    <div className="space-y-3">
      <Toolbar>
        <p className="text-xs text-slate-500">
          {rows.length} data requirements · <span className="font-semibold text-amber-700">{toSupply} to be supplied</span> before the tests can run
          (values in &lt;angle brackets&gt; are placeholders).
        </p>
        <div className="flex gap-2">
          <CopyButton text={rows.map((d) => `${d.id}\t${d.kind}\t${d.name}\t${d.value}`).join("\n")} />
          <button type="button" className={BTN} onClick={() => download("test-data.csv", csv(), "text/csv")}>Download CSV</button>
          <button type="button" className={BTN} onClick={() => download("test-data.json", JSON.stringify(rows, null, 2), "application/json")}>JSON</button>
        </div>
      </Toolbar>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-xs">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            <tr>{["ID", "Kind", "Name", "Value", "Source", "Used by"].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((d) => (
              <tr key={d.id} className="align-top">
                <td className="px-3 py-2 font-mono text-[11px] font-bold text-slate-500">{d.id}</td>
                <td className="px-3 py-2 capitalize">{d.kind}</td>
                <td className="px-3 py-2 text-slate-800">{d.name}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-slate-900">{d.value}</td>
                <td className="px-3 py-2">
                  <Chip className={d.source === "to be supplied" ? "border-amber-200 bg-amber-50 text-amber-800" : "border-emerald-200 bg-emerald-50 text-emerald-700"}>{d.source}</Chip>
                </td>
                <td className="px-3 py-2 font-mono text-[10px] text-slate-500">{d.usedBy.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- Coverage Matrix

function CoverageTab({ ts }: { ts: TestScenariosState }) {
  const cats = Object.keys(CATEGORY) as TestCategory[];
  const csv = () =>
    toCsv([
      ["Story", "Criterion", "Category", "Scenarios"],
      ...ts.coverage.flatMap((s) => s.criteria.map((c) => [s.storyId, c.text, c.category, c.scenarioIds.join(" ")])),
    ]);
  return (
    <div className="space-y-4">
      <Toolbar>
        <p className="text-xs text-slate-500">
          {ts.counts.criteriaCovered} of {ts.counts.criteria} acceptance criteria are covered by at least one scenario across {ts.counts.stories} user stories.
        </p>
        <div className="flex gap-2">
          <CopyButton text={csv()} label="Copy CSV" />
          <button type="button" className={BTN} onClick={() => download("coverage-matrix.csv", csv(), "text/csv")}>Download CSV</button>
        </div>
      </Toolbar>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-xs">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-3 py-2">User story</th>
              <th className="px-3 py-2">Criteria</th>
              {cats.map((k) => <th key={k} className="px-3 py-2 text-center">{CATEGORY[k].label}</th>)}
              <th className="px-3 py-2 text-center">Covered</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {ts.coverage.map((s) => (
              <tr key={s.storyId} className="align-top">
                <td className="px-3 py-2">
                  <p className="font-mono text-[10px] font-bold text-slate-400">{s.storyId}</p>
                  <p className="text-slate-800">{s.title}</p>
                </td>
                <td className="px-3 py-2 text-center font-bold text-slate-700">{s.criteria.length}</td>
                {cats.map((k) => (
                  <td key={k} className="px-3 py-2 text-center">{s.byCategory[k] ? <span className="font-bold text-slate-800">{s.byCategory[k]}</span> : <span className="text-slate-300">–</span>}</td>
                ))}
                <td className="px-3 py-2 text-center">
                  <Chip className={s.covered ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-red-200 bg-red-50 text-red-700"}>{s.covered ? "Yes" : "Gap"}</Chip>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details className="rounded-xl border border-slate-200 bg-white shadow-xs" open>
        <summary className="cursor-pointer px-4 py-3 text-xs font-bold uppercase tracking-wider text-slate-500">Criterion to scenario mapping</summary>
        <div className="overflow-x-auto border-t border-slate-100">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
              <tr><th className="px-3 py-2">Story</th><th className="px-3 py-2">Acceptance criterion</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Scenarios</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {ts.coverage.flatMap((s) =>
                s.criteria.map((c) => (
                  <tr key={`${s.storyId}-${c.index}`} className="align-top">
                    <td className="px-3 py-2 font-mono text-[11px] font-bold text-slate-500">{s.storyId}</td>
                    <td className="px-3 py-2 text-slate-800">{c.text}</td>
                    <td className="px-3 py-2"><Chip className={CATEGORY[c.category].chip}>{CATEGORY[c.category].label}</Chip></td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-600">{c.scenarioIds.join(", ")}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

// --------------------------------------------------------------------------- Results

const LIVE_NOTE: Record<TestRun["liveStatus"], string | null> = {
  "not-requested": null,
  completed: null,
  "setup-required": "The live run could not start.",
  unavailable: "The live run could not start.",
  failed: "The live run failed.",
};

function ResultsTab({
  ts, baseUrl, setBaseUrl, busy, onRun, onRunLive,
}: {
  ts: TestScenariosState; baseUrl: string; setBaseUrl: (v: string) => void; busy: string | null; onRun: () => void; onRunLive: () => void;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const [filter, setFilter] = useState<TestResultStatus | "all">("all");
  const run = ts.runs.find((r) => r.id === picked) ?? ts.runs[0] ?? null;
  const names = new Map(ts.cases.map((c) => [c.id, c] as const));
  const validUrl = /^https?:\/\/\S+$/.test(baseUrl.trim());
  const rows = run?.results.filter((r) => filter === "all" || r.status === filter) ?? [];
  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Run the tests</h4>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
            <p className="text-xs font-bold text-slate-800">Script checks</p>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Verifies that every test case is traceable, complete, has its data and is present in the Playwright script. Needs no running application.
            </p>
            <button type="button" className={`${BTN_PRIMARY} mt-2`} disabled={busy !== null} onClick={onRun}>
              {busy === "run" ? "Running…" : "Run script checks"}
            </button>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
            <p className="text-xs font-bold text-slate-800">Live Playwright run</p>
            <p className="mt-0.5 text-[11px] text-slate-500">Executes the generated tests in a browser against the application URL.</p>
            <div className="mt-2 flex gap-2">
              <input
                value={baseUrl}
                onChange={(ev) => setBaseUrl(ev.target.value)}
                placeholder="https://your-application"
                aria-label="Application base URL"
                className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
              <button type="button" className={BTN_PRIMARY} disabled={busy !== null || !validUrl} onClick={onRunLive}>
                {busy === "live" ? "Running…" : "Run live"}
              </button>
            </div>
          </div>
        </div>
      </section>

      {!run ? (
        <p className="py-6 text-center text-xs text-slate-500">No run yet. Results appear here after the first run.</p>
      ) : (
        <>
          {run.liveStatus !== "not-requested" && run.liveStatus !== "completed" && (
            <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <p className="font-bold">{LIVE_NOTE[run.liveStatus]}</p>
              <p className="mt-0.5 break-words font-mono text-[11px]">{run.liveReason}</p>
              <p className="mt-1">The cases below were not executed against the application, so they show as “Not run”.</p>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              {(["all", "passed", "failed", "skipped", "not-run"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setFilter(k)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${filter === k ? "border-blue-300 bg-blue-50 text-blue-700" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}
                >
                  {k === "all" ? "All" : RESULT[k].label} <span className="text-slate-400">{k === "all" ? run.total : run.summary[k]}</span>
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <select value={run.id} onChange={(ev) => setPicked(ev.target.value)} aria-label="Run history" className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-700">
                {ts.runs.map((r) => <option key={r.id} value={r.id}>{r.id} · {r.mode === "live" ? "live" : "checks"} · {new Date(r.at).toLocaleString()}</option>)}
              </select>
              <button
                type="button"
                className={BTN}
                onClick={() =>
                  download(
                    `${run.id}-results.csv`,
                    toCsv([["Case", "Name", "Status", "Mode", "Duration (ms)", "Message"], ...run.results.map((r) => [r.caseId, names.get(r.caseId)?.name, r.status, r.live ? "live" : "checks", r.durationMs, r.message])]),
                    "text/csv",
                  )
                }
              >
                Download CSV
              </button>
            </div>
          </div>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-xs">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                <tr><th className="px-3 py-2">Case</th><th className="px-3 py-2">Scenario</th><th className="px-3 py-2">Result</th><th className="px-3 py-2">Checks</th><th className="px-3 py-2">Details</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => {
                  const c = names.get(r.caseId);
                  return (
                    <tr key={r.caseId} className="align-top">
                      <td className="px-3 py-2 font-mono text-[11px] font-bold text-slate-500">{r.caseId}</td>
                      <td className="px-3 py-2">
                        <p className="text-slate-800">{c?.name}</p>
                        {c && <Chip className={CATEGORY[c.category].chip}>{CATEGORY[c.category].label}</Chip>}
                      </td>
                      <td className="px-3 py-2"><ResultChip status={r.status} /></td>
                      <td className="px-3 py-2">
                        <ul className="space-y-0.5">
                          {r.checks.map((k) => (
                            <li key={k.name} className={k.ok ? "text-slate-600" : "font-semibold text-red-700"}>
                              <span aria-hidden>{k.ok ? "✓" : "✗"}</span> {k.name}
                            </li>
                          ))}
                        </ul>
                      </td>
                      <td className="px-3 py-2 text-[11px] text-slate-500">
                        {r.message && <p className="break-words text-red-700">{r.message}</p>}
                        {r.durationMs != null && <p>{r.durationMs} ms</p>}
                        {r.live ? <p>Executed in a browser</p> : <p>Script check only</p>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
