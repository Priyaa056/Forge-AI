import React, { useMemo, useState } from 'react';
import { CheckCircle2, GitBranch, History, Loader2, RotateCcw, ScrollText } from 'lucide-react';
import type { ExecutionEvent, ProjectDetail, ProjectRollbackResult, ProjectRunEntry } from '../types';
import { cn, formatDateTime, formatDuration, isRunActive } from '../lib/utils';
import { EventLine } from './MonitoringFeed';
import { EmptyState, ErrorNote, Modal, Panel, Spinner, StatusBadge } from './ui';

interface VersionsPanelProps {
  project: ProjectDetail;
  events: ExecutionEvent[];
  eventsLoading: boolean;
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  onRollback: (targetRunId: string, reason?: string) => Promise<ProjectRollbackResult>;
}

function runRestorability(run: ProjectRunEntry): { ok: boolean; label: string } {
  if (run.is_current) return { ok: false, label: 'Active version' };
  if (run.stable) return { ok: true, label: 'Restorable' };
  if (isRunActive(run.execution_status)) return { ok: false, label: 'Still running' };
  if (run.execution_status === 'FAILED') return { ok: false, label: 'Not restorable: run failed' };
  return { ok: false, label: 'Not restorable: never promoted to a stable version' };
}

const LIFECYCLE_TYPES = new Set(['ROLLBACK_STARTED', 'ROLLBACK_COMPLETED', 'ROLLBACK_FAILED', 'VERSION_PROMOTED']);

export const VersionsPanel: React.FC<VersionsPanelProps> = ({
  project,
  events,
  eventsLoading,
  selectedRunId,
  onSelectRun,
  onRollback,
}) => {
  const [target, setTarget] = useState<ProjectRunEntry | null>(null);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProjectRollbackResult | null>(null);
  const [showAllEvents, setShowAllEvents] = useState(false);

  const versions = useMemo(() => [...project.versions].sort((a, b) => b.version - a.version), [project.versions]);
  const runs = useMemo(() => [...project.runs].reverse(), [project.runs]);
  const versionByRun = useMemo(() => {
    const m: Record<string, number> = {};
    project.versions.forEach((v) => {
      if (v.source === 'run') m[v.run_id] = v.version;
    });
    return m;
  }, [project.versions]);

  const shownEvents = useMemo(() => {
    const list = showAllEvents
      ? events
      : events.filter((e) => LIFECYCLE_TYPES.has(e.event_type) || e.event_type.startsWith('PIPELINE_'));
    return [...list].reverse();
  }, [events, showAllEvents]);

  const openConfirm = (run: ProjectRunEntry) => {
    setTarget(run);
    setReason('');
    setError(null);
  };

  const confirm = async () => {
    if (!target) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await onRollback(target.run_id, reason.trim() || undefined);
      setResult(res);
      setTarget(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Rollback failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      {result && (
        <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-800/60 text-xs text-emerald-200 flex items-start gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            Rolled back: version <strong>v{result.new_version}</strong> is now active (restored from v{result.restored_from_version}
            ). {Object.keys(result.restored_artifacts ?? {}).length} artifacts restored; files{' '}
            {result.files_verified ? 'verified by checksum' : 'NOT verified'}.
            {result.preview_restarted === true && ' The running preview was restarted on the restored version.'}
            {result.preview_restarted === false && ` The preview could not be restarted: ${result.preview_error ?? 'unknown error'}.`}
          </div>
          <button onClick={() => setResult(null)} className="text-emerald-400 hover:text-emerald-200 text-[11px]">
            Dismiss
          </button>
        </div>
      )}

      <Panel title="Stable versions" icon={<GitBranch className="w-4 h-4 text-emerald-400" />}>
        {versions.length === 0 ? (
          <EmptyState
            icon={<GitBranch className="w-6 h-6" />}
            title="No stable version yet."
            hint="A run becomes a stable version when all seven agents succeed."
          />
        ) : (
          <ul className="space-y-1.5">
            {versions.map((v) => {
              const current = v.version === project.current_version;
              return (
                <li
                  key={v.version}
                  className={cn(
                    'p-3 rounded-xl border text-xs flex flex-wrap items-center gap-x-3 gap-y-1',
                    current ? 'bg-emerald-950/30 border-emerald-700/70' : 'bg-slate-900/70 border-slate-800',
                  )}
                >
                  <span className={cn('font-mono font-bold text-sm', current ? 'text-emerald-300' : 'text-slate-200')}>
                    v{v.version}
                  </span>
                  {current && (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-600/30 border border-emerald-600/60 text-emerald-200 text-[10px] font-semibold">
                      ACTIVE
                    </span>
                  )}
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded border text-[10px] font-mono',
                      v.source === 'rollback'
                        ? 'bg-amber-950/60 border-amber-800/70 text-amber-300'
                        : 'bg-blue-950/60 border-blue-800/70 text-blue-300',
                    )}
                  >
                    {v.source === 'rollback' ? `rollback of v${v.restored_from_version ?? '?'}` : 'run'}
                  </span>
                  <button onClick={() => onSelectRun(v.run_id)} className="font-mono text-slate-400 hover:text-blue-300 underline-offset-2 hover:underline">
                    {v.run_id}
                  </button>
                  <span className="text-slate-500 font-mono ml-auto">{formatDateTime(v.promoted_at)}</span>
                  {v.reason && <p className="w-full text-slate-400 break-words">Reason: {v.reason}</p>}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel title="Runs & rollback targets" icon={<History className="w-4 h-4 text-amber-400" />}>
        <p className="text-xs text-slate-400 mb-3">
          Restoring a stable run re-activates all seven artifacts and its generated files (checksum-verified) as a new
          version. History is never deleted. Failed runs never became a stable version and cannot be restored.
        </p>
        <ul className="space-y-1.5">
          {runs.map((run) => {
            const r = runRestorability(run);
            const v = versionByRun[run.run_id];
            return (
              <li
                key={run.run_id}
                className={cn(
                  'p-3 rounded-xl border text-xs space-y-1.5',
                  run.run_id === selectedRunId ? 'border-blue-700/70 bg-blue-950/20' : 'border-slate-800 bg-slate-900/70',
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={run.execution_status ?? 'UNKNOWN'} size="xs" />
                  <button onClick={() => onSelectRun(run.run_id)} className="font-mono text-slate-200 hover:text-blue-300 hover:underline">
                    {run.run_id}
                  </button>
                  {v != null && <span className="font-mono text-emerald-300 text-[11px]">→ v{v}</span>}
                  {run.is_current && (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-600/30 border border-emerald-600/60 text-emerald-200 text-[10px] font-semibold">
                      ACTIVE
                    </span>
                  )}
                  {run.simulated_failure && (
                    <span className="text-[10px] font-mono text-amber-300">test mode: {run.simulated_failure} fails</span>
                  )}
                  <span className="ml-auto text-slate-500 font-mono">{formatDateTime(run.created_at)}</span>
                </div>
                {run.user_prompt && <p className="text-slate-400 line-clamp-2 break-words">{run.user_prompt}</p>}
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-slate-500 font-mono">
                    {formatDuration(run.total_duration_ms)}
                    {run.qa_summary?.score != null && ` · QA ${Math.round(run.qa_summary.score)}%`}
                  </span>
                  <span className="ml-auto">
                    {r.ok ? (
                      <button
                        onClick={() => openConfirm(run)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-600 hover:bg-amber-500 text-slate-950 font-semibold text-[11px]"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        Restore this version
                      </button>
                    ) : (
                      <span
                        className={cn(
                          'text-[11px]',
                          run.is_current ? 'text-emerald-400' : run.execution_status === 'FAILED' ? 'text-rose-400/80' : 'text-slate-500',
                        )}
                      >
                        {r.label}
                      </span>
                    )}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      </Panel>

      <Panel
        title="Project events"
        icon={<ScrollText className="w-4 h-4 text-blue-400" />}
        actions={
          <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer select-none">
            <input type="checkbox" checked={showAllEvents} onChange={(e) => setShowAllEvents(e.target.checked)} className="accent-blue-500" />
            Show agent lifecycle events
          </label>
        }
      >
        {eventsLoading && events.length === 0 ? (
          <Spinner label="Loading events..." />
        ) : shownEvents.length === 0 ? (
          <p className="text-xs text-slate-500">No rollbacks or promotions recorded yet.</p>
        ) : (
          <div className="max-h-80 overflow-y-auto space-y-1">
            {shownEvents.map((e) => (
              <EventLine key={e.event_id} evt={e} showRun />
            ))}
          </div>
        )}
      </Panel>

      <Modal
        open={!!target}
        onClose={() => !submitting && setTarget(null)}
        size="md"
        icon={
          <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
            <RotateCcw className="w-5 h-5" />
          </div>
        }
        title={`Restore version v${target ? versionByRun[target.run_id] ?? '?' : ''}?`}
        subtitle={target?.run_id}
        footer={
          <>
            <button
              onClick={() => setTarget(null)}
              disabled={submitting}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={confirm}
              disabled={submitting}
              className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs flex items-center gap-2 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
              {submitting ? 'Restoring...' : 'Confirm rollback'}
            </button>
          </>
        }
      >
        <div className="p-4 sm:p-6 space-y-3 text-xs">
          <p className="text-slate-300">
            The project will switch from <strong>v{project.current_version ?? '-'}</strong> to the snapshot produced by this
            run. A new version number is created; nothing is deleted. A running preview is restarted automatically.
          </p>
          {target?.user_prompt && <p className="text-slate-400 italic break-words">&ldquo;{target.user_prompt}&rdquo;</p>}
          <div>
            <label htmlFor="rb-reason" className="block font-semibold text-slate-300 mb-1.5">
              Reason (recorded in the audit log)
            </label>
            <input
              id="rb-reason"
              type="text"
              maxLength={300}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. The latest iteration broke the login page"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
          {error && <ErrorNote title="Rollback rejected" message={error} />}
        </div>
      </Modal>
    </div>
  );
};
