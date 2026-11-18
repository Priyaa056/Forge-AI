import {
  Artifact,
  ArtifactVersion,
  CreateProjectPayload,
  CreateRunPayload,
  DeployReport,
  ExecutionEvent,
  FileContent,
  GeneratedFile,
  ProjectDetail,
  ProjectListItem,
  ProjectRollbackResult,
  PreviewStatus,
  QaReport,
  RunStarted,
  RunSummary,
  StageName,
  StageRollbackPayload,
  StageRollbackResult,
  SystemInfo,
} from '../types';

/** Base URL of the FORGE AI platform API. Empty = same origin (the Vite dev proxy forwards /api). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) || '';

/** Error raised for any failed API call. `network` is true when the platform API could not be reached. */
export class ApiError extends Error {
  status: number;
  network: boolean;

  constructor(message: string, status: number, network = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.network = network;
  }
}

export function errorMessage(err: unknown, fallback = 'Unexpected error'): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function isNetworkError(err: unknown): boolean {
  return err instanceof ApiError && err.network;
}

function detailToString(detail: unknown): string | null {
  if (typeof detail === 'string') return detail;
  // FastAPI validation errors: [{loc, msg, type}]
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : null))
      .filter(Boolean);
    if (parts.length) return parts.join('; ');
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
    });
  } catch {
    throw new ApiError('Cannot reach the FORGE AI platform API.', 0, true);
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body ? detailToString((body as { detail: unknown }).detail) : null;
    if (detail) throw new ApiError(detail, response.status);
    // A 5xx without a JSON body usually comes from the dev proxy when the API process is down.
    const proxyDown = response.status >= 500 && body === null;
    throw new ApiError(
      proxyDown ? 'Cannot reach the FORGE AI platform API.' : `HTTP ${response.status} ${response.statusText}`.trim(),
      response.status,
      proxyDown,
    );
  }
  if (body === null && text) {
    throw new ApiError('The platform API returned an unexpected (non-JSON) response.', response.status);
  }
  return body as T;
}

const post = <T>(path: string, payload?: unknown) =>
  request<T>(path, { method: 'POST', body: payload === undefined ? undefined : JSON.stringify(payload) });

const enc = encodeURIComponent;

/** Fill defaults so that persisted / partial run summaries never break the UI. */
function normalizeRunSummary(raw: Partial<RunSummary> & { project_id: string; run_id: string }): RunSummary {
  return {
    user_prompt: '',
    execution_status: 'UNKNOWN',
    current_agent: null,
    progress_percent: 0,
    agent_statuses: {},
    artifact_ids: {},
    error_reports: {},
    total_duration_ms: 0,
    successful_agent_count: 0,
    failed_agent_count: 0,
    artifact_count: 0,
    simulated_failure: null,
    qa_summary: null,
    deployment_summary: null,
    agents: {},
    ...raw,
    promotion: raw.promotion ?? { state: 'not_applicable' },
  } as RunSummary;
}

export const api = {
  // system
  getSystem: () => request<SystemInfo>('/api/system'),

  // projects
  listProjects: () => request<{ projects: ProjectListItem[] }>('/api/projects').then((r) => r.projects ?? []),
  getProject: (pid: string) =>
    request<ProjectDetail>(`/api/projects/${enc(pid)}`).then((p) => ({
      ...p,
      versions: p.versions ?? [],
      runs: p.runs ?? [],
    })),
  createProject: (payload: CreateProjectPayload) => post<RunStarted>('/api/projects', payload),
  createRun: (pid: string, payload: CreateRunPayload) => post<RunStarted>(`/api/projects/${enc(pid)}/runs`, payload),
  getProjectEvents: (pid: string, limit = 500) =>
    request<{ events: ExecutionEvent[] }>(`/api/projects/${enc(pid)}/events?limit=${limit}`).then((r) => r.events ?? []),

  // runs
  getRun: (pid: string, rid: string) =>
    request<RunSummary>(`/api/projects/${enc(pid)}/runs/${enc(rid)}`).then((r) =>
      normalizeRunSummary({ ...r, project_id: r.project_id ?? pid, run_id: r.run_id ?? rid }),
    ),
  getRunEvents: (pid: string, rid: string, after?: string | null) =>
    request<{ events: ExecutionEvent[] }>(
      `/api/projects/${enc(pid)}/runs/${enc(rid)}/events${after ? `?after=${enc(after)}` : ''}`,
    ).then((r) => r.events ?? []),

  // artifacts
  getArtifact: (artifactId: string) => request<Artifact>(`/api/artifacts/${enc(artifactId)}`),
  getArtifactVersions: (pid: string, agent: StageName) =>
    request<{ versions: ArtifactVersion[] }>(`/api/projects/${enc(pid)}/artifacts/${enc(agent)}/versions`).then(
      (r) => r.versions ?? [],
    ),

  // files & specs
  listFiles: (pid: string, rid: string) =>
    request<{ files: GeneratedFile[] }>(`/api/projects/${enc(pid)}/runs/${enc(rid)}/files`).then((r) => r.files ?? []),
  getFileContent: (pid: string, rid: string, path: string) =>
    request<FileContent>(`/api/projects/${enc(pid)}/runs/${enc(rid)}/files/content?path=${enc(path)}`),
  downloadUrl: (pid: string, rid: string) => `${API_BASE}/api/projects/${enc(pid)}/runs/${enc(rid)}/download`,
  getQaReport: (pid: string, rid: string) => request<QaReport>(`/api/projects/${enc(pid)}/runs/${enc(rid)}/specs/qa`),
  getDeployReport: (pid: string, rid: string) =>
    request<DeployReport>(`/api/projects/${enc(pid)}/runs/${enc(rid)}/specs/deploy`),

  // rollback
  rollbackProject: (pid: string, target_run_id: string, reason?: string) =>
    post<ProjectRollbackResult>(`/api/projects/${enc(pid)}/rollback`, { target_run_id, reason: reason || undefined }),
  rollbackStage: (pid: string, rid: string, payload: StageRollbackPayload) =>
    post<StageRollbackResult>(`/api/projects/${enc(pid)}/runs/${enc(rid)}/rollback`, payload),

  // preview
  getPreview: (pid: string) => request<PreviewStatus>(`/api/projects/${enc(pid)}/preview`),
  startPreview: (pid: string) => post<PreviewStatus>(`/api/projects/${enc(pid)}/preview/start`),
  stopPreview: (pid: string) => post<PreviewStatus>(`/api/projects/${enc(pid)}/preview/stop`),
};
