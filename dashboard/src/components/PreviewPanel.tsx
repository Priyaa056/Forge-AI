import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, ExternalLink, Eye, EyeOff, KeyRound, Loader2, Monitor, Play, RefreshCw, Square } from 'lucide-react';
import type { PreviewStatus } from '../types';
import { cn } from '../lib/utils';
import { CopyButton, ErrorNote, Panel, Spinner } from './ui';

export type PreviewBusy = 'starting' | 'stopping' | null;

interface PreviewPanelProps {
  preview: PreviewStatus | null;
  loading: boolean;
  busy: PreviewBusy;
  error: string | null;
  currentVersion: number | null;
  onStart: () => void;
  onStop: () => void;
  onRefresh: () => void;
  onDismissError: () => void;
}

/** Compact preview controls for the project header. */
export const PreviewControls: React.FC<Omit<PreviewPanelProps, 'loading' | 'onRefresh' | 'onDismissError' | 'error'>> = ({
  preview,
  busy,
  currentVersion,
  onStart,
  onStop,
}) => {
  const disabled = !currentVersion;
  if (preview?.running && preview.url) {
    return (
      <div className="inline-flex items-center gap-1.5">
        <a
          href={preview.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium"
          title="Open the generated app in a new tab"
        >
          <span className="w-2 h-2 rounded-full bg-white pulse-subtle" />
          Open app v{preview.version}
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
        <button
          onClick={onStop}
          disabled={!!busy}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs disabled:opacity-50"
          title="Stop preview"
        >
          {busy === 'stopping' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5" />}
          Stop
        </button>
      </div>
    );
  }
  return (
    <button
      onClick={onStart}
      disabled={disabled || !!busy}
      title={disabled ? 'Preview becomes available after a successful run (no stable version yet)' : 'Start the generated app locally'}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-emerald-800/70 text-emerald-300 text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {busy === 'starting' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
      {busy === 'starting' ? 'Starting preview...' : 'Start preview'}
    </button>
  );
};

export const PreviewPanel: React.FC<PreviewPanelProps> = ({
  preview,
  loading,
  busy,
  error,
  currentVersion,
  onStart,
  onStop,
  onRefresh,
  onDismissError,
}) => {
  const [showPassword, setShowPassword] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const disabled = !currentVersion;

  return (
    <Panel
      title="Generated app preview"
      icon={<Monitor className="w-4 h-4 text-emerald-400" />}
      actions={
        <button
          onClick={onRefresh}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
          title="Refresh preview status"
          aria-label="Refresh preview status"
        >
          <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
        </button>
      }
    >
      <div className="space-y-4">
        <p className="text-xs text-slate-400">
          Runs the project&apos;s <strong>active version</strong> as a separate local application (its own API and React
          frontend) on a free port. It opens in a new tab and is independent of this platform dashboard.
        </p>

        {disabled && (
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800 text-xs text-slate-400">
            Preview is unavailable: this project has no stable version yet. It becomes available after a run in which all
            seven agents succeed.
          </div>
        )}

        {error && <ErrorNote title="Preview error" message={error} onDismiss={onDismissError} />}

        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-mono',
              preview?.running ? 'bg-emerald-950/50 border-emerald-800/70 text-emerald-300' : 'bg-slate-900 border-slate-700 text-slate-400',
            )}
          >
            <span className={cn('w-2 h-2 rounded-full', preview?.running ? 'bg-emerald-400 pulse-subtle' : 'bg-slate-600')} />
            {preview?.running ? `Running v${preview.version}` : 'Stopped'}
          </span>
          {!preview?.running ? (
            <button
              onClick={onStart}
              disabled={disabled || !!busy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {busy === 'starting' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              {busy === 'starting' ? 'Starting...' : 'Start preview'}
            </button>
          ) : (
            <>
              <button
                onClick={onStart}
                disabled={!!busy}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs disabled:opacity-50"
                title="Restart the preview on the active version"
              >
                {busy === 'starting' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                Restart
              </button>
              <button
                onClick={onStop}
                disabled={!!busy}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-950/70 hover:bg-rose-900/70 border border-rose-800/70 text-rose-200 text-xs disabled:opacity-50"
              >
                {busy === 'stopping' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5" />}
                Stop
              </button>
            </>
          )}
          {busy === 'starting' && (
            <Spinner label="Building the frontend (first start only) and starting the app; this can take 5-60 s." />
          )}
        </div>

        {preview?.running && preview.url && (
          <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-800/50 flex flex-wrap items-center gap-2">
            <a
              href={preview.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-mono text-emerald-300 hover:text-emerald-200 break-all"
            >
              {preview.url}
              <ExternalLink className="w-3.5 h-3.5 shrink-0" />
            </a>
            <CopyButton text={preview.url} label="URL" className="ml-auto" />
          </div>
        )}

        {preview?.stale && (
          <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-800/60 text-xs text-amber-200 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <span>
              The preview is running v{preview.version}, but the active version is v{preview.current_version}. Restart the
              preview to see the latest version.
            </span>
          </div>
        )}

        {preview?.message && (
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800 text-xs text-slate-300 break-words">{preview.message}</div>
        )}

        {preview && (
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800 space-y-2">
            <h3 className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
              <KeyRound className="w-3.5 h-3.5 text-amber-400" />
              Generated app admin login
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr_auto] gap-x-3 gap-y-1.5 items-center text-xs">
              <span className="text-slate-500">Email</span>
              <span className="font-mono text-slate-200 break-all">{preview.admin_email}</span>
              <CopyButton text={preview.admin_email} label="email" className="justify-self-start sm:justify-self-end" />
              <span className="text-slate-500">Password</span>
              <span className="font-mono text-slate-200 break-all flex items-center gap-2">
                {showPassword ? preview.admin_password : '•'.repeat(Math.min(16, preview.admin_password.length || 8))}
                <button
                  onClick={() => setShowPassword((s) => !s)}
                  className="text-slate-500 hover:text-slate-200"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                </button>
              </span>
              <CopyButton text={preview.admin_password} label="password" className="justify-self-start sm:justify-self-end" />
            </div>
            <p className="text-[11px] text-slate-500">
              Local-only preview credentials for the generated app&apos;s seeded admin account (stored in this machine&apos;s
              workspace). They are not credentials for the FORGE AI platform.
            </p>
          </div>
        )}

        {preview && (
          <div>
            <button
              onClick={() => setShowLog((s) => !s)}
              className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200"
            >
              {showLog ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              Preview process log {preview.log_tail ? `(${preview.log_tail.split('\n').length} lines)` : '(empty)'}
            </button>
            {showLog && (
              <pre className="mt-2 p-3 rounded-xl bg-slate-950/90 border border-slate-800 font-mono text-[11px] text-slate-300 whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
                {preview.log_tail || 'No output yet.'}
              </pre>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
};
