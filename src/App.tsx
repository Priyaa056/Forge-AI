import React, { useState, useCallback } from 'react';
import { Navbar } from './components/Navbar';
import { PromptInput } from './components/PromptInput';
import { MetricsHeader } from './components/MetricsHeader';
import { AgentGrid } from './components/AgentGrid';
import { MonitoringFeed } from './components/MonitoringFeed';
import { ArtifactModal } from './components/ArtifactModal';
import { RollbackModal } from './components/RollbackModal';

import { apiService } from './services/api';
import {
  PipelineStatusSummary,
  ArtifactModel,
  ExecutionEventModel,
  StageName,
} from './types';
import { AlertCircle } from 'lucide-react';

export default function App() {
  const [summary, setSummary] = useState<PipelineStatusSummary | null>(null);
  const [events, setEvents] = useState<ExecutionEventModel[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<ArtifactModel | null>(null);
  const [rollbackStage, setRollbackStage] = useState<StageName | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isFeedLoading, setIsFeedLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchRunEvents = useCallback(async (projectId: string, runId: string) => {
    setIsFeedLoading(true);
    try {
      const res = await apiService.getRunEvents(projectId, runId);
      setEvents(res.events || []);
    } catch {
      // Ignore background feed polling errors
    } finally {
      setIsFeedLoading(false);
    }
  }, []);

  const handleStartPipeline = async (prompt: string, projectId?: string) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const newSummary = await apiService.createProjectRun(prompt, projectId);
      setSummary(newSummary);
      if (newSummary.project_id && newSummary.run_id) {
        await fetchRunEvents(newSummary.project_id, newSummary.run_id);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Pipeline execution failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefreshFeed = async () => {
    if (summary?.project_id && summary?.run_id) {
      await fetchRunEvents(summary.project_id, summary.run_id);
    }
  };

  const handleViewArtifact = async (artifactId: string) => {
    try {
      const artifact = await apiService.getArtifactById(artifactId);
      setSelectedArtifact(artifact);
    } catch (err: any) {
      setErrorMessage(`Failed to load artifact: ${err.message}`);
    }
  };

  const handleOpenRollback = (stage: StageName) => {
    setRollbackStage(stage);
  };

  const handleExecuteRollback = async (
    stage: StageName,
    targetVersion: number,
    reason?: string,
    force?: boolean
  ) => {
    if (!summary?.project_id || !summary?.run_id) return;
    await apiService.rollbackRunStage(summary.project_id, summary.run_id, {
      agent_name: stage,
      target_version: targetVersion,
      reason,
      force,
    });

    // Refresh run status and monitoring events after rollback
    const updatedSummary = await apiService.getRunStatus(summary.project_id, summary.run_id);
    setSummary(updatedSummary);
    await fetchRunEvents(summary.project_id, summary.run_id);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-blue-600 selection:text-white">
      <Navbar
        monitoringStatus={summary?.monitoring_status || 'ACTIVE'}
        activeRunId={summary?.run_id}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 pb-16">
        {errorMessage && (
          <div className="mb-6 p-4 rounded-2xl bg-rose-950/80 border border-rose-800 text-rose-200 text-sm flex items-start justify-between gap-3 shadow-lg">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
            <button
              onClick={() => setErrorMessage(null)}
              className="text-xs font-mono text-rose-400 hover:text-rose-200"
            >
              Dismiss
            </button>
          </div>
        )}

        <PromptInput onStartPipeline={handleStartPipeline} isLoading={isLoading} />

        <MetricsHeader summary={summary} />

        <AgentGrid
          summary={summary}
          onViewArtifact={handleViewArtifact}
          onOpenRollback={handleOpenRollback}
        />

        <MonitoringFeed
          events={events}
          onRefresh={handleRefreshFeed}
          isLoading={isFeedLoading}
        />
      </main>

      <ArtifactModal
        artifact={selectedArtifact}
        onClose={() => setSelectedArtifact(null)}
      />

      <RollbackModal
        stage={rollbackStage}
        onClose={() => setRollbackStage(null)}
        onExecuteRollback={handleExecuteRollback}
      />
    </div>
  );
}
