// Types for the FORGE AI platform API (backend/main.py).

export type StageName = 'pm' | 'ui' | 'backend' | 'db' | 'auth' | 'qa' | 'deploy';

export const STAGE_ORDER: StageName[] = ['pm', 'ui', 'backend', 'db', 'auth', 'qa', 'deploy'];

export type AgentStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'RETRYING' | 'SKIPPED';

/** Run-level status. The API may also report 'UNKNOWN' for runs whose summary was never persisted. */
export type ExecutionStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'UNKNOWN';

export type PromotionState = 'pending' | 'promoted' | 'failed' | 'not_applicable';

// ------------------------------------------------------------------ system
export interface LlmInfo {
  llm_enabled: boolean;
  provider: string | null;
  mode: 'llm' | 'deterministic';
  detail: string;
}

export interface SystemInfo {
  llm: LlmInfo;
  frontend_toolchain_ready: boolean;
  node_available: boolean;
  docker_available: boolean;
  workspace: string;
  agents: { name: StageName; spec_file: string }[];
  fault_injection_enabled: boolean;
}

// ------------------------------------------------------------------ projects
export interface ProjectListItem {
  project_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  run_count: number;
  current_version: number | null;
  current_run_id: string | null;
  last_status: ExecutionStatus | null;
}

export interface ProjectVersion {
  version: number;
  run_id: string;
  source: 'run' | 'rollback';
  promoted_at: string;
  reason: string | null;
  restored_from_version: number | null;
}

export interface QaSummary {
  status: string | null;
  tests_run: number | null;
  tests_passed: number | null;
  tests_failed: number | null;
  score: number | null;
  frontend_build: string | null;
  summary: string | null;
}

export interface DeploymentSummary {
  status: string | null;
  deployment_ready: boolean | null;
  docker_available: boolean | null;
}

export interface ProjectRunEntry {
  run_id: string;
  user_prompt: string | null;
  created_at: string | null;
  execution_status: ExecutionStatus | null;
  progress_percent: number | null;
  total_duration_ms: number | null;
  qa_summary: QaSummary | null;
  simulated_failure: StageName | null;
  is_current: boolean;
  stable: boolean;
}

export interface ProjectDetail {
  project_id: string;
  name: string;
  project_name?: string | null;
  initial_prompt: string;
  created_at: string;
  updated_at?: string;
  current_version: number | null;
  current_run_id: string | null;
  versions: ProjectVersion[];
  runs: ProjectRunEntry[];
}

export interface CreateProjectPayload {
  user_prompt: string;
  project_name?: string;
  simulate_failure?: StageName;
}

export interface CreateRunPayload {
  user_prompt: string;
  simulate_failure?: StageName;
}

export interface RunStarted {
  project_id: string;
  run_id: string;
  status?: string;
}

// ------------------------------------------------------------------ runs
export interface AgentEntry {
  title: string;
  status: AgentStatus;
  duration_ms: number | null;
  artifact_id: string | null;
  attempts: number;
  generation_mode: string | null;
  generated_files: number;
  spec_file: string;
  error?: string | null;
}

export interface Promotion {
  state: PromotionState;
  version?: number;
  error?: string;
}

export interface RunSummary {
  project_id: string;
  run_id: string;
  user_prompt: string;
  execution_status: ExecutionStatus;
  current_agent: StageName | null;
  progress_percent: number;
  agent_statuses: Partial<Record<StageName, AgentStatus>>;
  artifact_ids: Partial<Record<StageName, string>>;
  error_reports: Record<string, string>;
  total_duration_ms: number;
  successful_agent_count: number;
  failed_agent_count: number;
  artifact_count: number;
  simulated_failure: StageName | null;
  qa_summary: QaSummary | null;
  deployment_summary: DeploymentSummary | null;
  promotion: Promotion;
  agents: Partial<Record<StageName, AgentEntry>>;
  latest_event_timestamp?: string | null;
}

export type EventType =
  | 'PIPELINE_STARTED'
  | 'PIPELINE_COMPLETED'
  | 'PIPELINE_FAILED'
  | 'AGENT_STARTED'
  | 'AGENT_COMPLETED'
  | 'AGENT_FAILED'
  | 'AGENT_RETRYING'
  | 'AGENT_SKIPPED'
  | 'AGENT_LOG'
  | 'ARTIFACT_CREATED'
  | 'ARTIFACT_FAILED'
  | 'ROLLBACK_STARTED'
  | 'ROLLBACK_COMPLETED'
  | 'ROLLBACK_FAILED'
  | 'VERSION_PROMOTED';

export type EventLevel = 'info' | 'warning' | 'error';

export interface ExecutionEvent {
  event_id: string;
  timestamp: string;
  run_id?: string;
  project_id?: string;
  event_type: EventType;
  agent_name: string | null;
  status: string | null;
  duration_ms: number | null;
  artifact_id: string | null;
  message: string | null;
  error_type: string | null;
  error_message: string | null;
  level: EventLevel | null;
}

// ------------------------------------------------------------------ artifacts
export interface ArtifactMetadata {
  generation_mode?: string | null;
  generated_files?: string[];
  notes?: string | string[] | null;
  attempts?: number;
  spec_file?: string;
  error?: string | null;
  [key: string]: unknown;
}

export interface Artifact {
  artifact_id: string;
  project_id: string;
  run_id: string;
  agent_name: string;
  artifact_type: string;
  version: number;
  created_at: string;
  input_artifacts: string[];
  status: 'COMPLETED' | 'FAILED' | 'PENDING';
  content: Record<string, unknown>;
  metadata: ArtifactMetadata;
}

export interface ArtifactVersion {
  artifact_id: string;
  version: number;
  run_id: string;
  status: string;
  created_at: string;
  is_rollback: boolean;
}

export interface StageRollbackPayload {
  agent_name: StageName;
  target_version: number;
  reason?: string;
  force?: boolean;
}

export interface StageRollbackResult {
  rollback_id: string;
  agent_name: string;
  target_version: number;
  restored_version?: number | null;
  status: 'COMPLETED' | 'FAILED';
  error_message?: string | null;
}

// ------------------------------------------------------------------ files
export interface GeneratedFile {
  path: string;
  bytes: number;
  agent: string | null;
}

export interface FileContent {
  path: string;
  content: string;
}

// ------------------------------------------------------------------ specs
export interface QaCheck {
  name: string;
  category: string;
  status: string;
  duration_ms: number;
  details: string;
}

export interface QaTestSuite {
  name: string;
  test_type?: string;
  tests_count: number;
  passed_count: number;
  failed_count: number;
}

export interface QaTestResult {
  suite: string;
  name: string;
  status: string;
  duration_ms: number;
  message: string | null;
}

export interface QaError {
  id: string;
  type: string;
  severity: string;
  component: string;
  agent: string;
  message: string;
  suggestion: string | null;
  test_name?: string | null;
}

export interface QaReport {
  status: string;
  tests_run: number;
  tests_passed: number;
  tests_failed: number;
  score: number;
  summary: string | null;
  repair_recommendation: string | null;
  frontend_build?: string;
  deployment_ready?: boolean;
  next_step?: string;
  checks: QaCheck[];
  test_suites: QaTestSuite[];
  test_results: QaTestResult[];
  errors: QaError[];
}

export interface HealthCheck {
  endpoint: string;
  status_code: number;
  status: string;
  response_time_ms: number;
  message?: string | null;
}

export interface ReadinessCheck {
  name: string;
  status: string;
  details: string;
}

export interface DeployReport {
  status: string;
  summary?: string | null;
  environment?: string;
  live_url?: string | null;
  deployment_ready: boolean;
  health_checks: HealthCheck[];
  readiness_checks: ReadinessCheck[];
  docker_available: boolean;
  container_build_verified: boolean;
  instructions: string[];
  required_env_vars: string[];
}

// ------------------------------------------------------------------ rollback & preview
export interface ProjectRollbackResult {
  status: string;
  new_version: number;
  restored_from_version: number;
  restored_artifacts: Record<string, string>;
  files_verified: boolean;
  preview_restarted?: boolean;
  preview_error?: string;
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
