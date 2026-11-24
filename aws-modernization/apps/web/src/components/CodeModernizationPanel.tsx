import {useEffect, useState} from 'react';

import {api, type Engagement} from '../api';

type CodeFile = {path: string; language: string; content: string};
type PushResult = Awaited<ReturnType<typeof api.codePush>>;
type Module2PushResult = Awaited<ReturnType<typeof api.codePushModule2>>;
type PushOperation =
    | {module: 'module1'; result: PushResult}
    | {module: 'module2'; result: Module2PushResult};

const inputCls =
    'mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-normal focus:border-blue-500 focus:bg-white focus:outline-none';

export function CodeModernizationPanel({e}: {e: Engagement}) {
    const [project, setProject] = useState('');
    const [module1Files, setModule1Files] = useState<CodeFile[]>([]);
    const [module2Files, setModule2Files] = useState<CodeFile[]>([]);
    const [selectedModule, setSelectedModule] = useState<'module1' | 'module2'>('module1');
    const [selected, setSelected] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [module1Branches, setModule1Branches] = useState<
        Record<string, {branch: string; commitSha: string; baseBranch?: string}>
    >({});

    const [repo, setRepo] = useState('');
    const [token, setToken] = useState('');
    const [module1TargetBranch, setModule1TargetBranch] = useState('modernized-code');
    const [module2TargetBranch, setModule2TargetBranch] = useState(
        () => `modernization/module-2-${Date.now()}`,
    );
    const [base, setBase] = useState('');
    const [overwrite, setOverwrite] = useState(false);
    const [message, setMessage] = useState('Add modernized code');
    const [confirm, setConfirm] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [preview, setPreview] = useState<PushOperation | null>(null);
    const [pushed, setPushed] = useState<PushOperation | null>(null);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        let live = true;
        setLoadError(null);
        api.codePushFiles(e.id)
            .then((r) => {
                if (!live) return;
                setProject(r.project);
                setModule1Files(r.files);
                setModule1Branches(r.module1Branches ?? {});
                setSelected(r.files[0]?.path ?? null);
            })
            .catch((err) => live && setLoadError(String(err.message ?? err)));
        return () => {
            live = false;
        };
    }, [e.id]);

    const branch = selectedModule === 'module1' ? module1TargetBranch : module2TargetBranch;
    const setBranch = selectedModule === 'module1' ? setModule1TargetBranch : setModule2TargetBranch;
    const module1ParentBranch = module1Branches[repo.trim()]?.branch ?? '';
    const files = selectedModule === 'module1' ? module1Files : module2Files;
    const displayProject = selectedModule === 'module1' ? project : 'InsuranceClaims';
    const previewResult = preview?.result;
    const previewBranch = preview?.module === 'module1'
        ? preview.result.branch
        : preview?.module === 'module2'
          ? preview.result.newBranch
          : '';
    const previewBase = preview?.module === 'module1'
        ? preview.result.baseBranch
        : preview?.module === 'module2'
          ? preview.result.parentBranch
          : '';

    // A preview is only valid for the values it was made with.
    useEffect(() => {
        setPreview(null);
        setConfirm(false);
        if (selectedModule === 'module2') setModule2Files([]);
    }, [repo, branch, base, overwrite, token, message, selectedModule]);

    const current = files.find((f) => f.path === selected);
    const folders = groupByFolder(files);
    const ready = repo.trim().length > 0 && token.trim().length > 0;
    const canPush = ready && (selectedModule === 'module1' || !!module1ParentBranch);

    useEffect(() => {
        setSelected(files[0]?.path ?? null);
    }, [files]);

    async function run(apply: boolean) {
        setBusy(true);
        setError(null);
        if (apply) setPushed(null);
        try {
            if (selectedModule === 'module1') {
                const res = await api.codePush(e.id, {
                    repo: repo.trim(),
                    token: token.trim(),
                    branch: branch.trim(),
                    base: base.trim(),
                    overwrite,
                    message: message.trim(),
                    apply,
                    confirm: apply && confirm,
                });
                if (apply) {
                    setPushed({module: 'module1', result: res});
                    const commitSha = res.commitSha;
                    if (commitSha) {
                        setModule1Branches((existing) => ({
                            ...existing,
                            [res.repo]: {
                                branch: res.branch,
                                commitSha,
                                baseBranch: res.baseBranch,
                            },
                        }));
                    }
                    setPreview(null);
                    setConfirm(false);
                } else {
                    setPreview({module: 'module1', result: res});
                    setPushed(null);
                }
            } else {
                if (!module1ParentBranch) {
                    throw new Error('Push Module 1 successfully first to establish the parent branch for Module 2.');
                }
                const res: Module2PushResult = await api.codePushModule2(e.id, {
                    repo: repo.trim(),
                    token: token.trim(),
                    newBranch: branch.trim(),
                    message: message.trim(),
                    apply,
                    confirm: apply && confirm,
                });
                if (apply) {
                    setPushed({module: 'module2', result: res});
                    setPreview(null);
                    setConfirm(false);
                } else {
                    const generated = res.previewFiles ?? [];
                    setModule2Files(generated);
                    setPreview({module: 'module2', result: res});
                    setPushed(null);
                }
            }
        } catch (err) {
            setError(String((err as Error).message ?? err));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className='space-y-4'>
            <section className='rounded-xl border border-slate-200 bg-white p-5 shadow-xs'>
                <div className='flex flex-wrap items-center justify-between gap-2'>
                    <h3 className='text-xs font-bold uppercase tracking-wider text-slate-500'>
                        Generated code · {displayProject}.Api
                    </h3>
                    <div className='flex items-center gap-2'>
                        <label className='text-[10px] font-semibold text-slate-500' htmlFor='code-push-module'>
                            Module
                        </label>
                        <select
                            id='code-push-module'
                            value={selectedModule}
                            disabled={busy}
                            onChange={(ev) => setSelectedModule(ev.target.value === 'module2' ? 'module2' : 'module1')}
                            className='rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700'
                        >
                            <option value='module1'>Module 1 · {project || 'Modernized API'}</option>
                            <option value='module2'>Module 2 · InsuranceClaims</option>
                        </select>
                        <span className='rounded bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800'>
                            {files.length} files
                        </span>
                    </div>
                </div>
                {loadError && (
                    <p
                        role='alert'
                        className='mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700'
                    >
                        {loadError}
                    </p>
                )}
                <div className='mt-3 grid gap-4 lg:grid-cols-[260px_1fr]'>
                    <div className='space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3'>
                        {folders.map(([folder, items]) => (
                            <div key={folder || '.'}>
                                {folder && (
                                    <div className='mb-1 text-[10px] font-bold uppercase text-slate-400'>
                                        {folder}/
                                    </div>
                                )}
                                <ul className='space-y-0.5'>
                                    {items.map((f) => (
                                        <li key={f.path}>
                                            <button
                                                type='button'
                                                onClick={() =>
                                                    setSelected(f.path)
                                                }
                                                className={`w-full truncate rounded px-2 py-1 text-left font-mono text-[11px] ${
                                                    f.path === selected
                                                        ? 'bg-blue-100 font-semibold text-blue-800'
                                                        : 'text-slate-700 hover:bg-white'
                                                }`}
                                            >
                                                {f.path.split('/').pop()}
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </div>
                    <div className='min-w-0 rounded-lg border border-slate-200'>
                        <div className='flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-1.5'>
                            <span className='truncate font-mono text-[11px] text-slate-600'>
                                {current?.path ?? 'Select a file'}
                            </span>
                            {current && (
                                <button
                                    type='button'
                                    onClick={() => {
                                        void navigator.clipboard
                                            ?.writeText(current.content)
                                            .then(() => {
                                                setCopied(true);
                                                setTimeout(
                                                    () => setCopied(false),
                                                    1200,
                                                );
                                            });
                                    }}
                                    className='rounded border border-slate-300 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-50'
                                >
                                    {copied ? 'Copied' : 'Copy'}
                                </button>
                            )}
                        </div>
                        <pre className='max-h-96 overflow-auto p-3 text-[11px] leading-relaxed text-slate-800'>
                            {current?.content ?? (
                                selectedModule === 'module2'
                                    ? 'Preview Module 2 to generate code using the latest successful Module 1 branch.'
                                    : ''
                            )}
                        </pre>
                    </div>
                </div>
            </section>

            <section className='rounded-xl border border-slate-200 bg-white p-5 shadow-xs'>
                <h3 className='text-xs font-bold uppercase tracking-wider text-slate-500'>
                    Push code to GitHub
                </h3>
                <div className='mt-3 grid gap-4 lg:grid-cols-2'>
                    <div className='space-y-3'>
                        <label className='block text-[11px] font-semibold text-slate-600'>
                            Repository (owner/repo)
                            <input
                                value={repo}
                                placeholder='owner/repo'
                                onChange={(ev) => setRepo(ev.target.value)}
                                className={inputCls}
                            />
                        </label>
                        <label className='block text-[11px] font-semibold text-slate-600'>
                            {selectedModule === 'module1' ? 'Base branch (optional)' : 'Latest Module 1 parent branch'}
                            <input
                                value={selectedModule === 'module1' ? base : module1ParentBranch}
                                placeholder={
                                    selectedModule === 'module1'
                                        ? "Leave empty to use the repo's default branch"
                                        : 'Push Module 1 successfully first'
                                }
                                readOnly={selectedModule === 'module2'}
                                onChange={(ev) => setBase(ev.target.value)}
                                className={inputCls}
                            />
                            {selectedModule === 'module2' && !module1ParentBranch && (
                                <span className='mt-1 block font-normal text-amber-700'>
                                    No successful Module 1 branch is recorded for this repository.
                                </span>
                            )}
                        </label>
                        <label className='block text-[11px] font-semibold text-slate-600'>
                            <span className='font-mono'>GitHub token (PAT)</span>
                            <input
                                type='password'
                                autoComplete='off'
                                value={token}
                                placeholder='Used for this push only (never stored)'
                                onChange={(ev) => setToken(ev.target.value)}
                                className={inputCls}
                            />
                        </label>
                        <div className='grid gap-2 sm:grid-cols-2'>
                            <label className='block text-[11px] font-semibold text-slate-600'>
                                New branch
                                <input
                                    value={branch}
                                    onChange={(ev) => setBranch(ev.target.value)}
                                    className={inputCls}
                                />
                            </label>
                            <label className='block text-[11px] font-semibold text-slate-600'>
                                Commit message
                                <input
                                    value={message}
                                    onChange={(ev) =>
                                        setMessage(ev.target.value)
                                    }
                                    className={inputCls}
                                />
                            </label>
                        </div>
                    </div>

                    <div className='space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4'>
                        <h4 className='text-xs font-bold uppercase tracking-wider text-slate-500'>
                            What will be pushed
                        </h4>
                        <p className='text-xs text-slate-600'>
                            {files.length} {selectedModule === 'module1' ? 'Module 1' : 'Module 2'} files will be committed to a new branch
                            {selectedModule === 'module1'
                                ? ' from the configured base branch.'
                                : ' from the latest successful Module 1 branch.'}
                            {' '}Existing branches are never overwritten.
                        </p>
                        {selectedModule === 'module1' && (
                            <label className='flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] text-amber-900'>
                                <input
                                    type='checkbox'
                                    checked={overwrite}
                                    onChange={(ev) => setOverwrite(ev.target.checked)}
                                    className='mt-0.5'
                                />
                                <span>
                                    Replace existing files. Off by default: files that already exist on the base branch are kept and skipped.
                                </span>
                            </label>
                        )}
                        <button
                            type='button'
                            disabled={busy || !canPush}
                            onClick={() => void run(false)}
                            className='rounded-lg border border-blue-300 bg-white px-3.5 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-50 disabled:opacity-50'
                        >
                            {busy && !preview ? 'Working…' : 'Preview (dry run)'}
                        </button>
                        {preview && (
                            <div className='space-y-2 border-t border-slate-200 pt-3'>
                                <label className='flex items-start gap-2 text-[11px] text-slate-700'>
                                    <input
                                        type='checkbox'
                                        checked={confirm}
                                        onChange={(ev) =>
                                            setConfirm(ev.target.checked)
                                        }
                                        className='mt-0.5'
                                    />
                                    <span>
                                        I understand this creates branch{' '}
                                        <strong>{previewBranch}</strong> in{' '}
                                        <strong>{previewResult?.repo}</strong> from{' '}
                                        <strong>{previewBase}</strong> with {previewResult?.fileCount} files.
                                    </span>
                                </label>
                                <button
                                    type='button'
                                    disabled={busy || !confirm || previewResult?.fileCount === 0}
                                    onClick={() => void run(true)}
                                    className='rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-500 disabled:opacity-40'
                                >
                                    {busy ? 'Pushing…' : 'Push to GitHub'}
                                </button>
                            </div>
                        )}
                    </div>
                </div>

                {error && (
                    <p
                        role='alert'
                        className='mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700'
                    >
                        {error}
                    </p>
                )}
                {preview && previewResult && (
                    <div className='mt-3 rounded-lg border border-slate-200'>
                        <div className='border-b border-slate-100 bg-slate-50 px-4 py-2 text-xs font-bold text-slate-800'>
                            Dry run for {previewResult.repo}
                            <span className='ml-2 font-mono font-normal text-slate-500'>
                                {previewBranch}
                            </span>
                        </div>
                        <p className='border-b border-slate-100 px-4 py-1.5 text-[11px] text-slate-600'>
                            {preview.module === 'module1' ? 'Base' : 'Module 1 parent'}:{' '}
                            <strong>{previewBase}</strong> · {previewResult.fileCount} files
                            {preview.module === 'module1'
                                ? ` · ${preview.result.counts?.new ?? 0} new · ${preview.result.counts?.replace ?? 0} replace · ${preview.result.counts?.skip ?? 0} kept`
                                : ` · ${preview.result.inheritedFileCount} inherited`}
                        </p>
                        {previewResult.fileCount === 0 && (
                            <p className='border-b border-amber-100 bg-amber-50 px-4 py-2 text-[11px] text-amber-800'>
                                No new files are available to push.
                            </p>
                        )}
                        <ul className='max-h-48 divide-y divide-slate-100 overflow-auto font-mono text-[11px] text-slate-700'>
                            {preview.module === 'module1'
                                ? (preview.result.plan ?? []).map((item) => (
                                    <li key={item.path} className='flex items-center justify-between gap-2 px-4 py-1'>
                                        <span className='truncate'>{item.path}</span>
                                        <span className='text-slate-500'>{item.action}</span>
                                    </li>
                                ))
                                : (preview.result.generatedFiles ?? []).map((path) => (
                                    <li key={path} className='px-4 py-1'>{path}</li>
                                ))}
                        </ul>
                    </div>
                )}
                {pushed?.module === 'module1' && (
                    <div className='mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-900'>
                        <div className='font-bold'>
                            Pushed {pushed.result.fileCount} files to {pushed.result.repo} on
                            branch {pushed.result.branch} (from {pushed.result.baseBranch}).
                        </div>
                        {pushed.result.initialisedEmptyRepo && (
                            <p className='mt-1 text-[11px]'>
                                The repository was empty, so a README was
                                added first to start its default branch.
                            </p>
                        )}
                        <div className='mt-2 flex flex-wrap gap-3'>
                            {pushed.result.branchUrl && (
                                <a
                                    href={pushed.result.branchUrl}
                                    target='_blank'
                                    rel='noreferrer'
                                    className='font-semibold text-blue-700 underline'
                                >
                                    View branch
                                </a>
                            )}
                            {pushed.result.commitUrl && (
                                <a
                                    href={pushed.result.commitUrl}
                                    target='_blank'
                                    rel='noreferrer'
                                    className='font-semibold text-blue-700 underline'
                                >
                                    View commit
                                </a>
                            )}
                        </div>
                    </div>
                )}
                {pushed?.module === 'module2' && (
                    <div className='mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-900'>
                        <div className='font-bold'>
                            Pushed {pushed.result.fileCount} Module 2 files to {pushed.result.repo} on branch {pushed.result.newBranch} (from {pushed.result.parentBranch}).
                        </div>
                        <div className='mt-2 flex flex-wrap gap-3'>
                            {pushed.result.branchUrl && (
                                <a href={pushed.result.branchUrl} target='_blank' rel='noreferrer' className='font-semibold text-blue-700 underline'>
                                    View branch
                                </a>
                            )}
                            {pushed.result.commitUrl && (
                                <a href={pushed.result.commitUrl} target='_blank' rel='noreferrer' className='font-semibold text-blue-700 underline'>
                                    View commit
                                </a>
                            )}
                        </div>
                    </div>
                )}
            </section>
        </div>
    );
}

function groupByFolder(files: CodeFile[]): [string, CodeFile[]][] {
    const map = new Map<string, CodeFile[]>();
    for (const f of files) {
        const i = f.path.lastIndexOf('/');
        const folder = i >= 0 ? f.path.slice(0, i) : '';
        map.set(folder, [...(map.get(folder) ?? []), f]);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
}
