import React from 'react';
import { Clock, CheckCircle2, XCircle, Layers } from 'lucide-react';
import { PipelineStatusSummary } from '../types';

interface MetricsHeaderProps {
  summary: PipelineStatusSummary | null;
}

export const MetricsHeader: React.FC<MetricsHeaderProps> = ({ summary }) => {
  if (!summary) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {['Total Duration', 'Successful Agents', 'Failed Agents', 'Artifacts Created'].map((label, i) => (
          <div key={i} className="glass-card rounded-xl p-4 border border-slate-800/80">
            <span className="text-xs text-slate-500 font-medium">{label}</span>
            <p className="text-xl font-bold text-slate-600 mt-1">--</p>
          </div>
        ))}
      </div>
    );
  }

  const durationDisplay =
    summary.total_duration_ms > 1000
      ? `${(summary.total_duration_ms / 1000).toFixed(2)}s`
      : `${summary.total_duration_ms}ms`;

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return 'bg-emerald-950/80 text-emerald-400 border-emerald-800/80';
      case 'FAILED':
        return 'bg-rose-950/80 text-rose-400 border-rose-800/80';
      case 'RUNNING':
        return 'bg-blue-950/80 text-blue-400 border-blue-800/80 pulse-subtle';
      default:
        return 'bg-slate-900 text-slate-400 border-slate-800';
    }
  };

  return (
    <div className="mb-8 space-y-4">
      <div className="glass-panel rounded-2xl p-5 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-white">Execution Metrics & Pipeline Status</h2>
            <span className={`text-xs font-mono font-bold px-3 py-1 rounded-full border ${getStatusBadge(summary.execution_status)}`}>
              {summary.execution_status}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 font-mono">
            Project: <span className="text-slate-200">{summary.project_id}</span> | Run: <span className="text-slate-200">{summary.run_id}</span>
          </p>
        </div>

        {summary.error_reports && Object.keys(summary.error_reports).length > 0 && (
          <div className="px-3 py-1.5 rounded-lg bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs flex items-center gap-2">
            <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>Errors reported in stage(s): {Object.keys(summary.error_reports).join(', ')}</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-card rounded-xl p-4 border border-slate-800/80 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400 font-medium">Total Duration</span>
            <p className="text-2xl font-bold text-white mt-1 font-mono">{durationDisplay}</p>
          </div>
          <div className="p-3 bg-blue-600/10 text-blue-400 rounded-xl">
            <Clock className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-xl p-4 border border-slate-800/80 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400 font-medium">Successful Agents</span>
            <p className="text-2xl font-bold text-emerald-400 mt-1 font-mono">{summary.successful_agent_count} / 7</p>
          </div>
          <div className="p-3 bg-emerald-600/10 text-emerald-400 rounded-xl">
            <CheckCircle2 className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-xl p-4 border border-slate-800/80 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400 font-medium">Failed Agents</span>
            <p className="text-2xl font-bold text-rose-400 mt-1 font-mono">{summary.failed_agent_count}</p>
          </div>
          <div className="p-3 bg-rose-600/10 text-rose-400 rounded-xl">
            <XCircle className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-xl p-4 border border-slate-800/80 flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400 font-medium">Total Artifacts</span>
            <p className="text-2xl font-bold text-indigo-400 mt-1 font-mono">{summary.artifact_count}</p>
          </div>
          <div className="p-3 bg-indigo-600/10 text-indigo-400 rounded-xl">
            <Layers className="w-5 h-5" />
          </div>
        </div>
      </div>
    </div>
  );
};
