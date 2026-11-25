import {useEffect, useRef, useState} from 'react';
import {modernizationEngineApi} from '../api';
import type {EnginePreview, ExecutionRecord, GeneratedArtifact, ModernizationPlan, OrchestrationRecord} from '../types/modernizationEngine';

function tree(paths: string[]) {
    type Node = {children: Map<string, Node>};
    const root: Node = {children: new Map()};
    for (const path of paths) {
        let node = root;
        for (const part of path.replace(/^output\//, '').split('/').filter(Boolean)) {
            let child = node.children.get(part);
            if (!child) { child = {children: new Map()}; node.children.set(part, child); }
            node = child;
        }
    }
    const render = (node: Node, prefix = '') => [...node.children.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, child]) => child.children.size
        ? <li key={`${prefix}${name}`}><details><summary className="cursor-pointer font-mono text-xs">{name}/</summary><ul className="ml-4">{render(child, `${prefix}${name}/`)}</ul></details></li>
        : <li key={`${prefix}${name}`} className="font-mono text-xs">{name}</li>);
    return render(root);
}

function summarizeFindings(findings: EnginePreview['findings']) {
    const grouped = new Map<string, {code: string; severity: string; message: string; count: number}>();
    for (const finding of findings) {
        const key = `${finding.severity}:${finding.code}:${finding.message}`;
        const current = grouped.get(key);
        if (current) current.count += 1;
        else grouped.set(key, {...finding, count: 1});
    }
    return [...grouped.values()];
}

export function ModernizationEnginePanel({engagementId, moduleId}: {engagementId: string; moduleId?: string}) {
    const [preview, setPreview] = useState<EnginePreview>(); const [plan, setPlan] = useState<ModernizationPlan>(); const [orchestration, setOrchestration] = useState<OrchestrationRecord>();
    const [execution, setExecution] = useState<ExecutionRecord>(); const [artifacts, setArtifacts] = useState<GeneratedArtifact[]>([]); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [operatorToken, setOperatorToken] = useState(''); const [needsAuthorization, setNeedsAuthorization] = useState(false);
    const preparedKey = useRef(''); const preparingKey = useRef(''); const visibleKey = useRef('');
    const prepare = () => modernizationEngineApi.prepare(engagementId, moduleId!);
    const refreshExecution = async (id: string) => { const [current, output] = await Promise.all([modernizationEngineApi.getExecution(engagementId, id), modernizationEngineApi.executionArtifacts(engagementId, id)]); setExecution(current.execution); setArtifacts(output.artifacts); };
    useEffect(() => {const key = `${engagementId}:${moduleId || ''}`; visibleKey.current = key; setPreview(undefined); setPlan(undefined); setOrchestration(undefined); if (!moduleId || preparedKey.current === key || preparingKey.current === key) return; preparingKey.current = key; setBusy(true); setError(''); prepare().then(result => { if (visibleKey.current !== key || !result) return; preparedKey.current = key; setPreview(result.readiness); setPlan(result.plan); setOrchestration(result.orchestration); }).catch(e => { if (visibleKey.current === key) setError(e instanceof Error ? e.message : String(e)); }).finally(() => { if (visibleKey.current === key) setBusy(false); if (preparingKey.current === key) preparingKey.current = ''; });}, [engagementId, moduleId]);
    useEffect(() => { if (!execution || !['QUEUED', 'RUNNING'].includes(execution.status)) return; const timer = window.setInterval(() => refreshExecution(execution.executionId).catch(e => { if (String(e).includes('401') || String(e).includes('authentication')) setNeedsAuthorization(true); setError(String(e.message || e)); }), 2000); return () => window.clearInterval(timer); }, [execution?.executionId, execution?.status]);
    const action = async (work: () => Promise<void>) => {setBusy(true); setError(''); try {await work();} catch (e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}};
    const start = () => action(async () => {if (!plan) return; try { const created = await modernizationEngineApi.startModernization(engagementId, plan.planId); setExecution(created.execution); await refreshExecution(created.execution.executionId); } catch (e) { if (String(e).includes('401') || String(e).includes('authentication')) setNeedsAuthorization(true); throw e; }});
    const authorize = () => action(async () => {await modernizationEngineApi.authorizeExecution(operatorToken); setOperatorToken(''); setNeedsAuthorization(false); setError('Execution authorization granted. Click Start modernization.');});
    const validate = () => action(async () => {if (execution) await refreshExecution((await modernizationEngineApi.validateExecution(engagementId, execution.executionId)).execution.executionId);});
    return <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5"><div><h3 className="font-semibold text-slate-900">Code Modernization</h3><p className="text-sm text-slate-600">Preparation uses the approved target and authoritative template snapshots. Provider work begins only after one explicit Start authorization.</p></div>
        {!moduleId ? <p className="text-sm">Select and approve a module in Scope first.</p> : <>
        {busy && <p className="text-sm text-blue-700">Preparing or updating modernization records…</p>}{error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        {preview && <div className="rounded bg-slate-50 p-3 text-sm"><p>Module: <strong>{moduleId}</strong> · readiness: <strong>{preview.overallStatus}</strong></p><p>Target: {String(preview.target.language || 'unconfigured')} / {String(preview.target.framework || 'unconfigured')}</p><p>Golden templates: {preview.templates.map(t => t.id).join(', ') || 'none'}</p>{preview.findings.length > 0 && <><p className="mt-2 text-xs text-slate-600">{preview.findings.filter(f => f.severity === 'blocker').length} blockers, {preview.findings.filter(f => f.severity === 'warning').length} warnings. Repeated findings are grouped below.</p><ul className="mt-2 list-disc pl-5">{summarizeFindings(preview.findings).map(f => <li key={`${f.severity}:${f.code}:${f.message}`} className={f.severity === 'blocker' ? 'text-red-700' : f.severity === 'warning' ? 'text-amber-700' : ''}>{f.code}{f.count > 1 ? ` (${f.count})` : ''}: {f.message}</li>)}</ul></>}</div>}
        {plan && <div className="rounded bg-slate-50 p-3 text-sm"><p>Modernization plan: <strong>{plan.status}</strong> · {plan.workstreams.map(w => w.name).join(', ') || 'no evidenced workstreams'}</p><p>Providers: {plan.tasks.map(t => `${t.name} → ${t.suggestedProvider}`).join('; ')}</p>{Object.entries(plan.providerReadiness || {}).map(([provider, readiness]) => <div key={provider} className="mt-2 border-l-2 border-slate-300 pl-2"><strong>{provider}</strong>: {readiness.status} <span className="text-slate-500">({readiness.verification})</span>{readiness.issues.map(issue => <p key={issue} className="text-xs text-amber-700">{issue}</p>)}</div>)}<ul className="mt-2 list-disc pl-5 text-xs">{plan.tasks.map(task => <li key={task.taskId}><strong>{task.taskId}</strong>: {task.suggestedProvider} — {task.providerRationale}; output: {task.expectedOutputFolders.join(', ')}{task.dependencies.length ? `; depends on ${task.dependencies.join(', ')}` : ''}{task.fallbackEligible ? `; fallback: ${task.fallbackProvider}` : ''}</li>)}</ul>{plan.blockers.length > 0 && <p className="text-red-700">Blocked: {plan.blockers.map(b => b.code).join(', ')}</p>}<button type="button" disabled={busy || !['READY_FOR_REVIEW', 'APPROVED_PLAN'].includes(plan.status)} onClick={start} className="mt-2 rounded bg-blue-700 px-3 py-1.5 text-white disabled:opacity-50">Start modernization</button></div>}
        {(!execution || needsAuthorization) && <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm"><p className="font-medium">{execution ? 'Renew execution authorization' : 'Authorize execution before starting'}</p><p className="mt-1">Enter the configured operator token. It is exchanged for a short-lived HttpOnly session and is not stored in the UI.</p><div className="mt-2 flex gap-2"><input type="password" value={operatorToken} onChange={e => setOperatorToken(e.target.value)} className="rounded border p-2" placeholder="Operator token" /><button type="button" disabled={busy || !operatorToken} onClick={authorize} className="rounded bg-blue-700 px-3 py-1.5 text-white disabled:opacity-50">Authorize</button></div>{needsAuthorization && <p className="mt-2 text-amber-800">Authorization is required to refresh execution logs and artifacts.</p>}</div>}
        {orchestration && <div className="rounded bg-slate-50 p-3 text-sm"><p>Prepared task orchestration: <strong>{orchestration.status}</strong> · {orchestration.assignments.length} task assignments</p><p>{orchestration.assignments.map(a => `${a.taskId} → ${a.agentId}`).join('; ')}</p></div>}
        <div className="rounded bg-slate-950 p-3 font-mono text-xs text-slate-100"><p className="mb-2 text-emerald-300">modernization execution {execution ? `${execution.executionId.slice(0, 12)} · ${execution.status}` : 'not started'}</p>{execution ? <><div className="max-h-56 overflow-auto space-y-1">{execution.logs.length ? execution.logs.map((log, index) => <p key={index}>[{new Date(log.at).toLocaleString()}] {log.taskId ? `${log.taskId} ` : ''}{log.provider ? `${log.provider} ` : ''}{log.status} {log.message}</p>) : <p>No persisted execution events yet.</p>}</div><p className="mt-2">Generated artifacts: {execution.artifacts.length}</p>{execution.status === 'COMPLETED' && <button type="button" disabled={busy} onClick={validate} className="mt-2 text-sky-300 underline">Validate generated output</button>}{execution.validation?.map(v => <p key={v.stage} className="mt-1">validation {v.stage}: {v.status} — {v.message}</p>)}</> : <p>Modernization has not started. Review the prepared package, readiness findings, task plan, and provider allocation above.</p>}</div>
        {artifacts.length > 0 && <details className="rounded bg-slate-50 p-3"><summary className="cursor-pointer text-sm font-medium">Generated application files ({artifacts.length})</summary><ul className="mt-2 max-h-64 overflow-auto">{tree(artifacts.map(a => a.path))}</ul></details>}
        <details><summary className="cursor-pointer text-sm">Advanced details</summary><p className="mt-2 text-xs text-slate-500">All packages, plans, approvals, execution events, and artifacts remain persisted and auditable. Provider execution is authorized server-side; React never receives credentials.</p></details>
        </>}</section>;
}
