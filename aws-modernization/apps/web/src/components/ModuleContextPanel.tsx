import {useEffect, useState} from 'react';
import {moduleContextApi} from '../api';
import type {ContextPackage, ContextTemplate} from '../types/moduleContext';

export function ModuleContextPanel({engagementId, moduleId, targetKey}: {engagementId: string; moduleId?: string; targetKey?: string}) {
    const [packages, setPackages] = useState<ContextPackage[]>([]);
    const [templates, setTemplates] = useState<ContextTemplate[]>([]);
    const [selectedTemplates, setSelectedTemplates] = useState<string[]>([]);
    const [selectedId, setSelectedId] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [freshness, setFreshness] = useState('');
    const [integrity, setIntegrity] = useState('');
    useEffect(() => {
        let active = true;
        setPackages([]);
        setSelectedId('');
        setError('');
        if (!moduleId) return;
        Promise.all([moduleContextApi.list(engagementId, moduleId), moduleContextApi.templates(engagementId)])
            .then(([list, catalog]) => {
                if (!active) return;
                setPackages(list.packages);
                setSelectedId(list.packages[0]?.packageId || '');
                setTemplates(catalog.templates);
                setSelectedTemplates(catalog.recommendedIds);
            })
            .catch(e => {if (active) setError(String(e.message || e));});
        return () => {active = false;};
    }, [engagementId, moduleId, targetKey]);
    const current = packages.find(p => p.packageId === selectedId);
    async function generate() {
        if (!moduleId) return;
        setBusy(true);
        setError('');
        setFreshness('');
        try {
            const result = await moduleContextApi.generate(engagementId, moduleId, selectedTemplates);
            setPackages(old => [result.manifest, ...old.filter(p => p.packageId !== result.manifest.packageId)]);
            setSelectedId(result.manifest.packageId);
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {setBusy(false);}
    }
    async function checkFreshness() {
        if (!current) return;
        setBusy(true);
        setError('');
        try {
            const r = await moduleContextApi.freshness(engagementId, current.packageId);
            setFreshness(r.status + ': ' + r.reason);
        } catch (e) {setError(e instanceof Error ? e.message : String(e));}
        finally {setBusy(false);}
    }
    async function checkIntegrity() {
        if (!current) return;
        setBusy(true); setError('');
        try {
            const r = await moduleContextApi.integrity(engagementId, current.packageId);
            setIntegrity(r.valid ? `Valid: ${r.artifactCount} artifacts; ${r.internalReferences}; ${r.templateHashes}.` : 'Invalid');
        } catch (e) {setError(e instanceof Error ? e.message : String(e));}
        finally {setBusy(false);}
    }
    return (
        <section className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
            <div>
                <h3 className="font-semibold text-slate-900">Module Context Package</h3>
                <p className="text-sm text-slate-600">
                    Snapshot source, dependencies, approved-stage records and acceptance criteria for future modernization.
                    Generation preserves existing artifacts and does not start a transformation.
                </p>
                <p className="mt-1 text-sm">Selected module: <strong>{moduleId || 'Select a module in Scope first'}</strong></p>
            </div>
            <fieldset className="space-y-2" disabled={busy}>
                <legend className="text-sm font-medium">Authoritative golden skills (suggested from configured target; review selection)</legend>
                {templates.map(t => (
                    <label key={t.id} className="block text-sm">
                        <input type="checkbox" className="mr-2" disabled={!t.available}
                            checked={selectedTemplates.includes(t.id)}
                            onChange={e => setSelectedTemplates(old => e.target.checked ? [...old, t.id] : old.filter(id => id !== t.id))} />
                        {t.id} â€” {t.kind}{!t.available ? ' (unavailable)' : ''}
                        <span className="block ml-6 text-xs text-slate-500">{t.limitations.join(' ')}</span>
                        <span className="block ml-6 text-xs break-all">{t.sourceIdentity} ? {t.revision}</span>
                        <span className="block ml-6 text-xs">Dependencies: {t.dependencies.map(d => d.name + ': ' + (d.version || 'version undeclared')).join(', ')}</span>
                        {t.files.map(f => <span key={f.name} className="block ml-6 text-xs">{f.name}: {f.applicability.condition}</span>)}
                        {t.compatibility.issues.map(i => <span key={i.code} className="block ml-6 text-xs text-amber-800">{i.severity}: {i.message}</span>)}
                    </label>
                ))}
            </fieldset>
            <button type="button" onClick={generate} disabled={busy || !moduleId}
                className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {busy ? 'Workingâ€¦' : 'Generate Context Package'}
            </button>
            {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
            {packages.length > 0 && (
                <label className="block text-sm">Package version
                    <select className="ml-2 max-w-full border rounded p-1" value={selectedId}
                        onChange={e => {setSelectedId(e.target.value); setFreshness('');}}>
                        {packages.map(p => <option key={p.packageId} value={p.packageId}>
                            {new Date(p.createdAt).toLocaleString()} â€” {p.packageId.slice(0, 10)}
                        </option>)}
                    </select>
                </label>
            )}
            {current && (
                <div className="space-y-3">
                    <p className="text-sm">
                        Schema {current.schemaVersion} Â· {current.coverage.sourceFiles} source files Â· {current.coverage.sirContracts} SIR contracts Â· {current.coverage.stories} stories
                    </p>
                    <p className="text-sm">Modernization prerequisites: <strong>{current.readiness.modernizationPrerequisites}</strong>.
                        Application execution has not been verified by packaging.</p>
                    {current.contract && <div className="grid gap-2 rounded bg-slate-50 p-3 text-xs md:grid-cols-2">
                        <p>Contract readiness: <strong>{current.contract.readiness.overallStatus}</strong> · blockers {current.contract.readiness.counts.blocker || 0}, warnings {current.contract.readiness.counts.warning || 0}</p>
                        <p>Integrity scope: {current.contract.artifactCount} artifacts</p>
                        <p>Traceability: {current.contract.traceability.summary.resolvedRelationships} resolved, {current.contract.traceability.summary.missingRelationships} missing, {current.contract.traceability.summary.unresolvedReferences} unresolved</p>
                        <p>Coverage gaps: {current.contract.traceability.summary.uncoveredBusinessRules} rules, {current.contract.traceability.summary.requirementsWithoutStoryCoverage} requirements, {current.contract.traceability.summary.storiesWithoutAcceptanceCriteria} stories</p>
                        <p>Dependencies: {Object.entries(current.contract.dependencies.counts).map(([k,v]) => `${k}: ${v}`).join(', ') || 'No dependency evidence collected'}</p>
                        <p>Target: {[current.contract.target.language, current.contract.target.framework, current.contract.target.frameworkVersion, current.contract.target.database].filter(Boolean).join(' · ') || 'Not configured'}</p>
                    </div>}
                    <div className="text-sm">Packaged golden bundles: {current.templates.length === 0 ? 'None ? not ready for modernization' : current.templates.map(t =>
                        <p key={t.id} className="break-all">{t.id} ? {t.fileCount} skill files ? {t.revision || t.contentDigest} ? {t.compatibility?.status || 'legacy metadata'}</p>)}</div>
                    <p className="text-xs text-slate-500 break-all">Source digest: {current.source.repositoryContentDigest}</p>
                    <div className="flex gap-4 text-sm">
                        <a className="text-blue-700 underline" href={moduleContextApi.downloadUrl(engagementId, current.packageId)}>Download package ZIP</a>
                        <button type="button" disabled={busy} onClick={checkFreshness} className="text-blue-700 underline">Check freshness</button>
                        <button type="button" disabled={busy} onClick={checkIntegrity} className="text-blue-700 underline">Verify integrity</button>
                    </div>
                    {freshness && <p className="text-sm" role="status">{freshness}</p>}
                    {integrity && <p className="text-sm" role="status">{integrity}</p>}
                    <details>
                        <summary className="cursor-pointer text-sm font-medium">Readiness findings ({current.readiness.findings.length})</summary>
                        <ul className="mt-2 space-y-2">
                            {current.readiness.findings.map((f, i) => <li key={i} className="rounded bg-slate-50 p-2 text-sm">
                                <strong>{f.severity}: {f.code}</strong><p>{f.message}</p>
                                <p className="text-slate-600">{f.action}</p>
                                {f.evidence.length > 0 && <p className="text-xs break-all">{f.evidence.join(', ')}</p>}
                            </li>)}
                        </ul>
                    </details>
                    {current.contract && <details>
                        <summary className="cursor-pointer text-sm font-medium">Approvals and target gaps</summary>
                        <div className="mt-2 text-xs space-y-1">
                            {current.contract.approvals.records.map(a => <p key={a.gateId}>{a.gateId}: {a.status || 'status unavailable'} / {a.decision || 'decision unavailable'} · revision binding {a.binding}</p>)}
                            {current.contract.target.missingFields.length > 0 && <p>Target fields unavailable: {current.contract.target.missingFields.join(', ')}</p>}
                        </div>
                    </details>}
                    <details>
                        <summary className="cursor-pointer text-sm font-medium">Artifact provenance and approvals</summary>
                        <div className="overflow-auto max-h-80 mt-2">
                            <table className="w-full text-xs text-left">
                                <thead><tr><th>Artifact</th><th>Role</th><th>Provenance</th><th>Approval</th></tr></thead>
                                <tbody>{current.artifacts.map(a => <tr key={a.id} className="border-t">
                                    <td className="p-1">{a.path}</td><td>{a.role}</td><td>{a.provenance}</td>
                                    <td>{String(a.approval.decision || (a.approval.approved ? 'recorded' : 'not recorded'))}
                                        {a.approval.binding ? ' Â· ' + String(a.approval.binding) : ''}</td>
                                </tr>)}</tbody>
                            </table>
                        </div>
                    </details>
                </div>
            )}
        </section>
    );
}
