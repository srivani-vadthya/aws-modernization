import { useEffect, useRef, useState } from "react";
import { api, type Engagement, type SemanticIR } from "../api";
import { ScopeGraph } from "./ScopeGraph";

const KIND_BADGE: Record<string, string> = {
  deterministic_business_rule: "bg-blue-100 text-blue-700 border-blue-200",
  legacy_plumbing_pruned: "bg-slate-100 text-slate-500 border-slate-200",
};

const KIND_LABEL: Record<string, string> = {
  deterministic_business_rule: "Business Rule",
  legacy_plumbing_pruned: "Legacy Plumbing (Pruned)",
};

function trustColor(boundary = ""): string {
  if (boundary.startsWith("Deterministic")) return "bg-red-50 text-red-700 border-red-200";
  if (boundary.startsWith("Pruned")) return "bg-slate-100 text-slate-500 border-slate-200";
  return "bg-amber-50 text-amber-700 border-amber-200";
}

export function SemanticIRPanel({ e, onChange }: { e: Engagement; onChange: (eng: Engagement) => void }) {
  const allSIR: SemanticIR[] = e.seed?.semantic_ir ?? [];
  const scopeCapId = e.scope?.capabilityId ?? null;

  // Filter to scoped module if scope is set, otherwise show all
  const sirList = scopeCapId
    ? allSIR.filter((s) => s.module === scopeCapId)
    : allSIR;

  const [selectedId, setSelectedId] = useState<string>(sirList[0]?.id ?? "");
  const [expandedRule, setExpandedRule] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const attempted = useRef<string | null>(null);

  async function generate(force: boolean) {
    setGenerating(true);
    setGenError(null);
    try {
      const updated = await api.generateSir(e.id, force);
      setSelectedId("");
      onChange(updated);
    } catch (err) {
      setGenError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  }

  // The SIR is derived from the AKG/AST of the scoped module the first time this screen is opened.
  const needsGeneration =
    !!scopeCapId && sirList.length === 0 && e.sirMeta?.capabilityId !== scopeCapId;
  useEffect(() => {
    const key = `${e.id}:${scopeCapId}`;
    if (!needsGeneration || attempted.current === key) return;
    attempted.current = key;
    void generate(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e.id, scopeCapId, needsGeneration]);

  const selected = sirList.find((s) => s.id === selectedId) ?? sirList[0];

  if (!scopeCapId) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-8 text-center text-sm text-amber-800">
        Select a scope before viewing its Semantic IR.
      </div>
    );
  }

  if (generating || needsGeneration) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-violet-200 bg-violet-50/60 p-6 text-sm text-violet-900">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-violet-600 border-t-transparent" />
        <div>
          <p className="font-semibold">Deriving the Semantic IR for {e.scope?.name}…</p>
          <p className="mt-0.5 text-xs text-violet-800">
            Tracing the module's use cases through the AST/AKG, then asking the LLM to word each contract from that
            evidence. This can take a minute.
          </p>
        </div>
      </div>
    );
  }

  if (sirList.length === 0) {
    return (
      <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-600">
        <p>
          {genError
            ? `Semantic IR generation failed: ${genError}`
            : "No Semantic IR contracts could be derived for this module: the AKG has no traced flows or operational relationships for it. Choose another scope, or re-run discovery."}
        </p>
        <button
          type="button"
          onClick={() => void generate(true)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
        >
          Try again
        </button>
      </div>
    );
  }

  const businessRules = selected?.rules.filter((r) => r.kind === "deterministic_business_rule") ?? [];
  const prunedRules = selected?.rules.filter((r) => r.kind === "legacy_plumbing_pruned") ?? [];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="rounded-xl border border-violet-200 bg-gradient-to-r from-violet-50 to-slate-50 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600 text-white text-xs font-bold shadow-sm">
              SIR
            </span>
            <div>
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900">
                Semantic Intermediate Representation
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Language-neutral business contracts extracted from legacy source — deterministic rules, state machines &amp; side effects
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="rounded bg-white border border-slate-200 px-2.5 py-1 text-slate-700">
              {sirList.length} contract{sirList.length !== 1 ? "s" : ""}
            </span>
            {scopeCapId && (
              <span className="rounded bg-violet-100 border border-violet-200 px-2.5 py-1 text-violet-700 font-semibold">
                Scoped: {e.scope?.name}
              </span>
            )}
            <button
              type="button"
              onClick={() => void generate(true)}
              disabled={generating}
              className="rounded border border-slate-300 bg-white px-2.5 py-1 font-sans font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              title="Re-derive the contracts from the AKG/AST and re-run the LLM wording"
            >
              Regenerate
            </button>
          </div>
        </div>
        {genError && <p role="alert" className="mt-2 text-xs text-red-700">Regeneration failed: {genError}</p>}
        {e.sirMeta?.capabilityId === scopeCapId && (
          <p className="mt-3 border-t border-violet-100 pt-2 text-[11px] text-slate-500">
            Derived from {e.sirMeta.basis}. Rule locations, snippets and AST nodes are read from the source; the{" "}
            {e.sirMeta.llm.status === "ok"
              ? `wording of ${e.sirMeta.llm.lifted} contract(s) was lifted by ${e.sirMeta.llm.model}`
              : "LLM was unavailable, so wording is derived from the AST alone"}
            .
          </p>
        )}
      </div>

      <ScopeGraph engagementId={e.id} capabilityId={scopeCapId} scopeName={e.scope?.name} />

      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        {/* Left: SIR contract list */}
        <div className="space-y-1.5">
          <p className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 px-1 mb-2">
            Execution Contracts
          </p>
          {sirList.map((sir) => {
            const bizCount = sir.rules.filter((r) => r.kind === "deterministic_business_rule").length;
            const prunedCount = sir.rules.filter((r) => r.kind === "legacy_plumbing_pruned").length;
            const isActive = sir.id === selectedId;
            return (
              <button
                key={sir.id}
                type="button"
                onClick={() => { setSelectedId(sir.id); setExpandedRule(null); }}
                className={`w-full rounded-xl border p-3.5 text-left transition ${
                  isActive
                    ? "border-violet-400 bg-violet-50 shadow-sm ring-1 ring-violet-300/40"
                    : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="font-mono text-[10px] font-bold text-violet-600 block">{sir.id}</span>
                    <span className={`text-xs font-semibold mt-0.5 block truncate ${isActive ? "text-violet-900" : "text-slate-800"}`}>
                      {sir.name}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-0.5 block truncate">{sir.summary}</span>
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                  <span className="rounded bg-blue-100 border border-blue-200 px-1.5 py-0.5 text-[9px] font-bold text-blue-700">
                    {bizCount} rules
                  </span>
                  {prunedCount > 0 && (
                    <span className="rounded bg-slate-100 border border-slate-200 px-1.5 py-0.5 text-[9px] font-bold text-slate-500">
                      {prunedCount} pruned
                    </span>
                  )}
                  <span className="rounded bg-slate-50 border border-slate-200 px-1.5 py-0.5 text-[9px] text-slate-500 font-mono">
                    {sir.module}
                  </span>
                  {sir.origin && (
                    <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold ${sir.origin === "llm" ? "bg-violet-50 border-violet-200 text-violet-700" : "bg-slate-50 border-slate-200 text-slate-500"}`}>
                      {sir.origin === "llm" ? "AI-worded" : "AST-derived"}
                    </span>
                  )}
                </div>
              </button>
            );
          })}

          {/* Show all / scoped toggle */}
          {scopeCapId && allSIR.length > sirList.length && (
            <p className="text-[10px] text-slate-400 text-center pt-1">
              {allSIR.length - sirList.length} contract(s) from other modules hidden
            </p>
          )}
        </div>

        {/* Right: selected SIR detail */}
        {selected && (
          <div className="space-y-4">
            {/* Contract header */}
            <div className="rounded-xl border border-violet-200 bg-white p-5 space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs font-bold text-violet-600 bg-violet-50 border border-violet-200 px-2 py-0.5 rounded">
                      {selected.id}
                    </span>
                    <span className="font-mono text-[10px] text-slate-500 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded">
                      module: {selected.module}
                    </span>
                  </div>
                  <h4 className="text-base font-bold text-slate-900">{selected.name}</h4>
                  <p className="text-xs text-slate-600 mt-1 leading-relaxed">{selected.summary}</p>
                </div>
              </div>

              {/* Inputs */}
              <div>
                <h5 className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mb-2">
                  Contract Inputs
                </h5>
                <div className="flex flex-wrap gap-2">
                  {selected.inputs.map((inp) => (
                    <div key={inp.name} className={`rounded-lg border px-3 py-1.5 text-xs ${inp.required ? "border-blue-200 bg-blue-50" : "border-slate-200 bg-slate-50"}`}>
                      <span className="font-mono font-bold text-slate-800">{inp.name}</span>
                      <span className="text-slate-400 mx-1">:</span>
                      <span className="font-mono text-blue-700">{inp.type}</span>
                      {inp.required && (
                        <span className="ml-1.5 text-[9px] font-bold text-red-600 uppercase">required</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* State machine */}
              <div>
                <h5 className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mb-2">
                  State Machine
                </h5>
                <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs">
                  {selected.stateMachine.split("->").map((state, i, arr) => (
                    <span key={i} className="flex items-center gap-1.5">
                      <span className="rounded-full border border-violet-300 bg-violet-50 px-3 py-1 text-violet-800 font-semibold">
                        {state.trim()}
                      </span>
                      {i < arr.length - 1 && (
                        <span className="text-slate-400 font-bold">→</span>
                      )}
                    </span>
                  ))}
                </div>
              </div>

              {/* Side effects */}
              <div>
                <h5 className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mb-2">
                  Side Effects &amp; Guarantees
                </h5>
                <ul className="space-y-1">
                  {selected.sideEffects.map((fx, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-slate-700">
                      <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-violet-400 shrink-0" />
                      {fx}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Integrations */}
              {selected.integrations.length > 0 && (
                <div>
                  <h5 className="text-[10px] uppercase font-semibold tracking-wider text-slate-400 mb-2">
                    Integration Dependencies
                  </h5>
                  <div className="flex flex-wrap gap-1.5">
                    {selected.integrations.map((intId) => (
                      <span key={intId} className="rounded bg-purple-50 border border-purple-200 px-2.5 py-1 font-mono text-xs text-purple-700 font-semibold">
                        {intId}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Business rules */}
            <div>
              <div className="flex items-center gap-2 mb-3">
                <h5 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Deterministic Business Rules
                </h5>
                <span className="rounded-full bg-blue-100 border border-blue-200 px-2 py-0.5 text-[10px] font-bold text-blue-700">
                  {businessRules.length}
                </span>
                <span className="text-[10px] text-slate-400 italic">Must not be altered by LLM generation</span>
              </div>
              <div className="space-y-2">
                {businessRules.map((rule) => {
                  const isOpen = expandedRule === rule.ruleId;
                  return (
                    <div key={rule.ruleId} className="rounded-xl border border-blue-200 bg-white overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setExpandedRule(isOpen ? null : rule.ruleId)}
                        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-blue-50/50 transition"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="text-[10px] text-slate-400 shrink-0">{isOpen ? "▼" : "▶"}</span>
                          <span className="font-mono text-xs font-bold text-blue-700 shrink-0">{rule.ruleId}</span>
                          <span className="text-xs text-slate-800 truncate">{rule.statement}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0 ml-3">
                          {rule.source === "llm" && (
                            <span className="hidden sm:block rounded bg-violet-50 border border-violet-200 px-2 py-0.5 text-[10px] font-bold text-violet-700">AI-worded</span>
                          )}
                          {rule.classification && (
                            <span className="hidden sm:block rounded bg-slate-100 border border-slate-200 px-2 py-0.5 text-[10px] text-slate-600 font-medium">
                              {rule.classification}
                            </span>
                          )}
                          <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${KIND_BADGE[rule.kind ?? ""] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}>
                            {KIND_LABEL[rule.kind ?? ""] ?? rule.kind}
                          </span>
                        </div>
                      </button>
                      {isOpen && (
                        <div className="border-t border-blue-100 bg-blue-50/30 px-4 py-4 space-y-3 text-xs">
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                              <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">AST Node</span>
                              <span className="font-mono text-purple-700 bg-white border border-slate-200 px-2 py-1 rounded block break-all">
                                {rule.astNode}
                              </span>
                            </div>
                            <div>
                              <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">Legacy Source Lines</span>
                              <span className="font-mono text-blue-700 bg-white border border-slate-200 px-2 py-1 rounded block">
                                {rule.legacyLines}
                              </span>
                            </div>
                          </div>
                          <div>
                            <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">Legacy Code Snippet</span>
                            <pre className="rounded-lg bg-slate-900 px-3 py-2.5 font-mono text-[11px] text-emerald-400 overflow-x-auto">
                              {rule.snippet}
                            </pre>
                          </div>
                          {rule.trustBoundary && (
                            <div className={`rounded-lg border px-3 py-2 text-[11px] font-semibold ${trustColor(rule.trustBoundary)}`}>
                              🔒 Trust Boundary: {rule.trustBoundary}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Pruned legacy plumbing */}
            {prunedRules.length > 0 && (
              <details className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
                <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-xs font-semibold text-slate-600 hover:bg-slate-100 transition">
                  <span className="flex items-center gap-2">
                    <span className="rounded bg-slate-200 border border-slate-300 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                      {prunedRules.length}
                    </span>
                    Legacy Plumbing Pruned (replaced by cloud framework)
                  </span>
                  <span className="text-slate-400">▼</span>
                </summary>
                <div className="border-t border-slate-200 divide-y divide-slate-100">
                  {prunedRules.map((rule) => (
                    <div key={rule.ruleId} className="px-4 py-3 space-y-1.5 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-slate-500">{rule.ruleId}</span>
                        <span className="text-slate-600">{rule.statement}</span>
                      </div>
                      <pre className="rounded bg-slate-800 px-2.5 py-2 font-mono text-[10px] text-slate-400 overflow-x-auto">
                        {rule.snippet}
                      </pre>
                      {rule.trustBoundary && (
                        <span className="text-[10px] text-slate-400 italic">{rule.trustBoundary}</span>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
