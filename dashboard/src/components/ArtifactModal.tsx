import React, { useEffect, useState } from 'react';
import { ArrowLeft, Calendar, FileCode, GitFork } from 'lucide-react';
import type { Artifact } from '../types';
import { api, errorMessage } from '../services/api';
import { agentBadgeClass } from '../lib/stages';
import { cn, formatDateTime } from '../lib/utils';
import { CopyButton, ErrorNote, Modal, Spinner, StatusBadge } from './ui';

interface ArtifactModalProps {
  artifactId: string | null;
  onClose: () => void;
}

type Tab = 'content' | 'metadata' | 'files' | 'lineage';

export const ArtifactModal: React.FC<ArtifactModalProps> = ({ artifactId, onClose }) => {
  // A stack so that lineage links can be followed and navigated back.
  const [stack, setStack] = useState<string[]>([]);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('content');

  useEffect(() => {
    setStack(artifactId ? [artifactId] : []);
  }, [artifactId]);

  const currentId = stack[stack.length - 1] ?? null;

  useEffect(() => {
    if (!currentId) {
      setArtifact(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTab('content');
    api
      .getArtifact(currentId)
      .then((a) => !cancelled && setArtifact(a))
      .catch((err) => !cancelled && setError(errorMessage(err, 'Failed to load artifact')))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [currentId]);

  if (!artifactId) return null;

  const json = artifact ? JSON.stringify(artifact.content, null, 2) : '';
  const meta = artifact?.metadata ?? {};
  const files = Array.isArray(meta.generated_files) ? meta.generated_files : [];
  const notes = Array.isArray(meta.notes) ? meta.notes : meta.notes ? [String(meta.notes)] : [];
  const extraMeta = Object.entries(meta).filter(
    ([k]) => !['generated_files', 'notes', 'generation_mode', 'attempts', 'spec_file', 'error'].includes(k),
  );

  const tabs: { id: Tab; label: string }[] = [
    { id: 'content', label: 'Content (JSON)' },
    { id: 'metadata', label: 'Metadata' },
    { id: 'files', label: `Generated files (${files.length})` },
    { id: 'lineage', label: `Lineage (${artifact?.input_artifacts.length ?? 0})` },
  ];

  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      icon={
        <div className="p-2 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30 shrink-0">
          <FileCode className="w-5 h-5" />
        </div>
      }
      title={
        <span className="flex flex-wrap items-center gap-2">
          {artifact ? artifact.artifact_type : 'Artifact'}
          {artifact && (
            <>
              <span className="text-xs font-mono px-2 py-0.5 rounded-md bg-blue-950 text-blue-400 border border-blue-800">
                v{artifact.version}
              </span>
              <span className={cn('text-xs font-mono px-2 py-0.5 rounded-md border', agentBadgeClass(artifact.agent_name))}>
                {artifact.agent_name}
              </span>
              <StatusBadge status={artifact.status} size="xs" />
            </>
          )}
        </span>
      }
      subtitle={currentId}
      headerActions={artifact && tab === 'content' ? <CopyButton text={json} label="JSON" /> : undefined}
      footer={
        <>
          {stack.length > 1 && (
            <button
              onClick={() => setStack((s) => s.slice(0, -1))}
              className="mr-auto px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium flex items-center gap-1.5"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back
            </button>
          )}
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium transition-colors"
          >
            Close
          </button>
        </>
      }
    >
      {loading && (
        <div className="p-8 flex justify-center">
          <Spinner label="Loading artifact..." />
        </div>
      )}
      {error && <ErrorNote className="m-4" message={error} />}
      {artifact && !loading && (
        <>
          <div className="px-4 sm:px-6 py-2.5 bg-slate-950/60 border-b border-slate-800/80 flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px] font-mono text-slate-400">
            <span className="flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-slate-500" />
              {formatDateTime(artifact.created_at)}
            </span>
            <span>run: {artifact.run_id}</span>
            <span>project: {artifact.project_id}</span>
          </div>
          <div className="px-3 sm:px-6 pt-3 flex gap-1 overflow-x-auto border-b border-slate-800/80">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  'px-3 py-2 text-xs font-medium border-b-2 -mb-px whitespace-nowrap transition-colors',
                  tab === t.id ? 'border-blue-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'content' && (
            <pre className="p-4 sm:p-6 bg-slate-950/90 font-mono text-[11px] sm:text-xs text-emerald-300 whitespace-pre-wrap break-words leading-relaxed">
              {json}
            </pre>
          )}

          {tab === 'metadata' && (
            <div className="p-4 sm:p-6 space-y-4 text-xs">
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  ['Generation mode', meta.generation_mode ?? '--'],
                  ['Attempts', meta.attempts ?? '--'],
                  ['Spec file', meta.spec_file ?? '--'],
                  ['Status', artifact.status],
                ].map(([k, v]) => (
                  <div key={String(k)} className="p-3 rounded-xl bg-slate-900/70 border border-slate-800">
                    <dt className="text-[11px] text-slate-500">{k}</dt>
                    <dd className="font-mono text-slate-200 mt-0.5 break-all">{String(v)}</dd>
                  </div>
                ))}
              </dl>
              {meta.error && <ErrorNote title="Error" message={String(meta.error)} />}
              {notes.length > 0 && (
                <div>
                  <h4 className="text-[11px] uppercase tracking-wide text-slate-500 mb-1.5">Notes</h4>
                  <ul className="space-y-1 list-disc pl-5 text-slate-300">
                    {notes.map((n, i) => (
                      <li key={i} className="break-words">
                        {String(n)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {extraMeta.length > 0 && (
                <div>
                  <h4 className="text-[11px] uppercase tracking-wide text-slate-500 mb-1.5">Other metadata</h4>
                  <pre className="p-3 rounded-xl bg-slate-950/90 border border-slate-800 font-mono text-[11px] text-slate-300 whitespace-pre-wrap break-words">
                    {JSON.stringify(Object.fromEntries(extraMeta), null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}

          {tab === 'files' && (
            <div className="p-4 sm:p-6">
              {files.length === 0 ? (
                <p className="text-xs text-slate-500">This agent did not write files to the generated app.</p>
              ) : (
                <ul className="space-y-1 font-mono text-xs">
                  {files.map((f) => (
                    <li key={f} className="px-3 py-1.5 rounded-lg bg-slate-900/70 border border-slate-800 text-slate-300 break-all">
                      {f}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {tab === 'lineage' && (
            <div className="p-4 sm:p-6 space-y-3">
              <p className="text-xs text-slate-400 flex items-center gap-1.5">
                <GitFork className="w-3.5 h-3.5 text-indigo-400" />
                Input artifacts this artifact was derived from (click to open).
              </p>
              {artifact.input_artifacts.length === 0 ? (
                <p className="text-xs text-slate-500">None — this is a root artifact.</p>
              ) : (
                <ul className="space-y-1.5">
                  {artifact.input_artifacts.map((id) => (
                    <li key={id}>
                      <button
                        onClick={() => setStack((s) => [...s, id])}
                        className="w-full text-left px-3 py-2 rounded-lg bg-slate-900/70 hover:bg-slate-800 border border-slate-800 font-mono text-xs text-blue-300 break-all"
                      >
                        {id}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </Modal>
  );
};
