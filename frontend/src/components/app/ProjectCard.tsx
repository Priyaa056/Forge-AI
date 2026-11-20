// A project on the dashboard: app icon in the app's own colour, live version, modules,
// the last build's seven agents at a glance, QA result and activity.
import { Link } from "@tanstack/react-router";
import { Clock, FlaskConical, Layers, Wand2 } from "lucide-react";
import { AGENTS, formatDuration, formatWhen } from "@/lib/agents";
import type { ProjectListItem } from "@/lib/api/types";
import { projectColor } from "@/lib/projects";
import { cn } from "@/lib/utils";
import { ProjectIcon } from "./AppShell";
import { ProjectActionsMenu } from "./DeleteProject";
import { RunStatusPill } from "./ui";

const SEGMENT: Record<string, { cls: string; label: string }> = {
  COMPLETED: { cls: "bg-success", label: "done" },
  REUSED: { cls: "bg-success/35", label: "reused (unchanged)" },
  FAILED: { cls: "bg-destructive", label: "failed" },
  RUNNING: { cls: "bg-primary animate-pulse", label: "working" },
  RETRYING: { cls: "bg-warning animate-pulse", label: "retrying" },
  SKIPPED: { cls: "bg-muted-foreground/20", label: "skipped" },
  PENDING: { cls: "bg-muted", label: "waiting" },
};

export function ProjectCard({
  project: p,
  onDelete,
}: {
  project: ProjectListItem;
  onDelete: () => void;
}) {
  const color = projectColor(p.theme_color, p.project_id);
  const modules = p.modules ?? [];
  const run = p.last_run;
  const qa = run?.qa;
  const allPassed = qa?.run ? qa.passed === qa.run : false;
  const segments = AGENTS.map((agent) => {
    const info = run?.agents?.[agent.stage];
    const key = info?.reused ? "REUSED" : (info?.status ?? "PENDING");
    return { agent, ...(SEGMENT[key] ?? SEGMENT["PENDING"]!) };
  });

  return (
    <div className="relative min-w-0 transition hover:-translate-y-1">
      <Link
        to="/app/projects/$projectId"
        params={{ projectId: p.project_id }}
        className="group relative block h-full overflow-hidden rounded-2xl border bg-card p-5 shadow-soft transition hover:border-primary"
      >
        <span aria-hidden className="absolute inset-x-0 top-0 h-1" style={{ background: color }} />
        <div className="flex items-start gap-3 pr-9">
          <ProjectIcon project={p} />
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-base font-semibold group-hover:text-primary">{p.name}</h3>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
              {p.current_version ? (
                <span className="font-semibold text-success">v{p.current_version} live</span>
              ) : (
                <span>No live version yet</span>
              )}
              {(p.refinements ?? 0) > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Wand2 className="size-3" /> {p.refinements} refinement
                  {p.refinements === 1 ? "" : "s"}
                </span>
              )}
            </p>
          </div>
          <RunStatusPill status={p.last_status} className="shrink-0" />
        </div>

        {p.initial_prompt && (
          <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">{p.initial_prompt}</p>
        )}

        {modules.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Modules">
            {modules.slice(0, 4).map((m) => (
              <li key={m} className="rounded-md border bg-background px-2 py-0.5 text-xs">
                {m}
              </li>
            ))}
            {modules.length > 4 && (
              <li className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                +{modules.length - 4}
              </li>
            )}
          </ul>
        )}

        {run && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-[11px] font-medium text-muted-foreground">
              <span>
                Last {run.mode === "refine" ? "refinement" : "build"}
                {run.duration_ms ? ` · ${formatDuration(run.duration_ms)}` : ""}
              </span>
              <span>7 agents</span>
            </div>
            <div
              className="mt-1.5 flex gap-1"
              role="img"
              aria-label={`Last build: ${segments.map((s) => `${s.agent.name} ${s.label}`).join(", ")}`}
            >
              {segments.map((s) => (
                <span
                  key={s.agent.stage}
                  title={`${s.agent.name}: ${s.label}`}
                  className={cn("h-1.5 flex-1 rounded-full", s.cls)}
                />
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t pt-3 text-xs text-muted-foreground">
          {qa?.run ? (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold",
                allPassed ? "bg-success/12 text-success" : "bg-warning/15 text-foreground",
              )}
            >
              <FlaskConical className="size-3" /> {qa.passed}/{qa.run} tests
            </span>
          ) : null}
          <span className="inline-flex items-center gap-1">
            <Layers className="size-3" /> {p.run_count} build{p.run_count === 1 ? "" : "s"}
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3" /> Updated {formatWhen(p.updated_at)}
          </span>
        </div>
      </Link>
      <ProjectActionsMenu
        projectName={p.name}
        onDelete={onDelete}
        className="absolute right-4 top-5"
      />
    </div>
  );
}
