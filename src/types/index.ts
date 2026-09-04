export type AgentStatusType = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'RETRYING';

export type StageName = 'pm' | 'ui' | 'backend' | 'db' | 'auth' | 'qa' | 'deploy';

export interface AgentSummaryEntry {
  status: AgentStatusType;
  duration_ms: number | null;
  artifact_id: string | null;
  error?: string | null;
}

export interface PipelineStatusSummary {
  project_id: string;
  run_id: string;
  user_prompt: string;
  execution_status: AgentStatusType;
  current_agent: StageName | null;
  agent_statuses: Record<StageName, AgentStatusType>;
  artifact_ids: Record<string, string>;
  error_reports: Record<string, string>;
  completed_stages: string[];
  output_directory: string;
  total_duration_ms: number;
  successful_agent_count: number;
  failed_agent_count: number;
  artifact_count: number;
  failed_artifact_count: number;
  latest_event_type: string | null;
  latest_event_timestamp: string | null;
  monitoring_status: string;
  agents: Record<string, AgentSummaryEntry>;
}

export interface ArtifactModel {
  artifact_id: string;
  project_id: string;
  run_id: string;
  agent_name: string;
  artifact_type: string;
  version: number;
  created_at: string;
  input_artifacts: string[];
  status: 'PENDING' | 'COMPLETED' | 'FAILED';
  content: Record<string, any>;
  metadata: Record<string, any>;
}

export interface ExecutionEventModel {
  event_id: string;
  timestamp: string;
  run_id: string;
  project_id: string;
  event_type: string;
  agent_name?: string | null;
  pipeline_stage?: string | null;
  status?: string | null;
  duration_ms?: number | null;
  artifact_id?: string | null;
  input_artifact_ids?: string[] | null;
  message?: string | null;
  error_type?: string | null;
  error_message?: string | null;
}

export interface RollbackResultModel {
  rollback_id: string;
  project_id: string;
  run_id: string;
  agent_name: string;
  source_artifact_id?: string | null;
  source_version?: number | null;
  target_artifact_id: string;
  target_version: number;
  restored_artifact_id?: string | null;
  restored_version?: number | null;
  status: 'COMPLETED' | 'FAILED';
  timestamp: string;
  reason?: string | null;
  error_message?: string | null;
}

export interface ProjectCreatePayload {
  user_prompt: string;
  project_id?: string;
  output_dir?: string;
  run_immediately?: boolean;
}

export interface RollbackPayload {
  agent_name: string;
  target_version: number;
  reason?: string;
  force?: boolean;
}
