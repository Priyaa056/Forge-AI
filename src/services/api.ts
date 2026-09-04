import {
  PipelineStatusSummary,
  ArtifactModel,
  ExecutionEventModel,
  RollbackResultModel,
  RollbackPayload,
} from '../types';

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetail = `HTTP Error ${response.status}: ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // Ignore JSON parse failure on error body
    }
    throw new Error(errorDetail);
  }
  return response.json();
}

export const apiService = {
  /**
   * Initialize and execute a new ForgePipeline project run (POST /api/projects).
   */
  async createProjectRun(
    userPrompt: string,
    projectId?: string,
    outputDir: string = 'outputs'
  ): Promise<PipelineStatusSummary> {
    const res = await fetch(`${API_BASE}/api/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_prompt: userPrompt,
        project_id: projectId || undefined,
        output_dir: outputDir,
        run_immediately: true,
      }),
    });
    return handleResponse<PipelineStatusSummary>(res);
  },

  /**
   * Fetch current pipeline status summary (GET /api/projects/{project_id}/runs/{run_id}).
   */
  async getRunStatus(projectId: string, runId: string): Promise<PipelineStatusSummary> {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/runs/${runId}`);
    return handleResponse<PipelineStatusSummary>(res);
  },

  /**
   * Fetch all artifacts created for a run (GET /api/projects/{project_id}/runs/{run_id}/artifacts).
   */
  async getRunArtifacts(
    projectId: string,
    runId: string
  ): Promise<{ project_id: string; run_id: string; count: number; artifacts: ArtifactModel[] }> {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/runs/${runId}/artifacts`);
    return handleResponse(res);
  },

  /**
   * Retrieve a specific artifact by artifact_id (GET /api/artifacts/{artifact_id}).
   */
  async getArtifactById(artifactId: string): Promise<ArtifactModel> {
    const res = await fetch(`${API_BASE}/api/artifacts/${artifactId}`);
    return handleResponse<ArtifactModel>(res);
  },

  /**
   * Fetch monitoring events for a run (GET /api/projects/{project_id}/runs/{run_id}/events).
   */
  async getRunEvents(
    projectId: string,
    runId: string
  ): Promise<{ project_id: string; run_id: string; count: number; events: ExecutionEventModel[] }> {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/runs/${runId}/events`);
    return handleResponse(res);
  },

  /**
   * Trigger stage rollback (POST /api/projects/{project_id}/runs/{run_id}/rollback).
   */
  async rollbackRunStage(
    projectId: string,
    runId: string,
    payload: RollbackPayload
  ): Promise<RollbackResultModel> {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/runs/${runId}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<RollbackResultModel>(res);
  },
};
