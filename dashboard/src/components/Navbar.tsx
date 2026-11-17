import React from 'react';
import { Cpu, Activity, ShieldCheck, FileCode } from 'lucide-react';

interface NavbarProps {
  monitoringStatus?: string;
  activeRunId?: string;
}

export const Navbar: React.FC<NavbarProps> = ({ monitoringStatus = 'ACTIVE', activeRunId }) => {
  return (
    <header className="glass-panel sticky top-0 z-30 border-b border-slate-800 px-6 py-4 mb-8">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-blue-600/20 border border-blue-500/30 rounded-xl text-blue-400">
            <Cpu className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              FORGE AI <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-blue-900/60 border border-blue-700/60 text-blue-300">v1.0.0</span>
            </h1>
            <p className="text-xs text-slate-400">Multi-Agent Orchestration, Observability & Rollback System</p>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          {activeRunId && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
              <FileCode className="w-3.5 h-3.5 text-blue-400" />
              <span>Run: {activeRunId}</span>
            </div>
          )}

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-950/60 border border-emerald-800/60 text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 pulse-subtle"></span>
            <Activity className="w-3.5 h-3.5" />
            <span>Monitoring: {monitoringStatus}</span>
          </div>

          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400">
            <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
            <span>Sanitization: Enabled</span>
          </div>
        </div>
      </div>
    </header>
  );
};
