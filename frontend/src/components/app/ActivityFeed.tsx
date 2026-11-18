import { useEffect, useMemo, useRef, useState } from "react";
import { agentByStage } from "@/lib/agents";
import type { ExecutionEvent } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const EVENT_TEXT: Record<string, (e: ExecutionEvent) => string> = {
  PIPELINE_STARTED: () => "Build started",
  PIPELINE_COMPLETED: () => "All seven agents completed",
  PIPELINE_FAILED: (e) => `Build failed: ${e.error_message ?? ""}`,
  AGENT_STARTED: () => "Started",
  AGENT_COMPLETED: () => "Completed",
  AGENT_FAILED: (e) => `Failed: ${e.error_message ?? ""}`,
  AGENT_RETRYING: (e) => `Retrying after error: ${e.error_message ?? ""}`,
  AGENT_SKIPPED: (e) => e.message ?? "Skipped",
  ARTIFACT_CREATED: () => "Artifact saved",
  ARTIFACT_FAILED: () => "Failure report saved",
  VERSION_PROMOTED: (e) => e.message ?? "Version promoted",
};

/** Live log of what each agent is doing (structured events from the orchestrator). */
export function ActivityFeed({ events, live }: { events: ExecutionEvent[]; live: boolean }) {
  const [agent, setAgent] = useState<string>("all");
  const box = useRef<HTMLDivElement>(null);
  const visible = useMemo(
    () =>
      events.filter(
        (e) => e.event_type !== "ARTIFACT_CREATED" && (agent === "all" || e.agent_name === agent),
      ),
    [events, agent],
  );

  // Follow new lines inside the log box only (never scroll the page itself).
  useEffect(() => {
    if (live && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [visible.length, live]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {live ? "Live — updating every second" : `${visible.length} entries`}
        </p>
        <select
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
          className="rounded-lg border bg-background px-2 py-1 text-xs"
          aria-label="Filter activity by agent"
        >
          <option value="all">All agents</option>
          {["pm", "ui", "backend", "db", "auth", "qa", "deploy", "orchestrator"].map((s) => (
            <option key={s} value={s}>
              {agentByStage(s)?.name ?? "Orchestrator"}
            </option>
          ))}
        </select>
      </div>
      <div
        ref={box}
        className="mt-3 max-h-[28rem] overflow-y-auto rounded-xl border bg-background p-3 font-mono text-xs leading-relaxed"
      >
        {visible.length === 0 && <p className="text-muted-foreground">No activity yet.</p>}
        {visible.map((e) => {
          const describe = EVENT_TEXT[e.event_type];
          const text =
            e.event_type === "AGENT_LOG"
              ? (e.message ?? "")
              : describe
                ? describe(e)
                : (e.message ?? e.event_type);
          const tone =
            e.level === "error" || e.event_type.endsWith("FAILED")
              ? "text-destructive"
              : e.level === "warning" ||
                  e.event_type === "AGENT_RETRYING" ||
                  e.event_type === "AGENT_SKIPPED"
                ? "text-warning"
                : e.event_type.endsWith("COMPLETED") || e.event_type === "VERSION_PROMOTED"
                  ? "text-success"
                  : "text-foreground";
          return (
            <div key={e.event_id} className="flex gap-3 py-0.5">
              <span className="shrink-0 text-muted-foreground">
                {new Date(e.timestamp).toLocaleTimeString()}
              </span>
              <span className="w-24 shrink-0 truncate font-semibold text-primary">
                {e.agent_name
                  ? (agentByStage(e.agent_name)?.name.replace(" Agent", "") ?? e.agent_name)
                  : "Pipeline"}
              </span>
              <span className={cn("min-w-0 break-words", tone)}>{text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
