import React, { useState } from 'react';
import { X, RotateCcw, AlertTriangle, ShieldAlert, Loader2 } from 'lucide-react';
import { StageName } from '../types';

interface RollbackModalProps {
  stage: StageName | null;
  currentVersion?: number;
  onClose: () => void;
  onExecuteRollback: (
    stage: StageName,
    targetVersion: number,
    reason?: string,
    force?: boolean
  ) => Promise<void>;
}

export const RollbackModal: React.FC<RollbackModalProps> = ({
  stage,
  currentVersion = 1,
  onClose,
  onExecuteRollback,
}) => {
  const [targetVersion, setTargetVersion] = useState<number>(1);
  const [reason, setReason] = useState<string>('');
  const [force, setForce] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!stage) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setIsSubmitting(true);
    try {
      await onExecuteRollback(stage, targetVersion, reason.trim() || undefined, force);
      onClose();
    } catch (err: any) {
      setErrorMsg(err.message || 'Rollback failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
      <div className="glass-panel rounded-2xl border border-slate-700/80 w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30">
              <RotateCcw className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Stage Rollback & Recovery</h3>
              <p className="text-xs text-slate-400 font-mono">Stage: <span className="text-amber-400 font-bold uppercase">{stage}</span></p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="p-3.5 rounded-xl bg-amber-950/40 border border-amber-800/50 text-amber-300 text-xs flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Additive Rollback Operation</p>
              <p className="mt-0.5 text-amber-200/80">
                Rolling back creates a <strong>new artifact version</strong> containing restored historical content. Historical versions will NOT be deleted.
              </p>
            </div>
          </div>

          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs flex items-start gap-2.5">
              <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Rollback Rejected:</p>
                <p className="mt-0.5 font-mono">{errorMsg}</p>
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5 font-mono">
              Target Historical Version:
            </label>
            <input
              type="number"
              min={1}
              value={targetVersion}
              onChange={(e) => setTargetVersion(parseInt(e.target.value, 10) || 1)}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-100 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
              required
            />
            <p className="text-[11px] text-slate-500 mt-1 font-mono">
              Select target version number (e.g. 1).
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5 font-mono">
              Rollback Reason (Audit Log):
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Reverting schema changes in v2"
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-100 text-xs focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>

          <div className="flex items-center gap-2 pt-2">
            <input
              type="checkbox"
              id="force-toggle"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="w-4 h-4 rounded bg-slate-900 border-slate-700 text-amber-500 focus:ring-amber-500"
            />
            <label htmlFor="force-toggle" className="text-xs text-slate-300 font-medium select-none cursor-pointer">
              Force Rollback (bypasses downstream dependency warnings)
            </label>
          </div>

          {/* Buttons */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs flex items-center gap-2 transition-colors disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Executing Rollback...</span>
                </>
              ) : (
                <>
                  <RotateCcw className="w-4 h-4" />
                  <span>Execute Rollback</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
