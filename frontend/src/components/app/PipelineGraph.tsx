// The seven agents as a connected graph (PM → UI → … → Deploy) that follows a build live:
// the working agent pulses, packets flow along the line into it, agents a refinement reused
// unchanged are drawn dashed, and every node shows how long its agent took.
import { Fragment, useEffect, useRef, useState } from "react";
import { Check, ChevronRight, Repeat2, RotateCcw, X } from "lucide-react";
import { AGENTS, formatDuration } from "@/lib/agents";
import type { AgentSummary, RunSummary, StageName } from "@/lib/api/types";
import { type EdgeState, type NodeState, edgeInto, nodeState } from "@/lib/pipelineGraph";
import { cn } from "@/lib/utils";

const STATE_LABEL: Record<NodeState, string> = {
  waiting: "Waiting",
  working: "Working",
  retrying: "Retrying",
  done: "Done",
  reused: "Reused",
  failed: "Failed",
  skipped: "Skipped",
};

const NODE_STYLE: Record<NodeState, { card: string; icon: string; text: string }> = {
  waiting: { card: "", icon: "bg-muted text-muted-foreground", text: "text-muted-foreground" },
  working: {
    card: "border-primary ring-4 ring-primary/15 shadow-glow",
    icon: "bg-primary text-primary-foreground",
    text: "text-primary",
  },
  retrying: {
    card: "border-warning ring-4 ring-warning/20",
    icon: "bg-warning text-foreground",
    text: "text-foreground",
  },
  done: { card: "border-success/45", icon: "bg-success/12 text-success", text: "text-success" },
  reused: {
    card: "border-dashed border-success/60 bg-muted/40",
    icon: "border border-dashed border-success/60 text-success",
    text: "text-success",
  },
  failed: {
    card: "border-destructive/70 bg-destructive/5",
    icon: "bg-destructive/12 text-destructive",
    text: "text-destructive",
  },
  skipped: {
    card: "opacity-50",
    icon: "bg-muted text-muted-foreground",
    text: "text-muted-foreground",
  },
};

// Fill of the line between two agents, and the colour of its arrow head.
const EDGE_STYLE: Record<EdgeState, { fill: string; arrow: string }> = {
  idle: { fill: "", arrow: "text-muted-foreground/30" },
  flowing: {
    fill: "text-primary pipeline-dashes motion-safe:animate-pipeline-flow",
    arrow: "text-primary",
  },
  retrying: {
    fill: "text-warning pipeline-dashes motion-safe:animate-pipeline-flow",
    arrow: "text-warning",
  },
  done: { fill: "bg-success", arrow: "text-success" },
  reused: { fill: "bg-card text-success/70 pipeline-dashes", arrow: "text-success/70" },
  failed: { fill: "bg-destructive", arrow: "text-destructive" },
  skipped: {
    fill: "bg-card text-muted-foreground/40 pipeline-dots",
    arrow: "text-muted-foreground/30",
  },
};

const shortName = (name: string) => name.replace(/ Agent$/, "");

/** Re-renders every `ms` while enabled, so a working agent's time ticks between polls. */
function useNow(enabled: boolean, ms = 200) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [enabled, ms]);
  return now;
}

function nodeTime(state: NodeState, info: AgentSummary | undefined, sinceUpdate: number): string {
  if (state === "reused") return `from v${info?.reused_from_version ?? "?"}`;
  const ms = info?.duration_ms;
  if (ms === null || ms === undefined) return "—";
  if (state === "working" || state === "retrying") return formatDuration(ms + sinceUpdate);
  return formatDuration(ms);
}

export function PipelineGraph({
  summary,
  live = false,
  updatedAt,
  onSelect,
  className,
}: {
  summary: RunSummary | undefined;
  /** The build is still running, so the graph shows itself as live. */
  live?: boolean;
  /** When the summary was fetched (ms epoch); a working agent's time keeps counting from it. */
  updatedAt?: number;
  onSelect?: (stage: StageName) => void;
  className?: string;
}) {
  const nodes = AGENTS.map((agent) => {
    const info = summary?.agents[agent.stage];
    return { agent, info, state: nodeState(info) };
  });
  const active = nodes.find((n) => n.state === "working" || n.state === "retrying");
  const now = useNow(Boolean(active));
  // Count on from the last poll, but never far past it if polling stalls.
  const sinceUpdate = updatedAt ? Math.min(Math.max(now - updatedAt, 0), 3000) : 0;
  const done = nodes.filter((n) => n.state === "done" || n.state === "reused").length;
  const reused = nodes.filter((n) => n.state === "reused").length;

  // On narrow screens the graph scrolls sideways: keep the working agent in view.
  const scroller = useRef<HTMLDivElement>(null);
  const activeStage = active?.agent.stage ?? null;
  useEffect(() => {
    const box = scroller.current;
    if (!box || !activeStage || box.scrollWidth <= box.clientWidth) return;
    const node = box.querySelector<HTMLElement>(`[data-stage="${activeStage}"]`);
    if (!node || typeof box.scrollTo !== "function") return;
    box.scrollTo({
      left: node.offsetLeft - (box.clientWidth - node.offsetWidth) / 2,
      behavior: "smooth",
    });
  }, [activeStage]);

  return (
    <section className={cn("min-w-0", className)} aria-label="Agent pipeline graph">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
          AGENT PIPELINE
          {live ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
              <span className="size-1.5 rounded-full bg-primary motion-safe:animate-pulse" />
              Live
            </span>
          ) : null}
          <span className="font-medium">
            · {done}/7 done{reused ? ` · ${reused} reused` : ""}
          </span>
        </p>
        <Legend />
      </div>

      <div
        ref={scroller}
        role="list"
        aria-label="Agents in pipeline order"
        className="relative -mx-1 mt-3 flex overflow-x-auto px-1 pb-2 pt-1"
      >
        {nodes.map(({ agent, info, state }, index) => {
          const style = NODE_STYLE[state];
          const clickable = Boolean(info?.artifact_id && onSelect);
          const time = nodeTime(state, info, sinceUpdate);
          const attempts = info?.attempts ?? 0;
          const label = `${agent.name}: ${STATE_LABEL[state]}${
            time !== "—" ? `, ${time}` : ""
          }${attempts > 1 ? `, ${attempts} attempts` : ""}`;
          return (
            <Fragment key={agent.stage}>
              {index > 0 && <Edge state={edgeInto(state)} />}
              <div role="listitem" data-stage={agent.stage} className="shrink-0">
                <button
                  type="button"
                  data-state={state}
                  disabled={!clickable}
                  onClick={() => onSelect?.(agent.stage)}
                  title={clickable ? `Open the ${agent.name}'s output` : undefined}
                  aria-label={label}
                  className={cn(
                    "flex w-[6.5rem] flex-col items-center rounded-xl border bg-background px-1.5 pb-2.5 pt-3 text-center transition-[border-color,box-shadow,opacity] duration-300",
                    clickable &&
                      "hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    !clickable && "cursor-default",
                    style.card,
                  )}
                >
                  <span
                    className={cn(
                      "relative grid size-10 place-items-center rounded-full transition-colors duration-300",
                      style.icon,
                    )}
                  >
                    {(state === "working" || state === "retrying") && (
                      <span
                        aria-hidden
                        data-testid="pulse"
                        className={cn(
                          "absolute inset-0 rounded-full motion-safe:animate-pipeline-halo",
                          state === "working" ? "bg-primary/45" : "bg-warning/50",
                        )}
                      />
                    )}
                    <agent.icon className="relative size-5" />
                    <Badge state={state} attempts={attempts} />
                  </span>
                  <span className="mt-2 w-full truncate text-xs font-semibold">
                    {shortName(agent.name)}
                  </span>
                  <span className={cn("text-[11px] font-medium", style.text)}>
                    {STATE_LABEL[state]}
                  </span>
                  <span className="text-[11px] tabular-nums text-muted-foreground">{time}</span>
                </button>
              </div>
            </Fragment>
          );
        })}
      </div>
    </section>
  );
}

function Badge({ state, attempts }: { state: NodeState; attempts: number }) {
  const base =
    "absolute -bottom-1 -right-1 grid size-[1.125rem] place-items-center rounded-full ring-2 ring-background";
  if (state === "done")
    return (
      <span className={cn(base, "bg-success text-white")}>
        <Check className="size-2.5" strokeWidth={3} />
      </span>
    );
  if (state === "failed")
    return (
      <span className={cn(base, "bg-destructive text-white")}>
        <X className="size-2.5" strokeWidth={3} />
      </span>
    );
  if (state === "reused")
    return (
      <span className={cn(base, "border border-dashed border-success/60 bg-card text-success")}>
        <Repeat2 className="size-2.5" strokeWidth={2.5} />
      </span>
    );
  if (state === "retrying")
    return (
      <span className={cn(base, "bg-card text-[9px] font-bold text-foreground")}>
        {attempts > 1 ? attempts : <RotateCcw className="size-2.5" strokeWidth={2.5} />}
      </span>
    );
  return null;
}

function Edge({ state }: { state: EdgeState }) {
  const style = EDGE_STYLE[state];
  const filled = state !== "idle";
  return (
    <div
      aria-hidden
      data-edge={state}
      className="relative flex h-[4.125rem] min-w-6 flex-1 items-center self-start"
    >
      <span className="relative h-[3px] flex-1 overflow-hidden rounded-full bg-border">
        <span
          className={cn(
            "absolute inset-y-0 left-0 rounded-full transition-[width] duration-700 ease-out",
            style.fill,
          )}
          style={{ width: filled ? "100%" : "0%" }}
        />
      </span>
      {(state === "flowing" || state === "retrying") && (
        <span
          data-testid="packet"
          className={cn(
            "absolute top-1/2 size-2 -translate-y-1/2 rounded-full motion-safe:animate-pipeline-packet motion-reduce:hidden",
            state === "flowing"
              ? "bg-primary shadow-[0_0_8px_2px] shadow-primary/50"
              : "bg-warning shadow-[0_0_8px_2px] shadow-warning/50",
          )}
        />
      )}
      <ChevronRight className={cn("-ml-1.5 size-4 shrink-0", style.arrow)} strokeWidth={2.5} />
    </div>
  );
}

const LEGEND: { label: string; state: EdgeState }[] = [
  { label: "Done", state: "done" },
  { label: "Working", state: "flowing" },
  { label: "Reused", state: "reused" },
  { label: "Failed", state: "failed" },
  { label: "Skipped", state: "skipped" },
];

function Legend() {
  return (
    <ul className="hidden flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground sm:flex">
      {LEGEND.map(({ label, state }) => (
        <li key={label} className="inline-flex items-center gap-1.5">
          <span className="relative h-[3px] w-4 overflow-hidden rounded-full bg-border">
            <span className={cn("absolute inset-0", EDGE_STYLE[state].fill)} />
          </span>
          {label}
        </li>
      ))}
    </ul>
  );
}
