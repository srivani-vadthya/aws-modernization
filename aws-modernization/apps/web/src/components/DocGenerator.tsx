import {useState} from 'react';
import {api} from '../api';

export function DocGenerator({engagementId}: {engagementId: string}) {
    const [busy, setBusy] = useState<'docx' | 'html' | null>(null);
    const [error, setError] = useState<string | null>(null);

    async function download(format: 'docx' | 'html') {
        setBusy(format);
        setError(null);
        try {
            const url =
                format === 'docx'
                    ? api.generateDocsDocx(engagementId)
                    : api.generateDocsHtml(engagementId);
            const res = await fetch(url, {method: 'POST'});
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                throw new Error(body.detail || `Request failed (${res.status})`);
            }
            const blob = await res.blob();
            const objectUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            const disposition = res.headers.get('Content-Disposition') || '';
            const match = disposition.match(/filename="([^"]+)"/);
            a.href = objectUrl;
            a.download = match ? match[1] : `documentation.${format}`;
            a.click();
            URL.revokeObjectURL(objectUrl);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Download failed');
        } finally {
            setBusy(null);
        }
    }

    return (
        <div className='rounded-xl border border-slate-200 bg-white p-5 shadow-xs'>
            <div className='flex flex-wrap items-center justify-between gap-3'>
                <div>
                    <p className='text-sm font-semibold text-slate-800'>
                        Generate Project Documentation
                    </p>
                    <p className='text-xs text-slate-500 mt-0.5'>
                        AI-generated docs based on the uploaded repository —
                        downloadable as .docx or .html.
                    </p>
                </div>
                <div className='flex items-center gap-2'>
                    {/* <button
                        type='button'
                        disabled={busy !== null}
                        onClick={() => void download('docx')}
                        className='rounded-lg border border-blue-300 bg-blue-50 px-3.5 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-100 disabled:opacity-50 transition'
                    >
                        {busy === 'docx' ? 'Generating…' : '↓ Download .docx'}
                    </button> */}
                    <button
                        type='button'
                        disabled={busy !== null}
                        onClick={() => void download('html')}
                        className='rounded-lg border border-slate-300 bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition'
                    >
                        {busy === 'html' ? 'Generating…' : '↓ Download .html'}
                    </button>
                </div>
            </div>
            {busy && (
                <p className='mt-3 text-xs text-slate-500 flex items-center gap-2'>
                    <span className='h-3 w-3 animate-spin rounded-full border-2 border-blue-600 border-t-transparent' />
                    Analyzing repository and generating documentation with
                    Bedrock… this may take a moment.
                </p>
            )}
            {error && (
                <p className='mt-3 rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs text-red-700'>
                    {error}
                </p>
            )}
        </div>
    );
}
