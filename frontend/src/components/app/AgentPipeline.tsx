import { ChevronRight, RotateCcw } from "lucide-react";
import { AGENTS, MODE_LABEL, STATUS_LABEL, formatDuration } from "@/lib/agents";
import type { RunSummary, StageName } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { StatusDot } from "./ui";

/** The seven agents in pipeline order, styled like the agent list in the landing hero. */
export function AgentPipeline({
  summary,
  onSelect,
}: {
  summary: RunSummary | undefined;
  onSelect: (stage: StageName) => void;
}) {
  return (
    <ol className="space-y-2">
      {AGENTS.map((agent, index) => {
        const info = summary?.agents[agent.stage];
        const status = info?.status ?? "PENDING";
        const clickable = Boolean(info?.artifact_id);
        return (
          <li key={agent.stage}>
            <button
              type="button"
              disabled={!clickable}
              onClick={() => onSelect(agent.stage)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg border bg-background px-3 py-2.5 text-left text-sm transition",
                clickable && "hover:border-primary",
                status === "RUNNING" && "border-primary",
                status === "FAILED" && "border-destructive/60",
                status === "SKIPPED" && "opacity-60",
              )}
              aria-label={`${agent.name}: ${STATUS_LABEL[status]}${clickable ? " — open artifact" : ""}`}
            >
              <span className="w-5 text-xs font-semibold text-muted-foreground">0{index + 1}</span>
              <agent.icon className="size-4 shrink-0 text-primary" />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{agent.name}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {info?.error ? info.error : agent.does}
                </span>
              </span>
              <span className="hidden flex-col items-end text-xs text-muted-foreground sm:flex">
                <span>
                  {STATUS_LABEL[status]}
                  {status === "RUNNING" || status === "COMPLETED" || status === "FAILED"
                    ? ` · ${formatDuration(info?.duration_ms)}`
                    : ""}
                </span>
                <span className="flex items-center gap-1">
                  {info?.generation_mode
                    ? (MODE_LABEL[info.generation_mode] ?? info.generation_mode)
                    : ""}
                  {(info?.attempts ?? 0) > 1 && (
                    <span className="inline-flex items-center gap-0.5 text-warning">
                      <RotateCcw className="size-3" />
                      {info?.attempts}
                    </span>
                  )}
                </span>
              </span>
              <StatusDot status={status} />
              {clickable && <ChevronRight className="size-4 text-muted-foreground" />}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
