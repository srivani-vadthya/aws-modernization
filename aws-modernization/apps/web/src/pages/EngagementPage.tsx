import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Engagement, type PhaseMeta } from "../api";
import { GateBar } from "../components/GateBar";
import { PhasePanels } from "../components/PhasePanels";

export function EngagementPage() {
  const { id } = useParams();
  const [eng, setEng] = useState<Engagement | null>(null);
  const [phases, setPhases] = useState<PhaseMeta[]>([]);
  const [phase, setPhase] = useState("discovery");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.meta().then((m) => setPhases(m.phases));
  }, []);

  useEffect(() => {
    if (!id) return;
    api
      .get(id)
      .then((e) => {
        setEng(e);
        setPhase(!e.currentPhase || e.currentPhase === "intake" ? "discovery" : e.currentPhase);
      })
      .catch((err) => setError(err.message));
  }, [id]);

  if (error) {
    return (
      <div className="p-10 max-w-xl mx-auto mt-10 rounded-xl border border-red-200 bg-red-50 text-center">
        <p className="text-red-700 font-medium">{error}</p>
        <Link to="/" className="mt-4 inline-block text-sm font-semibold text-blue-600 hover:underline">
          ← Return to Dashboard
        </Link>
      </div>
    );
  }
  if (!eng) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <div className="flex items-center gap-3 text-slate-500 font-medium text-sm">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          Loading engagement workspace…
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      {/* Sidebar Navigation */}
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-white p-5 flex flex-col justify-between shadow-sm">
        <div>
          <Link to="/" className="flex items-center gap-3 group pb-5 border-b border-slate-100">
            <img src="/VMLogo.png" alt="VModernize" className="h-7 w-auto object-contain" />
            <div className="h-5 w-px bg-slate-200" />
            <span className="text-xs font-bold tracking-wider text-slate-800 group-hover:text-blue-600 transition">
              VModernize
            </span>
          </Link>
          
          <div className="mt-5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Current Scope</span>
            <h1 className="mt-0.5 text-sm font-bold leading-snug text-slate-900">{eng.name}</h1>
            <p className="mt-1 font-mono text-[11px] text-slate-500">
              ID: {eng.id} · <span className="capitalize">{eng.sourceType}</span>
            </p>
          </div>

          <div className="mt-6">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Modernization Workflow</div>
            
            {/* Grouped Workflow Nav */}
            <div className="space-y-3">
              {/* Cluster 1: Reverse Engineering */}
              <div>
                <span className="text-[10px] font-bold uppercase text-slate-400 block px-1 mb-1">
                  1. Discovery &amp; Scope
                </span>
                <ol className="space-y-1">
                  {[
                    { id: "discovery", label: "Discovery", step: "01", altId: "graph" },
                    { id: "scope", label: "Scope & Boundaries", step: "02" },
                    { id: "semantic-ir", label: "Semantic IR", step: "03" },
                  ].map((item) => {
                    const g = eng.gates[item.id] || (item.altId ? eng.gates[item.altId] : undefined);
                    const isCurrent = phase === item.id || (item.altId && phase === item.altId);
                    const isApproved = g?.decision === "approved";
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setPhase(item.id)}
                          className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                            isCurrent
                              ? "bg-blue-50 text-blue-700 font-bold border border-blue-200 shadow-xs"
                              : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                          }`}
                        >
                          <span className="flex items-center">
                            <span className={`mr-2 font-mono text-[10px] ${isCurrent ? "text-blue-600 font-bold" : "text-slate-400"}`}>
                              {item.step}
                            </span>
                            {item.label}
                          </span>
                          {isApproved ? (
                            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700">✓</span>
                          ) : g?.status ? (
                            <span className="text-[9px] font-medium uppercase text-slate-400">{g.status}</span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </div>

              {/* Cluster 2: Specifications & Agile Planning */}
              <div>
                <span className="text-[10px] font-bold uppercase text-slate-400 block px-1 mb-1">
                  2. Requirements &amp; Plan
                </span>
                <ol className="space-y-1">
                  {[
                    { id: "requirements", label: "Requirements & Backlog", step: "04", altId: "backlog" },
                    { id: "modernize", label: "Target Architecture", step: "05" },
                  ].map((item) => {
                    const g = eng.gates[item.id] || (item.altId ? eng.gates[item.altId] : undefined);
                    const isCurrent = phase === item.id || (item.altId && phase === item.altId);
                    const isApproved = g?.decision === "approved";
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setPhase(item.id)}
                          className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                            isCurrent
                              ? "bg-blue-50 text-blue-700 font-bold border border-blue-200 shadow-xs"
                              : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                          }`}
                        >
                          <span className="flex items-center">
                            <span className={`mr-2 font-mono text-[10px] ${isCurrent ? "text-blue-600 font-bold" : "text-slate-400"}`}>
                              {item.step}
                            </span>
                            {item.label}
                          </span>
                          {isApproved ? (
                            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700">✓</span>
                          ) : g?.status ? (
                            <span className="text-[9px] font-medium uppercase text-slate-400">{g.status}</span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </div>

              {/* Cluster 3: Modernization & Delivery */}
              <div>
                <span className="text-[10px] font-bold uppercase text-slate-400 block px-1 mb-1">
                  3. Modernize &amp; Verify
                </span>
                <ol className="space-y-1">
                  {[
                    { id: "tests", label: "Tests & Parity", step: "06" },
                    { id: "failures", label: "Failure Analysis", step: "07" },
                    { id: "artifacts", label: "Final Artifacts", step: "08" },
                  ].map((item) => {
                    const g = eng.gates[item.id];
                    const isCurrent = phase === item.id;
                    const isApproved = g?.decision === "approved";
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setPhase(item.id)}
                          className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                            isCurrent
                              ? "bg-blue-50 text-blue-700 font-bold border border-blue-200 shadow-xs"
                              : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                          }`}
                        >
                          <span className="flex items-center">
                            <span className={`mr-2 font-mono text-[10px] ${isCurrent ? "text-blue-600 font-bold" : "text-slate-400"}`}>
                              {item.step}
                            </span>
                            {item.label}
                          </span>
                          {isApproved ? (
                            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700">✓</span>
                          ) : g?.status ? (
                            <span className="text-[9px] font-medium uppercase text-slate-400">{g.status}</span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </div>
            </div>
          </div>
        </div>

        <div className="pt-4 border-t border-slate-100">
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span>AWS Region</span>
            <span className="font-mono font-medium text-slate-700 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
              {eng.region}
            </span>
          </div>
        </div>
      </aside>

      {/* Main Content Pane */}
      <main className="flex min-w-0 flex-1 flex-col px-8 py-7">
        {/* Phase Header & AIOps Banner */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-blue-600">
              {phases.find((p) => p.id === phase)?.group === "reverse" ? "Phase 1: Reverse Engineering" : "Phase 2: Forward Engineering"}
            </p>
            <h2 className="text-2xl font-bold text-slate-900 mt-0.5">{phases.find((p) => p.id === phase)?.label || phase}</h2>
          </div>
          
          <div className="flex flex-wrap items-center gap-3">
            {phase !== "discovery" && eng.seed?.telemetry && (
              <div className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-mono shadow-xs">
                <span className="flex items-center gap-1.5 text-slate-700 font-bold">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                  AIOps Bedrock Telemetry
                </span>
                <span className="text-slate-300">|</span>
                <span className="text-slate-700 font-semibold">
                  {(eng.seed.telemetry.summary.totalInputTokens + eng.seed.telemetry.summary.totalOutputTokens).toLocaleString()} tokens
                </span>
                <span className="text-slate-300">|</span>
                <span className="text-emerald-700 font-bold">${eng.seed.telemetry.summary.totalCostUsd.toFixed(4)}</span>
                <span className="text-slate-300">|</span>
                <span className="text-slate-500">{(eng.seed.telemetry.summary.totalDurationMs / 1000).toFixed(1)}s</span>
              </div>
            )}
            <Link
              to="/"
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-xs transition"
            >
              All Engagements
            </Link>
          </div>
        </div>

        {/* Phase Body */}
        <div className="flex-1">
          <PhasePanels engagement={eng} phase={phase} onChange={setEng} />
        </div>

        {/* HITL Sign-off Gate Bar with Orchestrator Feedback Loop */}
        <GateBar
          engagement={eng}
          phase={phase}
          extraHint={phase === "scope" && !eng.scope ? "Select a business capability module before approving scope." : undefined}
          onDecide={async (decision, comment, actor) => {
            const next = await api.gate(eng.id, phase, decision, comment, actor);
            setEng(next);
            if (decision === "approved" && next.currentPhase) setPhase(next.currentPhase === "intake" ? "discovery" : next.currentPhase);
          }}
          onFeedback={phase === "discovery" ? undefined : async (comment: string) => {
            const res = await api.feedback(eng.id, comment, phase);
            setEng(res.engagement);
            if (res.targetPhase) {
              setPhase(res.targetPhase === "intake" ? "discovery" : res.targetPhase);
            }
          }}
        />
      </main>

    </div>
  );
}
