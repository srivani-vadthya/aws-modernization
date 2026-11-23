import React, { useState, useEffect } from 'react';
import { Shield, FileText, CheckCircle2, AlertCircle, Plus } from 'lucide-react';
import axios from 'axios';

interface Policy {
  policyId: number;
  policyNumber: string;
  policyType: string;
  premiumAmount: number;
  status: string;
  effectiveDate: string;
}

export function App() {
  const [policies, setPolicies] = useState<Policy[]>([
    { policyId: 1, policyNumber: "POL-AUTO-2026-001", policyType: "Comprehensive Auto", premiumAmount: 1450.00, status: "Active", effectiveDate: "2026-01-01" },
    { policyId: 2, policyNumber: "POL-HOME-2026-042", policyType: "Homeowner Shield", premiumAmount: 2100.00, status: "Pending Underwriting", effectiveDate: "2026-02-15" }
  ]);
  const [loading, setLoading] = useState(false);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold">
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white tracking-tight">Insurance Management System (IMS)</h1>
            <p className="text-xs text-slate-400">Modernized .NET 8 WebAPI + React 18 Clean Architecture</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            Backend API: Healthy (net8.0)
          </span>
          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-sm transition">
            <Plus className="h-4 w-4" /> Issue Policy
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Active Policies</span>
            <div className="text-2xl font-bold text-white mt-1">1,248</div>
            <div className="text-xs text-emerald-400 mt-2 flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> 99.8% Sync with Aurora DB
            </div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Open Claims</span>
            <div className="text-2xl font-bold text-white mt-1">37</div>
            <div className="text-xs text-amber-400 mt-2 flex items-center gap-1">
              <AlertCircle className="h-3.5 w-3.5" /> SLA Target: &lt; 24h
            </div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
            <span className="text-xs font-medium uppercase tracking-wider text-slate-400">Monthly Gross Premium</span>
            <div className="text-2xl font-bold text-white mt-1">$482,900</div>
            <div className="text-xs text-blue-400 mt-2">Migrated from EF6 DataContext</div>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <FileText className="h-4 w-4 text-emerald-400" /> Active Policies Under Management
            </h2>
            <span className="text-xs text-slate-400">Live feed from ASP.NET Core 8 API</span>
          </div>

          <table className="w-full text-left text-sm">
            <thead className="bg-slate-950/60 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-6 py-3">Policy #</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Premium</th>
                <th className="px-6 py-3">Effective Date</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {policies.map(p => (
                <tr key={p.policyId} className="hover:bg-slate-800/40 transition">
                  <td className="px-6 py-3.5 font-mono text-xs font-semibold text-emerald-300">{p.policyNumber}</td>
                  <td className="px-6 py-3.5 text-slate-300">{p.policyType}</td>
                  <td className="px-6 py-3.5 font-semibold text-white">${p.premiumAmount.toFixed(2)}</td>
                  <td className="px-6 py-3.5 text-slate-400 text-xs">{p.effectiveDate}</td>
                  <td className="px-6 py-3.5">
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      {p.status}
                    </span>
                  </td>
                  <td className="px-6 py-3.5 text-right">
                    <button className="text-xs text-blue-400 hover:text-blue-300 font-medium">View Details</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

export default App;
