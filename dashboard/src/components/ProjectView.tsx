import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  Download,
  FolderTree,
  GitBranch,
  Monitor,
  Plus,
  Rocket,
  Sparkles,
  TestTube,
} from 'lucide-react';
import type { ExecutionEvent, PreviewStatus, ProjectDetail, RunSummary, StageName, SystemInfo } from '../types';
import { ApiError, api, errorMessage } from '../services/api';
import { useRunMonitor } from '../hooks/useRunMonitor';
import { cn, formatDateTime } from '../lib/utils';
import { AgentGrid } from './AgentGrid';
import { ArtifactModal } from './ArtifactModal';
import { DeployPanel } from './DeployPanel';
import { FilesPanel } from './FilesPanel';
import { MetricsHeader } from './MetricsHeader';
import { MonitoringFeed } from './MonitoringFeed';
import { PreviewControls, PreviewPanel, type PreviewBusy } from './PreviewPanel';
import { PromptInput, type PromptSubmission } from './PromptInput';
import { QAPanel } from './QAPanel';
import { RollbackModal } from './RollbackModal';
import { VersionsPanel } from './VersionsPanel';
import { EmptyState, ErrorNote, Modal, Spinner, StatusBadge } from './ui';

interface ProjectViewProps {
  projectId: string;
  runId: string | null;
  system: SystemInfo | null;
  onSelectRun: (runId: string | null, replace?: boolean) => void;
  onProjectsChanged: () => void;
  onNewProject: () => void;
}

type Tab = 'feed' | 'qa' | 'deploy' | 'files' | 'versions' | 'preview';

export const ProjectView: React.FC<ProjectViewProps> = ({
  projectId,
  runId,
  system,
  onSelectRun,
  onProjectsChanged,
  onNewProject,
}) => {
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [projectError, setProjectError] = useState<{ message: string; notFound: boolean } | null>(null);
  const [tab, setTab] = useState<Tab>('feed');
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [rollbackStage, setRollbackStage] = useState<StageName | null>(null);
  const [iterationOpen, setIterationOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const [preview, setPreview] = useState<PreviewStatus | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewBusy, setPreviewBusy] = useState<PreviewBusy>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const [projectEvents, setProjectEvents] = useState<ExecutionEvent[]>([]);
  const [projectEventsLoading, setProjectEventsLoading] = useState(false);

  // ---------------------------------------------------------------- loaders
  const loadProject = useCallback(async () => {
    try {
      const p = await api.getProject(projectId);
      setProject(p);
      setProjectError(null);
    } catch (err) {
      setProjectError({
        message: errorMessage(err, 'Failed to load project'),
        notFound: err instanceof ApiError && err.status === 404,
      });
    }
  }, [projectId]);

  const loadPreview = useCallback(async () => {
    setPreviewLoading(true);
    try {
      setPreview(await api.getPreview(projectId));
    } catch (err) {
      setPreviewError(errorMessage(err, 'Failed to load preview status'));
    } finally {
      setPreviewLoading(false);
    }
  }, [projectId]);

  const loadProjectEvents = useCallback(async () => {
    setProjectEventsLoading(true);
    try {
      setProjectEvents(await api.getProjectEvents(projectId));
    } catch {
      // shown as empty; the global banner reports connectivity problems
    } finally {
      setProjectEventsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setProject(null);
    setProjectError(null);
    setPreview(null);
    setPreviewError(null);
    setProjectEvents([]);
    setTab('feed');
    void loadProject();
    void loadPreview();
    void loadProjectEvents();
  }, [loadProject, loadPreview, loadProjectEvents]);

  // Keep the preview status fresh while it runs (stale flag, log tail).
  useEffect(() => {
    if (!preview?.running || previewBusy) return;
    const t = setInterval(() => {
      api.getPreview(projectId).then(setPreview).catch(() => undefined);
    }, 5000);
    return () => clearInterval(t);
  }, [preview?.running, previewBusy, projectId]);

  // ---------------------------------------------------------------- run selection & monitoring
  const latestRunId = project?.runs.length ? project.runs[project.runs.length - 1].run_id : null;
  const effectiveRunId = runId ?? latestRunId;

  const onSettled = useCallback(
    (_s: RunSummary) => {
      void loadProject();
      void loadPreview();
      void loadProjectEvents();
      onProjectsChanged();
    },
    [loadProject, loadPreview, loadProjectEvents, onProjectsChanged],
  );
  const onStatusChange = useCallback(
    (_s: RunSummary) => {
      void loadProject();
      onProjectsChanged();
    },
    [loadProject, onProjectsChanged],
  );

  const monitor = useRunMonitor(projectId, effectiveRunId, onSettled, onStatusChange);
  const summary = monitor.summary;

  // ---------------------------------------------------------------- actions
  const startIteration = async (sub: PromptSubmission) => {
    const res = await api.createRun(projectId, { user_prompt: sub.prompt, simulate_failure: sub.simulateFailure });
    setIterationOpen(false);
    setTab('feed');
    onSelectRun(res.run_id);
    await loadProject();
    onProjectsChanged();
  };

  const rollbackProject = async (targetRunId: string, reason?: string) => {
    const res = await api.rollbackProject(projectId, targetRunId, reason);
    await Promise.all([loadProject(), loadPreview(), loadProjectEvents()]);
    onProjectsChanged();
    return res;
  };

  const startPreview = async () => {
    setPreviewBusy('starting');
    setPreviewError(null);
    try {
      setPreview(await api.startPreview(projectId));
    } catch (err) {
      setPreviewError(errorMessage(err, 'Failed to start preview'));
      void loadPreview();
    } finally {
      setPreviewBusy(null);
    }
  };

  const stopPreview = async () => {
    setPreviewBusy('stopping');
    setPreviewError(null);
    try {
      setPreview(await api.stopPreview(projectId));
    } catch (err) {
      setPreviewError(errorMessage(err, 'Failed to stop preview'));
    } finally {
      setPreviewBusy(null);
    }
  };

  const startPreviewFromHeader = () => {
    setTab('preview');
    void startPreview();
  };

  // ---------------------------------------------------------------- derived
  const runs = useMemo(() => (project ? [...project.runs].reverse() : []), [project]);
  const runNumber = useMemo(() => {
    const m: Record<string, number> = {};
    project?.runs.forEach((r, i) => (m[r.run_id] = i + 1));
    return m;
  }, [project]);
  const selectedRunEntry = project?.runs.find((r) => r.run_id === effectiveRunId) ?? null;
  const qaStatus = summary?.agents?.qa?.status ?? summary?.agent_statuses?.qa ?? 'PENDING';
  const deployStatus = summary?.agents?.deploy?.status ?? summary?.agent_statuses?.deploy ?? 'PENDING';
  const statusKey = `${summary?.execution_status}|${summary?.promotion?.state}`;

  // ---------------------------------------------------------------- render
  if (projectError && !project) {
    return (
      <div className="max-w-2xl mx-auto mt-10 space-y-4">
        <ErrorNote
          title={projectError.notFound ? 'Project not found' : 'Could not load project'}
          message={projectError.notFound ? `No project with id "${projectId}" exists on this server.` : projectError.message}
        />
        <div className="flex gap-2">
          {!projectError.notFound && (
            <button onClick={() => void loadProject()} className="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-slate-200">
              Retry
            </button>
          )}
          <button onClick={onNewProject} className="px-3 py-1.5 rounded-xl bg-blue-600 text-xs text-white">
            New project
          </button>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="p-10 flex justify-center">
        <Spinner label="Loading project..." />
      </div>
    );
  }

  const displayName = project.project_name || project.name;
  const tabs: { id: Tab; label: string; icon: React.ReactNode; badge?: React.ReactNode }[] = [
    {
      id: 'feed',
      label: 'Live feed',
      icon: <Activity className="w-3.5 h-3.5" />,
      badge: monitor.polling ? <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 pulse-subtle" /> : undefined,
    },
    {
      id: 'qa',
      label: 'QA',
      icon: <TestTube className="w-3.5 h-3.5" />,
      badge:
        summary?.qa_summary?.score != null ? (
          <span className="text-[10px] font-mono text-slate-400">{Math.round(summary.qa_summary.score)}%</span>
        ) : undefined,
    },
    { id: 'deploy', label: 'Deployment', icon: <Rocket className="w-3.5 h-3.5" /> },
    { id: 'files', label: 'Files', icon: <FolderTree className="w-3.5 h-3.5" /> },
    {
      id: 'versions',
      label: 'Versions & rollback',
      icon: <GitBranch className="w-3.5 h-3.5" />,
      badge: <span className="text-[10px] font-mono text-slate-400">{project.versions.length}</span>,
    },
    {
      id: 'preview',
      label: 'Preview',
      icon: <Monitor className="w-3.5 h-3.5" />,
      badge: preview?.running ? <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> : undefined,
    },
  ];

  return (
    <div className="space-y-5">
      {/* Project header */}
      <section className="glass-panel rounded-2xl border border-slate-800 p-4 sm:p-5 shadow-lg">
        <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg sm:text-xl font-bold text-white break-words">{displayName}</h2>
              {project.current_version ? (
                <span className="px-2 py-0.5 rounded-md bg-emerald-950/60 border border-emerald-800/70 text-emerald-300 text-xs font-mono">
                  active v{project.current_version}
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-700 text-slate-400 text-xs font-mono">
                  no stable version yet
                </span>
              )}
            </div>
            <p className="text-[11px] font-mono text-slate-500 break-all">
              {project.project_id} · created {formatDateTime(project.created_at)} · {project.runs.length} run
              {project.runs.length === 1 ? '' : 's'}
            </p>
            <p className="text-xs text-slate-400 line-clamp-2 break-words" title={project.initial_prompt}>
              {project.initial_prompt}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <button
              onClick={() => setIterationOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-medium shadow-lg shadow-blue-600/20"
            >
              <Plus className="w-3.5 h-3.5" />
              New iteration
            </button>
            {project.current_version ? (
              <a
                href={api.downloadUrl(projectId, 'current')}
                download
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-medium"
                title={`Download the source of the active version (v${project.current_version}) as a .zip`}
              >
                <Download className="w-3.5 h-3.5" />
                Download app (v{project.current_version})
              </a>
            ) : (
              <span
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-500 text-xs cursor-not-allowed"
                title="Available once a run produces a stable version"
              >
                <Download className="w-3.5 h-3.5" />
                Download app
              </span>
            )}
            <PreviewControls
              preview={preview}
              busy={previewBusy}
              currentVersion={project.current_version}
              onStart={startPreviewFromHeader}
              onStop={() => void stopPreview()}
            />
          </div>
        </div>
      </section>

      {notice && <ErrorNote message={notice} onDismiss={() => setNotice(null)} />}

      {/* Run selector */}
      <section className="min-w-0">
        <div className="flex items-center justify-between gap-2 mb-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Runs</h3>
          {runId && runId !== latestRunId && (
            <button onClick={() => onSelectRun(null)} className="text-[11px] text-blue-300 hover:text-blue-200">
              Jump to latest run
            </button>
          )}
        </div>
        {runs.length === 0 ? (
          <p className="text-xs text-slate-500">This project has no runs.</p>
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-1.5 -mx-1 px-1">
            {runs.map((r) => {
              const selected = r.run_id === effectiveRunId;
              const liveStatus = selected && summary?.run_id === r.run_id ? summary.execution_status : r.execution_status;
              return (
                <button
                  key={r.run_id}
                  onClick={() => onSelectRun(r.run_id)}
                  className={cn(
                    'shrink-0 text-left px-3 py-2 rounded-xl border transition-colors min-w-[11rem] max-w-[16rem]',
                    selected ? 'bg-blue-950/40 border-blue-700/80' : 'bg-slate-900/60 border-slate-800 hover:border-slate-700',
                  )}
                  title={r.user_prompt ?? undefined}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-slate-100">Run {runNumber[r.run_id]}</span>
                    <StatusBadge status={liveStatus ?? 'UNKNOWN'} size="xs" />
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 text-[10px] font-mono text-slate-500">
                    <span className="truncate">{r.run_id}</span>
                    {r.is_current && <span className="text-emerald-400 shrink-0">· active</span>}
                    {r.simulated_failure && <span className="text-amber-300 shrink-0">· test</span>}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">{formatDateTime(r.created_at)}</div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {effectiveRunId && (
        <>
          <div className="glass-card rounded-xl px-4 py-2.5 text-xs text-slate-300 flex items-start gap-2">
            <Sparkles className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
            <span className="break-words min-w-0">
              <span className="text-slate-500">Prompt for run {runNumber[effectiveRunId] ?? ''}: </span>
              {summary?.user_prompt || selectedRunEntry?.user_prompt || '--'}
            </span>
          </div>

          {monitor.error && !summary && <ErrorNote title="Could not load run" message={monitor.error} />}
          {monitor.error && summary && (
            <p className="text-[11px] text-amber-300">Live update failed ({monitor.error}); retrying...</p>
          )}

          <MetricsHeader summary={summary} stalled={monitor.stalled} />

          <AgentGrid summary={summary} onOpenArtifact={setArtifactId} onOpenVersions={setRollbackStage} />

          {/* Detail tabs */}
          <section className="min-w-0">
            <div className="flex gap-1 overflow-x-auto border-b border-slate-800 mb-4 -mx-1 px-1">
              {tabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={cn(
                    'shrink-0 inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors',
                    tab === t.id ? 'border-blue-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200',
                  )}
                >
                  {t.icon}
                  {t.label}
                  {t.badge}
                </button>
              ))}
            </div>

            {tab === 'feed' && <MonitoringFeed events={monitor.events} live={monitor.polling} loading={monitor.loading} />}
            {tab === 'qa' && (
              <QAPanel projectId={projectId} runId={effectiveRunId} qaStatus={qaStatus} refreshKey={`${qaStatus}|${statusKey}`} />
            )}
            {tab === 'deploy' && (
              <DeployPanel
                projectId={projectId}
                runId={effectiveRunId}
                deployStatus={deployStatus}
                refreshKey={`${deployStatus}|${statusKey}`}
              />
            )}
            {tab === 'files' && (
              <FilesPanel
                projectId={projectId}
                runId={effectiveRunId}
                hasCurrentVersion={!!project.current_version}
                currentVersion={project.current_version}
                refreshKey={`${summary?.artifact_count}|${statusKey}|${project.current_version}`}
              />
            )}
            {tab === 'versions' && (
              <VersionsPanel
                project={project}
                events={projectEvents}
                eventsLoading={projectEventsLoading}
                selectedRunId={effectiveRunId}
                onSelectRun={(rid) => onSelectRun(rid)}
                onRollback={rollbackProject}
              />
            )}
            {tab === 'preview' && (
              <PreviewPanel
                preview={preview}
                loading={previewLoading}
                busy={previewBusy}
                error={previewError}
                currentVersion={project.current_version}
                onStart={() => void startPreview()}
                onStop={() => void stopPreview()}
                onRefresh={() => void loadPreview()}
                onDismissError={() => setPreviewError(null)}
              />
            )}
          </section>
        </>
      )}

      {!effectiveRunId && (
        <EmptyState title="No runs yet for this project." hint="Start a new iteration to generate the app." />
      )}

      <ArtifactModal artifactId={artifactId} onClose={() => setArtifactId(null)} />

      {rollbackStage && effectiveRunId && (
        <RollbackModal
          projectId={projectId}
          runId={effectiveRunId}
          stage={rollbackStage}
          onClose={() => setRollbackStage(null)}
          onOpenArtifact={(id) => {
            setRollbackStage(null);
            setArtifactId(id);
          }}
          onDone={(res) => {
            setNotice(null);
            monitor.reload();
            void loadProjectEvents();
            if (res.status !== 'COMPLETED') setNotice(res.error_message ?? 'Stage rollback did not complete');
          }}
        />
      )}

      <Modal
        open={iterationOpen}
        onClose={() => setIterationOpen(false)}
        size="lg"
        icon={
          <div className="p-2 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30 shrink-0">
            <Plus className="w-5 h-5" />
          </div>
        }
        title="New iteration"
        subtitle={`${displayName} · builds on ${project.current_version ? `active v${project.current_version}` : 'the project prompt'}`}
      >
        <div className="p-4 sm:p-6">
          <p className="text-xs text-slate-400 mb-4">
            All seven agents run again with your change request. If the run succeeds it becomes the next stable version;
            if it fails, the current version stays active.
          </p>
          <PromptInput
            mode="iteration"
            faultInjectionEnabled={!!system?.fault_injection_enabled}
            onSubmit={startIteration}
            onCancel={() => setIterationOpen(false)}
          />
        </div>
      </Modal>
    </div>
  );
};

