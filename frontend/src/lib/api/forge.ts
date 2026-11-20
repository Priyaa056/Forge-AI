// Typed endpoint functions for the FORGE AI platform API. UI components call these, never fetch directly.
import { downloadFile, request } from "./client";
import type {
  Artifact,
  DeployReport,
  ExecutionEvent,
  FileEntry,
  GitHubPushRequest,
  GitHubPushResult,
  PreviewStatus,
  ProjectDetail,
  ProjectListItem,
  QAReport,
  RollbackResult,
  RunSummary,
  Session,
  StageName,
  SystemInfo,
  User,
} from "./types";

const enc = encodeURIComponent;

export const forgeApi = {
  // Accounts
  register: (email: string, password: string) =>
    request<Session>("/api/auth/register", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),
  login: (email: string, password: string) =>
    request<Session>("/api/auth/login", { method: "POST", body: { email, password }, auth: false }),
  me: () => request<User>("/api/auth/me"),

  // Platform
  system: () => request<SystemInfo>("/api/system", { auth: false }),

  // Projects & runs
  listProjects: () =>
    request<{ projects: ProjectListItem[] }>("/api/projects").then((r) => r.projects),
  getProject: (projectId: string) => request<ProjectDetail>(`/api/projects/${enc(projectId)}`),
  createProject: (prompt: string, projectName?: string, simulateFailure?: StageName) =>
    request<{ project_id: string; run_id: string }>("/api/projects", {
      method: "POST",
      body: {
        user_prompt: prompt,
        ...(projectName ? { project_name: projectName } : {}),
        ...(simulateFailure ? { simulate_failure: simulateFailure } : {}),
      },
    }),
  /** Permanently deletes a project with its builds, versions, files, artifacts and preview. */
  deleteProject: (projectId: string) =>
    request<{ deleted: boolean; project_id: string; name?: string }>(
      `/api/projects/${enc(projectId)}`,
      {
        method: "DELETE",
      },
    ),
  createRun: (projectId: string, prompt: string, simulateFailure?: StageName) =>
    request<{ project_id: string; run_id: string }>(`/api/projects/${enc(projectId)}/runs`, {
      method: "POST",
      body: {
        user_prompt: prompt,
        ...(simulateFailure ? { simulate_failure: simulateFailure } : {}),
      },
    }),
  getRun: (projectId: string, runId: string) =>
    request<RunSummary>(`/api/projects/${enc(projectId)}/runs/${enc(runId)}`),
  getRunEvents: (projectId: string, runId: string) =>
    request<{ events: ExecutionEvent[] }>(
      `/api/projects/${enc(projectId)}/runs/${enc(runId)}/events`,
    ).then((r) => r.events),
  getProjectEvents: (projectId: string) =>
    request<{ events: ExecutionEvent[] }>(`/api/projects/${enc(projectId)}/events`).then(
      (r) => r.events,
    ),

  // Artifacts & reports
  getArtifact: (artifactId: string) => request<Artifact>(`/api/artifacts/${enc(artifactId)}`),
  getQAReport: (projectId: string, runId: string) =>
    request<QAReport>(`/api/projects/${enc(projectId)}/runs/${enc(runId)}/specs/qa`),
  getDeployReport: (projectId: string, runId: string) =>
    request<DeployReport>(`/api/projects/${enc(projectId)}/runs/${enc(runId)}/specs/deploy`),

  // Generated files ("current" = the active stable version)
  listFiles: (projectId: string, runId: string) =>
    request<{ files: FileEntry[] }>(
      `/api/projects/${enc(projectId)}/runs/${enc(runId)}/files`,
    ).then((r) => r.files),
  readFile: (projectId: string, runId: string, path: string) =>
    request<{ path: string; content: string }>(
      `/api/projects/${enc(projectId)}/runs/${enc(runId)}/files/content?path=${enc(path)}`,
    ),
  downloadZip: (projectId: string, runId: string) =>
    downloadFile(
      `/api/projects/${enc(projectId)}/runs/${enc(runId)}/download`,
      `${projectId}-${runId}.zip`,
    ),

  /** Pushes the live version to GitHub as one commit. The token is sent for this request only. */
  pushToGitHub: (projectId: string, body: GitHubPushRequest) =>
    request<GitHubPushResult>(`/api/projects/${enc(projectId)}/github/push`, {
      method: "POST",
      body,
    }),

  // Versions
  rollback: (projectId: string, targetRunId: string, reason?: string) =>
    request<RollbackResult>(`/api/projects/${enc(projectId)}/rollback`, {
      method: "POST",
      body: { target_run_id: targetRunId, ...(reason ? { reason } : {}) },
    }),

  // Live preview of the generated application
  previewStatus: (projectId: string) =>
    request<PreviewStatus>(`/api/projects/${enc(projectId)}/preview`),
  startPreview: (projectId: string) =>
    request<PreviewStatus>(`/api/projects/${enc(projectId)}/preview/start`, { method: "POST" }),
  stopPreview: (projectId: string) =>
    request<PreviewStatus>(`/api/projects/${enc(projectId)}/preview/stop`, { method: "POST" }),
};
