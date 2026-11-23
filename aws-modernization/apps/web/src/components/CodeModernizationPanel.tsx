import {useEffect, useState} from 'react';

import {api, type Engagement} from '../api';

type CodeFile = {path: string; language: string; content: string};
type PushResult = Awaited<ReturnType<typeof api.codePush>>;

const inputCls =
    'mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-normal focus:border-blue-500 focus:bg-white focus:outline-none';

export function CodeModernizationPanel({e}: {e: Engagement}) {
    const [project, setProject] = useState('');
    const [files, setFiles] = useState<CodeFile[]>([]);
    const [selected, setSelected] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);

    const [repo, setRepo] = useState('');
    const [token, setToken] = useState('');
    const [branch, setBranch] = useState('modernized-code');
    const [base, setBase] = useState('');
    const [overwrite, setOverwrite] = useState(false);
    const [message, setMessage] = useState('Add modernized code');
    const [confirm, setConfirm] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [preview, setPreview] = useState<PushResult | null>(null);
    const [pushed, setPushed] = useState<PushResult | null>(null);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        let live = true;
        setLoadError(null);
        api.codePushFiles(e.id)
            .then((r) => {
                if (!live) return;
                setProject(r.project);
                setFiles(r.files);
                setSelected(r.files[0]?.path ?? null);
            })
            .catch((err) => live && setLoadError(String(err.message ?? err)));
        return () => {
            live = false;
        };
    }, [e.id]);

    // A preview is only valid for the values it was made with.
    useEffect(() => {
        setPreview(null);
        setConfirm(false);
    }, [repo, branch, base, overwrite, token, message]);

    const current = files.find((f) => f.path === selected);
    const folders = groupByFolder(files);
    const ready = repo.trim().length > 0 && token.trim().length > 0;

    async function run(apply: boolean) {
        setBusy(true);
        setError(null);
        if (apply) setPushed(null);
        try {
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
                setPushed(res);
                setPreview(null);
                setConfirm(false);
            } else {
                setPreview(res);
                setPushed(null);
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
                        Modernized code{project ? ` · ${project}.Api` : ''}
                    </h3>
                    <span className='rounded bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800'>
                        Demo project · {files.length} files
                    </span>
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
                            {current?.content}
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
                            Base branch (optional)
                            <input
                                value={base}
                                placeholder="Leave empty to use the repo's default branch"
                                onChange={(ev) => setBase(ev.target.value)}
                                className={inputCls}
                            />
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
                            {files.length} code files as one commit on a new
                            branch, built on top of the base branch. Existing
                            branches are never overwritten.
                        </p>
                        <label className='flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] text-amber-900'>
                            <input
                                type='checkbox'
                                checked={overwrite}
                                onChange={(ev) => setOverwrite(ev.target.checked)}
                                className='mt-0.5'
                            />
                            <span>
                                Replace existing files. Off by default: files
                                that already exist on the base branch are kept
                                and skipped.
                            </span>
                        </label>
                        <button
                            type='button'
                            disabled={busy || !ready}
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
                                        <strong>{preview.branch}</strong> in{' '}
                                        <strong>{preview.repo}</strong> from{' '}
                                        <strong>{preview.baseBranch}</strong>{' '}
                                        with {preview.fileCount} files.
                                    </span>
                                </label>
                                <button
                                    type='button'
                                    disabled={busy || !confirm || preview.fileCount === 0}
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
                {preview && (
                    <div className='mt-3 rounded-lg border border-slate-200'>
                        <div className='border-b border-slate-100 bg-slate-50 px-4 py-2 text-xs font-bold text-slate-800'>
                            Dry run for {preview.repo}
                            <span className='ml-2 font-mono font-normal text-slate-500'>
                                {preview.branch}
                            </span>
                        </div>
                        <p className='border-b border-slate-100 px-4 py-1.5 text-[11px] text-slate-600'>
                            Base: <strong>{preview.baseBranch}</strong> ·{' '}
                            {preview.counts?.new ?? 0} new ·{' '}
                            {preview.counts?.replace ?? 0} replace ·{' '}
                            {preview.counts?.skip ?? 0} kept (already exist)
                        </p>
                        {preview.fileCount === 0 && (
                            <p className='border-b border-amber-100 bg-amber-50 px-4 py-2 text-[11px] text-amber-800'>
                                Nothing to push: every file already exists on
                                the base branch. Tick &quot;Replace existing
                                files&quot; to overwrite them.
                            </p>
                        )}
                        <ul className='max-h-48 divide-y divide-slate-100 overflow-auto font-mono text-[11px] text-slate-700'>
                            {(preview.plan ?? []).map((f) => (
                                <li
                                    key={f.path}
                                    className='flex items-center justify-between gap-2 px-4 py-1'
                                >
                                    <span className='truncate'>{f.path}</span>
                                    <span
                                        className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
                                            f.action === 'new'
                                                ? 'bg-emerald-50 text-emerald-700'
                                                : f.action === 'replace'
                                                  ? 'bg-amber-50 text-amber-800'
                                                  : 'bg-slate-100 text-slate-500'
                                        }`}
                                    >
                                        {f.action === 'new'
                                            ? 'New'
                                            : f.action === 'replace'
                                              ? 'Will replace'
                                              : 'Kept (exists)'}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
                {pushed && (
                    <div className='mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-900'>
                        <div className='font-bold'>
                            Pushed {pushed.fileCount} files to {pushed.repo} on
                            branch {pushed.branch} (from {pushed.baseBranch}).
                        </div>
                        {pushed.initialisedEmptyRepo && (
                            <p className='mt-1 text-[11px]'>
                                The repository was empty, so a README was
                                added first to start its default branch.
                            </p>
                        )}
                        <div className='mt-2 flex flex-wrap gap-3'>
                            {pushed.branchUrl && (
                                <a
                                    href={pushed.branchUrl}
                                    target='_blank'
                                    rel='noreferrer'
                                    className='font-semibold text-blue-700 underline'
                                >
                                    View branch
                                </a>
                            )}
                            {pushed.commitUrl && (
                                <a
                                    href={pushed.commitUrl}
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
