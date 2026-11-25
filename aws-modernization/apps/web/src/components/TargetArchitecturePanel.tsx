import {useState} from 'react';
import {api, type Engagement} from '../api';

type TargetField = 'language' | 'framework' | 'languageVersion' | 'frameworkVersion' | 'runtime' | 'runtimeVersion' | 'frontendRequirement' | 'data' | 'dataAccessTechnology' | 'orm' | 'migrationStrategy' | 'architecture' | 'apiApproach' | 'serviceDecomposition' | 'deploymentCloud' | 'deploymentRegion' | 'deploymentEnvironment' | 'integrationRequirements';
type FormState = Record<TargetField, string>;

const initial = (engagement: Engagement): FormState => {
    const target = (engagement.seed?.target || {}) as Record<string, unknown>;
    const field = (name: TargetField, fallback = '') => String(target[name] ?? fallback);
    return {
        language: field('language', 'csharp'), framework: field('framework', 'aspnetcore'), languageVersion: field('languageVersion', '8'), frameworkVersion: field('frameworkVersion', '8'), runtime: field('runtime', 'dotnet'), runtimeVersion: field('runtimeVersion', '8'),
        frontendRequirement: field('frontendRequirement', 'react'), data: field('data', 'sql server'), dataAccessTechnology: field('dataAccessTechnology'), orm: field('orm'), migrationStrategy: field('migrationStrategy'),
        architecture: field('architecture', 'clean-architecture'), apiApproach: field('apiApproach', 'controllers'), serviceDecomposition: field('serviceDecomposition'), deploymentCloud: field('deploymentCloud', 'aws'), deploymentRegion: field('deploymentRegion'), deploymentEnvironment: field('deploymentEnvironment', 'development'), integrationRequirements: field('integrationRequirements'),
    };
};

export function TargetArchitecturePanel({engagement, onChange}: {engagement: Engagement; onChange: (engagement: Engagement) => void}) {
    const [form, setForm] = useState(() => initial(engagement));
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState('');
    const target = (engagement.seed?.target || {}) as Record<string, unknown>;
    const update = (field: TargetField, value: string) => setForm(previous => ({...previous, [field]: value}));
    const select = (label: string, field: TargetField, options: Array<[string, string]>) => <label className="block text-sm"><span className="block font-medium">{label}</span><select className="mt-1 w-full rounded border p-2" value={form[field]} onChange={e => update(field, e.target.value)}>{options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>;
    const input = (label: string, field: TargetField, placeholder = '') => <label className="block text-sm"><span className="block font-medium">{label}</span><input className="mt-1 w-full rounded border p-2" value={form[field]} placeholder={placeholder} onChange={e => update(field, e.target.value)} /></label>;
    async function save(approve: boolean) {
        setBusy(true); setMessage('');
        try {
            await api.setTarget(engagement.id, {...form, approved: approve, approvedBy: approve ? 'user' : undefined});
            const refreshed = await api.get(engagement.id);
            onChange(refreshed);
            setMessage(approve ? 'Target architecture approved and persisted.' : 'Target architecture saved as a draft.');
        } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
        finally { setBusy(false); }
    }
    const approved = target.approved === true && target.approvalStatus === 'APPROVED';
    return <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
        <div><h3 className="font-semibold text-slate-900">Target Architecture</h3><p className="text-sm text-slate-600">Choose the target frontend, backend, and database. Advanced options preserve the existing configuration contract when needed.</p></div>
        <div className="grid gap-4 md:grid-cols-2">
            {select('Frontend target', 'frontendRequirement', [['react', 'React'], ['angular', 'Angular'], ['other', 'Other / not yet templated']])}
            {select('Backend technology', 'language', [['csharp', '.NET / C#'], ['java', 'Java'], ['node', 'Node.js / TypeScript'], ['python', 'Python']])}
            {select('Backend framework', 'framework', [['aspnetcore', 'ASP.NET Core'], ['spring-boot', 'Spring Boot'], ['node-express', 'Node / Express'], ['fastapi', 'FastAPI'], ['django', 'Django']])}
            {input('Framework version', 'frameworkVersion', 'e.g. 8')}
            {input('Target database', 'data', 'e.g. PostgreSQL or SQL Server')}
        </div>
        <details className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <summary className="cursor-pointer text-sm font-medium text-slate-800">Advanced options</summary>
            <p className="mt-2 text-xs text-slate-600">Use these only when the default target choices need project-specific overrides.</p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
            {input('Language version', 'languageVersion', 'e.g. 8 or 21')}
            {select('Runtime', 'runtime', [['dotnet', '.NET'], ['jvm', 'JVM'], ['node', 'Node.js'], ['python', 'Python']])}
            {input('Runtime version', 'runtimeVersion', 'e.g. 8, 21, 20, 3.12')}
            {select('Architecture pattern', 'architecture', [['clean-architecture', 'Clean architecture'], ['layered', 'Layered'], ['ddd', 'Domain-driven design'], ['hexagonal', 'Hexagonal'], ['microservice', 'Microservice']])}
            {select('API approach', 'apiApproach', [['controllers', 'Controller-based REST APIs'], ['minimal-apis', 'Minimal APIs'], ['graphql', 'GraphQL'], ['events', 'Event-driven']])}
            {input('Service decomposition', 'serviceDecomposition', 'e.g. modular monolith or bounded services')}
            {input('Data access technology', 'dataAccessTechnology', 'e.g. Entity Framework Core')}
            {input('ORM', 'orm', 'e.g. EF Core')}
            {input('Migration strategy', 'migrationStrategy', 'e.g. versioned migrations')}
            {select('Deployment cloud', 'deploymentCloud', [['aws', 'AWS'], ['azure', 'Azure'], ['gcp', 'Google Cloud'], ['other', 'Other']])}
            {input('Deployment region', 'deploymentRegion', 'Optional')}
            {select('Environment', 'deploymentEnvironment', [['development', 'Development'], ['test', 'Test'], ['staging', 'Staging'], ['production', 'Production']])}
            {input('Integration requirements', 'integrationRequirements', 'APIs, queues, identity, external systems')}
            </div>
        </details>
        <div className="flex flex-wrap items-center gap-3"><button type="button" disabled={busy} onClick={() => save(false)} className="rounded border border-blue-700 px-4 py-2 text-sm text-blue-700 disabled:opacity-50">Save draft</button><button type="button" disabled={busy} onClick={() => save(true)} className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Review and approve target</button><span className={approved ? 'text-sm text-emerald-700' : 'text-sm text-amber-700'}>{approved ? `Approved${target.approvedAt ? ` at ${target.approvedAt}` : ''}` : 'Draft — modernization remains blocked'}</span></div>
        {message && <p role="status" className={message.startsWith('Target') ? 'text-sm text-emerald-700' : 'text-sm text-red-700'}>{message}</p>}
    </section>;
}
