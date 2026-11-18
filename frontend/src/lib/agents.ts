// The seven FORGE AI agents, with the same names and icons the landing page uses.
import {
  ClipboardList,
  Database,
  FlaskConical,
  Palette,
  Rocket,
  Server,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import type { AgentStatus, StageName } from "./api/types";

export type AgentMeta = { stage: StageName; name: string; does: string; icon: LucideIcon };

export const AGENTS: AgentMeta[] = [
  { stage: "pm", name: "PM Agent", does: "Turns your idea into a spec", icon: ClipboardList },
  { stage: "ui", name: "UI Agent", does: "Designs every screen", icon: Palette },
  { stage: "backend", name: "Backend Agent", does: "Writes the APIs", icon: Server },
  { stage: "db", name: "Database Agent", does: "Models your data", icon: Database },
  { stage: "auth", name: "Auth Agent", does: "Secures user access", icon: ShieldCheck },
  { stage: "qa", name: "QA Agent", does: "Tests what was built", icon: FlaskConical },
  {
    stage: "deploy",
    name: "Deploy Agent",
    does: "Prepares & health-checks the release",
    icon: Rocket,
  },
];

export const agentByStage = (stage: string): AgentMeta | undefined =>
  AGENTS.find((a) => a.stage === stage);

/** Status dot colours, following the hero mock (success / pulsing primary / muted). */
export const STATUS_DOT: Record<AgentStatus, string> = {
  PENDING: "bg-muted-foreground/30",
  RUNNING: "bg-primary animate-pulse",
  RETRYING: "bg-warning animate-pulse",
  COMPLETED: "bg-success",
  FAILED: "bg-destructive",
  SKIPPED: "bg-muted-foreground/15",
};

export const STATUS_LABEL: Record<AgentStatus, string> = {
  PENDING: "Waiting",
  RUNNING: "Working",
  RETRYING: "Retrying",
  COMPLETED: "Done",
  FAILED: "Failed",
  SKIPPED: "Skipped",
};

export const MODE_LABEL: Record<string, string> = {
  llm: "LLM",
  deterministic: "Rule-based",
  deterministic_fallback: "Rule-based (LLM fallback)",
  execution: "Executed",
  custom_handler: "Custom",
};

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
