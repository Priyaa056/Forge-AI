import React from 'react';
import { AlertTriangle, CheckCircle2, Clock, FlaskConical, Gauge, GitBranch, Layers, XCircle } from 'lucide-react';
import type { RunSummary } from '../types';
import { STAGE_META, isStageName } from '../lib/stages';
import { cn, formatDuration, isRunActive, promotionLabel } from '../lib/utils';
import { StatusBadge } from './ui';

interface MetricsHeaderProps {
  summary: RunSummary | null;
  stalled?: boolean;
}

const Metric: React.FC<{ label: string; value: React.ReactNode; icon: React.ReactNode; tone: string; hint?: string }> = ({
  label,
  value,
  icon,
  tone,
  hint,
}) => (
  <div className="glass-card rounded-xl p-3 sm:p-4 flex items-center justify-between gap-2 min-w-0" title={hint}>
    <div className="min-w-0">
      <span className="text-[11px] text-slate-400 font-medium">{label}</span>
      <div className={cn('text-lg sm:text-xl font-bold mt-0.5 font-mono truncate', tone)}>{value}</div>
    </div>
    <div className={cn('p-2 sm:p-2.5 rounded-xl bg-slate-900/80 shrink-0', tone)}>{icon}</div>
  </div>
);

export const MetricsHeader: React.FC<MetricsHeaderProps> = ({ summary, stalled }) => {
  if (!summary) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {['Status', 'Duration', 'Completed', 'Failed', 'Artifacts', 'QA score'].map((label) => (
          <div key={label} className="glass-card rounded-xl p-4">
            <span className="text-[11px] text-slate-500 font-medium">{label}</span>
            <p className="text-xl font-bold text-slate-700 mt-1">--</p>
          </div>
        ))}
      </div>
    );
  }

  const status = summary.execution_status;
  const progress = Math.max(0, Math.min(100, summary.progress_percent ?? 0));
  const active = isRunActive(status);
  const promotion = summary.promotion;
  const qaScore = summary.qa_summary?.score;
  const errorStages = Object.keys(summary.error_reports ?? {});

  const barColor =
    status === 'FAILED'
      ? 'bg-rose-500'
      : status === 'COMPLETED'
        ? 'bg-emerald-500'
        : 'bg-gradient-to-r from-blue-500 to-indigo-500';

  return (
    <div className="space-y-3">
      <div className="glass-panel rounded-2xl p-4 border border-slate-800 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={status} />
            {active && summary.current_agent && isStageName(summary.current_agent) && (
              <span className="text-xs text-slate-300">
                Running <span className="font-semibold text-blue-300">{STAGE_META[summary.current_agent].title}</span>
              </span>
            )}
            {!(active && promotion.state === 'not_applicable') && (
            <span
              className={cn(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] font-mono',
                promotion.state === 'promoted' && 'bg-emerald-950/60 border-emerald-800/70 text-emerald-300',
                promotion.state === 'pending' && 'bg-blue-950/60 border-blue-800/70 text-blue-300 pulse-subtle',
                promotion.state === 'failed' && 'bg-rose-950/60 border-rose-800/70 text-rose-300',
                promotion.state === 'not_applicable' && 'bg-slate-900 border-slate-800 text-slate-400',
              )}
              title={
                promotion.state === 'not_applicable'
                  ? 'Only fully successful runs become a stable version'
                  : (promotion.error ?? undefined)
              }
            >
              <GitBranch className="w-3 h-3" />
              {promotionLabel(promotion)}
            </span>
            )}
            {summary.simulated_failure && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] font-mono bg-amber-950/60 border-amber-800/70 text-amber-300">
                <FlaskConical className="w-3 h-3" />
                test mode: {summary.simulated_failure} fails
              </span>
            )}
          </div>
          <span className="text-xs font-mono text-slate-300">{progress}%</span>
        </div>

        <div
          className="h-2.5 w-full rounded-full bg-slate-900 border border-slate-800 overflow-hidden"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={cn('h-full rounded-full transition-all duration-500', barColor, active && 'pulse-subtle')}
            style={{ width: `${progress}%` }}
          />
        </div>

        {status === 'FAILED' && (
          <p className="text-xs text-rose-300 flex items-start gap-1.5">
            <XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>
              This run failed{errorStages.length ? ` (${errorStages.join(', ')})` : ''}. The previous stable version, if
              any, remains active.
            </span>
          </p>
        )}
        {promotion.state === 'failed' && promotion.error && (
          <p className="text-xs text-rose-300 break-words">Promotion error: {promotion.error}</p>
        )}
        {stalled && (
          <p className="text-xs text-amber-300 flex items-start gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            No progress has been reported for a while. If the platform API was restarted, this run will not resume;
            start a new iteration.
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
        <Metric label="Duration" value={formatDuration(summary.total_duration_ms)} icon={<Clock className="w-4 h-4" />} tone="text-blue-300" />
        <Metric
          label="Completed agents"
          value={`${summary.successful_agent_count} / 7`}
          icon={<CheckCircle2 className="w-4 h-4" />}
          tone="text-emerald-400"
        />
        <Metric
          label="Failed agents"
          value={summary.failed_agent_count}
          icon={<XCircle className="w-4 h-4" />}
          tone={summary.failed_agent_count ? 'text-rose-400' : 'text-slate-300'}
        />
        <Metric label="Artifacts" value={summary.artifact_count} icon={<Layers className="w-4 h-4" />} tone="text-indigo-300" />
        <Metric
          label="QA score"
          value={qaScore != null ? `${Math.round(qaScore)}%` : '--'}
          icon={<Gauge className="w-4 h-4" />}
          tone={qaScore == null ? 'text-slate-500' : qaScore >= 80 ? 'text-emerald-400' : qaScore >= 50 ? 'text-amber-300' : 'text-rose-400'}
          hint={
            summary.qa_summary
              ? `${summary.qa_summary.tests_passed ?? 0}/${summary.qa_summary.tests_run ?? 0} tests passed`
              : 'QA has not reported yet'
          }
        />
      </div>
    </div>
  );
};
