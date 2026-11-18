import React, { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, RotateCcw } from 'lucide-react';
import type { ArtifactVersion, StageName, StageRollbackResult } from '../types';
import { ApiError, api, errorMessage } from '../services/api';
import { STAGE_META } from '../lib/stages';
import { cn, formatDateTime } from '../lib/utils';
import { ErrorNote, Modal, Spinner } from './ui';

interface RollbackModalProps {
  projectId: string;
  runId: string;
  stage: StageName | null;
  onClose: () => void;
  onDone: (result: StageRollbackResult) => void;
  onOpenArtifact: (artifactId: string) => void;
}

/** Advanced: artifact-level rollback of a single agent's output (creates a new artifact version). */
export const RollbackModal: React.FC<RollbackModalProps> = ({ projectId, runId, stage, onClose, onDone, onOpenArtifact }) => {
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [target, setTarget] = useState<number | null>(null);
  const [reason, setReason] = useState('');
  const [force, setForce] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; conflict: boolean } | null>(null);

  useEffect(() => {
    if (!stage) return;
    let cancelled = false;
    setVersions([]);
    setTarget(null);
    setReason('');
    setForce(false);
    setError(null);
    setLoadError(null);
    setLoading(true);
    api
      .getArtifactVersions(projectId, stage)
      .then((v) => {
        if (cancelled) return;
        const sorted = [...v].sort((a, b) => b.version - a.version);
        setVersions(sorted);
        const candidate = sorted.find((x, i) => i > 0 && x.status === 'COMPLETED');
        setTarget(candidate?.version ?? null);
      })
      .catch((err) => !cancelled && setLoadError(errorMessage(err, 'Failed to load versions')))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [projectId, stage]);

  if (!stage) return null;
  const latest = versions[0]?.version;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (target == null) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.rollbackStage(projectId, runId, {
        agent_name: stage,
        target_version: target,
        reason: reason.trim() || undefined,
        force,
      });
      onDone(result);
      onClose();
    } catch (err) {
      setError({ message: errorMessage(err, 'Rollback failed'), conflict: err instanceof ApiError && err.status === 409 });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="md"
      icon={
        <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
          <RotateCcw className="w-5 h-5" />
        </div>
      }
      title={`${STAGE_META[stage].title} — artifact versions`}
      subtitle="Advanced: stage-level artifact rollback"
    >
      <form onSubmit={submit} className="p-4 sm:p-6 space-y-4">
        <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-800/50 text-amber-200/90 text-xs flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <p>
            Restores one agent&apos;s artifact as a <strong>new version</strong> (history is kept). It does not change the
            generated files or the active app version — use <em>Versions &amp; rollback</em> to restore a whole stable
            version.
          </p>
        </div>

        {loading && <Spinner label="Loading versions..." />}
        {loadError && <ErrorNote message={loadError} />}

        {!loading && versions.length > 0 && (
          <div className="max-h-56 overflow-y-auto space-y-1.5 pr-1">
            {versions.map((v) => (
              <label
                key={v.artifact_id}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-xl border text-xs cursor-pointer',
                  target === v.version ? 'bg-amber-950/30 border-amber-700/70' : 'bg-slate-900/70 border-slate-800 hover:border-slate-700',
                  v.version === latest && 'cursor-not-allowed opacity-70',
                )}
              >
                <input
                  type="radio"
                  name="target-version"
                  className="accent-amber-500"
                  disabled={v.version === latest}
                  checked={target === v.version}
                  onChange={() => setTarget(v.version)}
                />
                <span className="font-mono font-semibold text-slate-100 w-8">v{v.version}</span>
                <span className="flex-1 min-w-0">
                  <span className="block font-mono text-slate-400 truncate">
                    {v.run_id} · {formatDateTime(v.created_at)}
                  </span>
                  <span className="flex flex-wrap gap-1 mt-0.5">
                    <span className={cn('text-[10px] font-mono', v.status === 'COMPLETED' ? 'text-emerald-400' : 'text-rose-400')}>
                      {v.status}
                    </span>
                    {v.is_rollback && <span className="text-[10px] font-mono text-amber-300">rollback</span>}
                    {v.version === latest && <span className="text-[10px] font-mono text-blue-300">latest</span>}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    onOpenArtifact(v.artifact_id);
                  }}
                  className="text-[11px] text-blue-300 hover:text-blue-200 shrink-0"
                >
                  view
                </button>
              </label>
            ))}
          </div>
        )}
        {!loading && !loadError && versions.length < 2 && (
          <p className="text-xs text-slate-500">There is no earlier version of this artifact to roll back to.</p>
        )}

        <div>
          <label htmlFor="stage-rb-reason" className="block text-xs font-semibold text-slate-300 mb-1.5">
            Reason (audit log)
          </label>
          <input
            id="stage-rb-reason"
            type="text"
            value={reason}
            maxLength={300}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Reverting a bad requirements change"
            className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-slate-100 text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} className="accent-amber-500" />
          Force (roll back even though downstream artifacts depend on this one)
        </label>

        {error && (
          <ErrorNote
            title={error.conflict ? 'Rollback rejected (dependency conflict)' : 'Rollback failed'}
            message={error.conflict && !force ? `${error.message}\nEnable "Force" to override.` : error.message}
          />
        )}

        <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || target == null}
            className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
            {target != null ? `Restore v${target}` : 'Select a version'}
          </button>
        </div>
      </form>
    </Modal>
  );
};
