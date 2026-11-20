// Node and line states of the live pipeline graph, derived from a run summary.
import type { AgentSummary } from "./api/types";

export type NodeState =
  "waiting" | "working" | "retrying" | "done" | "reused" | "failed" | "skipped";
export type EdgeState = "idle" | "flowing" | "retrying" | "done" | "reused" | "failed" | "skipped";

export function nodeState(info: AgentSummary | undefined): NodeState {
  if (!info) return "waiting";
  if (info.generation_mode === "reused") return "reused";
  switch (info.status) {
    case "RUNNING":
      return "working";
    case "RETRYING":
      return "retrying";
    case "COMPLETED":
      return "done";
    case "FAILED":
      return "failed";
    case "SKIPPED":
      return "skipped";
    default:
      return "waiting";
  }
}

/** The pipeline is sequential, so the line into an agent takes that agent's state. */
export function edgeInto(target: NodeState): EdgeState {
  switch (target) {
    case "working":
      return "flowing";
    case "waiting":
      return "idle";
    default:
      return target;
  }
}
