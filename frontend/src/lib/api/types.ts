// Response shapes of the FORGE AI platform API (backend/main.py).

export type StageName = "pm" | "ui" | "backend" | "db" | "auth" | "qa" | "deploy";
export type AgentStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "RETRYING" | "SKIPPED";
export type RunStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface Session {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface SystemInfo {
  llm: {
    llm_enabled: boolean;
    provider: string | null;
    mode: "llm" | "deterministic";
    detail: string;
  };
  frontend_toolchain_ready: boolean;
  node_available: boolean;
  docker_available: boolean;
  agents: { name: StageName; spec_file: string }[];
  fault_injection_enabled: boolean;
}

export interface ProjectListItem {
  project_id: string;
  name: string;
  initial_prompt: string | null;
  created_at: string;
  updated_at: string;
  run_count: number;
  current_version: number | null;
  current_run_id: string | null;
  last_status: RunStatus | null;
  /** The latest build: per-agent status (7 agents), QA tests, duration. */
  last_run?: {
    run_id: string | null;
    mode: "build" | "refine";
    duration_ms: number | null;
    agents: Partial<Record<StageName, { status: AgentStatus | null; reused: boolean }>>;
    qa: { passed: number | null; run: number | null } | null;
  } | null;
  refinements?: number;
  /** The generated app's primary colour (#rrggbb). */
  theme_color?: string | null;
  modules?: string[];
}

/** GET /api/stats: analytics for the signed-in user. */
export interface DashboardStats {
  days: number;
  projects: number;
  live_apps: number;
  builds: number;
  succeeded: number;
  failed: number;
  running: number;
  refinements: number;
  success_rate: number | null;
  avg_build_ms: number | null;
  tests_passed: number;
  tests_run: number;
  agent_avg_ms: Partial<Record<StageName, number | null>>;
  builds_change_pct: number | null;
  success_rate_change: number | null;
  daily: {
    date: string;
    builds: number;
    succeeded: number;
    failed: number;
    success_rate: number | null;
    avg_build_ms: number | null;
    tests_passed: number;
  }[];
}

export interface QASummary {
  status: string | null;
  tests_run: number | null;
  tests_passed: number | null;
  tests_failed: number | null;
  score: number | null;
  frontend_build: string | null;
  summary: string | null;
  regression?: RegressionReport | null;
}

/** Refinements: what passed in the refined version, re-checked. */
export interface RegressionReport {
  base_version: number | null;
  requirements_checked: number;
  requirements_still_met: number;
  requirements_retired: number;
  tests_checked: number;
  tests_still_passing: number;
  tests_retired: number;
  failures: string[];
}

export interface ChangeItem {
  action: "added" | "removed" | "modified" | "renamed" | string;
  area: string;
  target: string;
  detail: string;
  agents: string[];
}

export interface AgentImpact {
  agent: StageName;
  action: "plan" | "update" | "reuse" | "validate" | "package" | string;
  reasons: string[];
}

/** The PM agent's plan for a refinement. */
export interface ChangePlan {
  change_request: string;
  base_run_id: string | null;
  base_version: number | null;
  summary: string;
  applied: string[];
  changes: ChangeItem[];
  agents: AgentImpact[];
  preserved: Record<string, number>;
  unresolved: string[];
  notes: string[];
}

export interface FileChanges {
  added: string[];
  modified: string[];
  removed: string[];
  counts: { added: number; modified: number; removed: number; unchanged: number };
  by_agent: Record<string, { added: number; modified: number; removed: number }>;
}

export interface RefinementSummary {
  base_run_id: string | null;
  base_version: number | null;
  change_request: string;
  plan_summary: string | null;
  /** Actual actions: plan | update | reused | "update (impact check)" | validate | package */
  agent_actions: Record<string, string>;
  escalated: { agent: string; files: string[] }[];
  files: FileChanges | null;
}

export interface RunChanges {
  project_id: string;
  run_id: string;
  execution_status: RunStatus;
  base_run_id: string | null;
  base_version: number | null;
  change_request: string;
  plan: ChangePlan | null;
  agent_actions: Record<string, string>;
  escalated: { agent: string; files: string[] }[];
  files: FileChanges | null;
  regression: RegressionReport | null;
  promotion?: RunSummary["promotion"];
  error_reports: Partial<Record<string, string>>;
}

/** A refinement planned but not applied yet (POST /refine/preview). */
export interface RefinePreview {
  applicable: boolean;
  /** Why nothing can be applied (when applicable is false). */
  message: string | null;
  draft_id: string | null;
  base_run_id: string;
  base_version: number;
  change_request: string;
  plan: ChangePlan | null;
  generation_mode?: string;
  /** Data the change would delete or invalidate in a deployed database. */
  warnings: string[];
  migration: { file: string; sql: string } | null;
  /** Code changes from the PM, UI, Backend, Database and Auth agents, computed in a scratch copy. */
  files: FileChanges | null;
  notes: string[];
  expires_at?: string;
}

export interface RunListItem {
  run_id: string;
  user_prompt: string | null;
  created_at: string | null;
  execution_status: RunStatus;
  progress_percent: number | null;
  total_duration_ms: number | null;
  qa_summary: QASummary | null;
  simulated_failure: StageName | null;
  is_current: boolean;
  stable: boolean;
  /** "refine" for iterative refinements of a live version. */
  mode?: "build" | "refine";
  base_version?: number | null;
}

export interface VersionEntry {
  version: number;
  run_id: string;
  source: "run" | "rollback";
  promoted_at: string;
  reason: string | null;
  restored_from_version: number | null;
}

export interface ProjectDetail {
  project_id: string;
  name: string;
  project_name?: string;
  initial_prompt: string;
  created_at: string;
  updated_at: string;
  current_version: number | null;
  current_run_id: string | null;
  versions: VersionEntry[];
  runs: RunListItem[];
  /** The GitHub repository this project was last pushed to. */
  github?: GitHubLink;
}

export interface GitHubLink {
  full_name: string;
  html_url: string;
  branch: string;
  last_commit: string;
  commit_url: string;
  pushed_version: number | null;
  pushed_at: string;
}

export interface GitHubPushRequest {
  /** Used for this push only; the platform never stores it. */
  token: string;
  mode: "new" | "existing";
  /** New repository name (mode "new"). */
  name?: string;
  /** "owner/name" of an existing repository (mode "existing"). */
  repository?: string;
  private?: boolean;
  branch?: string;
  message?: string;
}

export interface GitHubPushResult {
  pushed: boolean;
  /** False when GitHub already had exactly these files (no commit was made). */
  changed: boolean;
  created_repository: boolean;
  full_name: string;
  html_url: string;
  branch: string;
  commit_sha: string;
  commit_url: string;
  files: number;
  removed: string[];
  github: GitHubLink;
}

export interface AgentSummary {
  title: string;
  status: AgentStatus;
  duration_ms: number | null;
  artifact_id: string | null;
  attempts: number;
  generation_mode: string | null;
  generated_files: number;
  spec_file: string;
  error?: string;
  /** Set when a refinement reused this agent's output from an earlier version. */
  reused_from_version?: number;
}

export interface RunSummary {
  project_id: string;
  run_id: string;
  user_prompt: string;
  execution_status: RunStatus;
  current_agent: StageName | null;
  progress_percent: number;
  agent_statuses: Record<StageName, AgentStatus>;
  artifact_ids: Partial<Record<StageName, string>>;
  error_reports: Partial<Record<string, string>>;
  total_duration_ms: number;
  successful_agent_count: number;
  failed_agent_count: number;
  artifact_count: number;
  simulated_failure: StageName | null;
  qa_summary: QASummary | null;
  deployment_summary: {
    status: string;
    deployment_ready: boolean;
    docker_available: boolean;
  } | null;
  promotion?: {
    state: "pending" | "promoted" | "failed" | "not_applicable";
    version?: number;
    error?: string;
  };
  agents: Record<StageName, AgentSummary>;
  mode?: "build" | "refine";
  refinement?: RefinementSummary | null;
}

export interface ExecutionEvent {
  event_id: string;
  timestamp: string;
  run_id: string;
  project_id: string;
  event_type: string;
  agent_name: string | null;
  status: string | null;
  duration_ms: number | null;
  artifact_id: string | null;
  message: string | null;
  error_type: string | null;
  error_message: string | null;
  level: string | null;
}

export interface Artifact {
  artifact_id: string;
  project_id: string;
  run_id: string;
  agent_name: StageName;
  artifact_type: string;
  version: number;
  created_at: string;
  input_artifacts: string[];
  status: "COMPLETED" | "FAILED" | "PENDING";
  content: Record<string, unknown>;
  metadata: {
    generation_mode?: string;
    generated_files?: string[];
    notes?: string[];
    attempts?: number;
    spec_file?: string;
    error?: string;
    is_rollback?: boolean;
  };
}

export interface FileEntry {
  path: string;
  bytes: number;
  agent: StageName | null;
}

export interface PreviewStatus {
  running: boolean;
  url: string | null;
  version: number | null;
  current_version: number | null;
  stale: boolean;
  admin_email: string;
  admin_password: string;
  log_tail: string;
  message: string | null;
}

export interface QACheck {
  name: string;
  category: string;
  status: "passed" | "failed" | "skipped";
  duration_ms: number;
  details: string;
}

export interface QAReport {
  status: "passed" | "failed";
  tests_run: number;
  tests_passed: number;
  tests_failed: number;
  score: number;
  checks: QACheck[];
  test_suites: { name: string; tests_count: number; passed_count: number; failed_count: number }[];
  test_results: {
    suite: string;
    name: string;
    status: string;
    duration_ms: number;
    message: string | null;
  }[];
  errors: {
    id: string;
    type: string;
    severity: string;
    component: string;
    agent: string;
    message: string;
    suggestion: string | null;
  }[];
  frontend_build: string;
  summary: string | null;
  repair_recommendation: string | null;
}

export interface DeployReport {
  status: "success" | "failed";
  deployment_ready: boolean;
  docker_available: boolean;
  container_build_verified: boolean;
  health_checks: {
    endpoint: string;
    status_code: number;
    status: string;
    response_time_ms: number;
  }[];
  readiness_checks: { name: string; status: "passed" | "failed" | "skipped"; details: string }[];
  instructions: string[];
  required_env_vars: string[];
  summary: string | null;
}

export interface RollbackResult {
  status: string;
  new_version: number;
  restored_from_version: number;
  files_verified: boolean;
  preview_restarted?: boolean;
  preview_error?: string;
}
