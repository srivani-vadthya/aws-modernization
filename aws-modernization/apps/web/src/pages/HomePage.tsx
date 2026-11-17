import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

type Listed = {
  id: string;
  name: string;
  sourceType: string;
  status: string;
  currentPhase: string;
  updatedAt?: string;
  domain?: string;
};

export function HomePage() {
  const nav = useNavigate();
  const [items, setItems] = useState<Listed[]>([]);
  const [gitUrl, setGitUrl] = useState("https://github.com/cicsdev/cics-genapp.git");
  const [branch, setBranch] = useState("main");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.list().then(setItems).catch(() => setItems([]));
  }, []);

  async function run(label: string, fn: () => Promise<{ id: string }>) {
    setError(null);
    setBusy(label);
    try {
      const eng = await fn();
      nav(`/e/${eng.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(null);
    }
  }

  function onZip(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem("zip") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      setError("Choose a zip file");
      return;
    }
    void run("zip", () => api.zip(file));
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-10 flex flex-col sm:flex-row sm:items-end justify-between gap-6 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-4">
            <img src="/VMLogo.png" alt="VModernize Logo" className="h-10 w-auto object-contain" />
            <div className="h-8 w-px bg-slate-300" />
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-600">Enterprise Modernization Platform</p>
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">VModernize</h1>
            </div>
          </div>
          <p className="mt-3 max-w-2xl text-slate-600 text-sm leading-relaxed">
            Reverse-engineer legacy application estates, isolate business capabilities, and accelerate target cloud-native microservices on AWS. Driven by Bedrock AI and AWS Transform.
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-right text-xs shadow-sm">
          <div className="font-semibold text-slate-800">Region: us-east-1</div>
          <div className="text-slate-500 mt-0.5 flex items-center justify-end gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            HITL Automated Governance
          </div>
        </div>
      </header>

      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {/* Card 1: IMS (.NET 8 + React Target) */}
        <button
          type="button"
          disabled={!!busy}
          onClick={() => void run("ims", () => api.folder("c:/Surya/ims", "Insurance Management System (IMS)"))}
          className="group rounded-2xl border-2 border-blue-500/30 bg-gradient-to-br from-blue-50/80 via-white to-white p-6 text-left shadow-sm hover:border-blue-600 hover:shadow-md transition-all relative overflow-hidden"
        >
          <div className="flex items-center justify-between">
            <p className="text-[11px] uppercase tracking-wider text-blue-700 font-bold">.NET 8 &amp; React Target</p>
            <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-[10px] font-bold text-blue-700 border border-blue-200">LIVE DEMO</span>
          </div>
          <h2 className="mt-3 text-lg font-bold text-slate-900 group-hover:text-blue-600 transition">Load IMS Insurance</h2>
          <p className="mt-2 text-xs leading-relaxed text-slate-600">
            C# ASP.NET MVC monolith with EF DataContext (Policies, Claims, Clients, Billing).
          </p>
          <div className="mt-5 pt-3 border-t border-blue-100 flex items-center justify-between">
            <span className="text-xs font-semibold text-blue-600">
              {busy === "ims" ? "Analyzing IMS codebase…" : "Modernize with .NET 8 + React →"}
            </span>
            <span className="text-blue-500 text-sm group-hover:translate-x-1 transition-transform">→</span>
          </div>
        </button>

        {/* Card 2: Mainframe GenApp */}
        <button
          type="button"
          disabled={!!busy}
          onClick={() => void run("sample", () => api.sample())}
          className="group rounded-2xl border border-slate-200 bg-white p-6 text-left shadow-sm hover:border-amber-500 hover:shadow-md transition-all"
        >
          <div className="flex items-center justify-between">
            <p className="text-[11px] uppercase tracking-wider text-amber-700 font-bold">Mainframe COBOL Demo</p>
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800 border border-amber-200">SAMPLE</span>
          </div>
          <h2 className="mt-3 text-lg font-bold text-slate-900 group-hover:text-amber-700 transition">Load GenApp insurance</h2>
          <p className="mt-2 text-xs leading-relaxed text-slate-600">
            Clones IBM CICS GenApp (customers, motor &amp; home policies). Scope Motor policy into Spring Boot.
          </p>
          <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between">
            <span className="text-xs font-semibold text-amber-700">
              {busy === "sample" ? "Cloning repository…" : "Start with sample →"}
            </span>
            <span className="text-amber-600 text-sm group-hover:translate-x-1 transition-transform">→</span>
          </div>
        </button>

        {/* Card 3: Clone Git Repo */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run("git", () => api.git(gitUrl, branch));
          }}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm flex flex-col justify-between"
        >
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">Git Repository</p>
            <h2 className="mt-2 text-lg font-bold text-slate-900">Clone repository</h2>
            <input
              className="mt-3 w-full rounded-lg border border-slate-300 bg-slate-50/70 px-3 py-2 font-mono text-xs text-slate-800 placeholder-slate-400 focus:bg-white focus:border-blue-500 focus:outline-none transition"
              value={gitUrl}
              onChange={(e) => setGitUrl(e.target.value)}
              placeholder="https://github.com/org/repo.git"
            />
            <input
              className="mt-2 w-full rounded-lg border border-slate-300 bg-slate-50/70 px-3 py-2 font-mono text-xs text-slate-800 placeholder-slate-400 focus:bg-white focus:border-blue-500 focus:outline-none transition"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="branch"
            />
          </div>
          <button
            type="submit"
            disabled={!!busy}
            className="mt-4 w-full rounded-lg bg-slate-900 py-2 text-xs font-semibold text-white shadow-sm hover:bg-slate-800 disabled:opacity-40 transition"
          >
            {busy === "git" ? "Cloning and preparing discovery…" : "Clone & Discover"}
          </button>
        </form>

        {/* Card 4: Upload Zip */}
        <form onSubmit={onZip} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm flex flex-col justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">Local Archive</p>
            <h2 className="mt-2 text-lg font-bold text-slate-900">Upload ZIP</h2>
            <p className="mt-2 text-xs text-slate-500">COBOL, RPG, C#/.NET, Java, or C/C++ archives.</p>
            <input
              name="zip"
              type="file"
              accept=".zip"
              className="mt-3 block w-full text-xs text-slate-600 file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-2.5 file:py-1.5 file:text-xs file:font-semibold file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
            />
          </div>
          <button
            type="submit"
            disabled={!!busy}
            className="mt-4 w-full rounded-lg bg-slate-900 py-2 text-xs font-semibold text-white shadow-sm hover:bg-slate-800 disabled:opacity-40 transition"
          >
            {busy === "zip" ? "Unpacking…" : "Upload & Analyze"}
          </button>
        </form>
      </div>

      {error && (
        <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-medium text-red-700 flex items-center justify-between">
          <span>{error}</span>
        </div>
      )}

      <section className="mt-12">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">Active Engagements</h3>
          <span className="text-xs text-slate-500">{items.length} records</span>
        </div>
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {items.length === 0 ? (
            <p className="px-6 py-8 text-sm text-slate-500 text-center">No engagements created yet.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-600">
                <tr>
                  <th className="px-6 py-3.5">Engagement Name</th>
                  <th className="px-6 py-3.5">Source Type</th>
                  <th className="px-6 py-3.5">Domain</th>
                  <th className="px-6 py-3.5">Current Phase</th>
                  <th className="px-6 py-3.5 text-right">Engagement ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => nav(`/e/${item.id}`)}
                    className="hover:bg-slate-50/80 cursor-pointer transition"
                  >
                    <td className="px-6 py-4 font-semibold text-slate-900 flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-blue-600" />
                      {item.name}
                    </td>
                    <td className="px-6 py-4 text-xs font-medium text-slate-600">
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 border border-slate-200 font-mono text-[11px]">
                        {item.sourceType}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-600 capitalize">{item.domain || "unclassified"}</td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-200">
                        {item.currentPhase === "intake" ? "discovery" : item.currentPhase}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right font-mono text-xs text-slate-400">{item.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
