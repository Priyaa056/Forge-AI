import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PipelineGraph } from "@/components/app/PipelineGraph";
import type { AgentStatus, AgentSummary, RunSummary, StageName } from "@/lib/api/types";
import { edgeInto, nodeState } from "@/lib/pipelineGraph";

const STAGES: StageName[] = ["pm", "ui", "backend", "db", "auth", "qa", "deploy"];

function agent(status: AgentStatus, extra: Partial<AgentSummary> = {}): AgentSummary {
  return {
    title: "",
    status,
    duration_ms: null,
    artifact_id: null,
    attempts: status === "PENDING" ? 0 : 1,
    generation_mode: null,
    generated_files: 0,
    spec_file: "",
    ...extra,
  };
}

function run(agents: Partial<Record<StageName, AgentSummary>>): RunSummary {
  const all = Object.fromEntries(STAGES.map((s) => [s, agents[s] ?? agent("PENDING")])) as Record<
    StageName,
    AgentSummary
  >;
  return {
    project_id: "proj_1",
    run_id: "run_2",
    user_prompt: "Add a phone field to members",
    execution_status: "RUNNING",
    current_agent: "backend",
    progress_percent: 30,
    agent_statuses: Object.fromEntries(STAGES.map((s) => [s, all[s].status])) as Record<
      StageName,
      AgentStatus
    >,
    artifact_ids: {},
    error_reports: {},
    total_duration_ms: 4000,
    successful_agent_count: 2,
    failed_agent_count: 0,
    artifact_count: 2,
    simulated_failure: null,
    qa_summary: null,
    deployment_summary: null,
    agents: all,
    mode: "refine",
  };
}

const node = (name: RegExp) => screen.getByRole("button", { name });
const edgeStates = (container: HTMLElement) =>
  [...container.querySelectorAll("[data-edge]")].map((e) => e.getAttribute("data-edge"));

describe("pipeline graph states", () => {
  it("maps agent summaries to node and line states", () => {
    expect(nodeState(undefined)).toBe("waiting");
    expect(nodeState(agent("RUNNING"))).toBe("working");
    expect(nodeState(agent("RETRYING"))).toBe("retrying");
    expect(nodeState(agent("COMPLETED", { generation_mode: "reused" }))).toBe("reused");
    expect(nodeState(agent("SKIPPED"))).toBe("skipped");
    expect(edgeInto("working")).toBe("flowing");
    expect(edgeInto("waiting")).toBe("idle");
    expect(edgeInto("reused")).toBe("reused");
  });
});

describe("PipelineGraph", () => {
  const live = run({
    pm: agent("COMPLETED", { duration_ms: 1200, artifact_id: "art_pm" }),
    ui: agent("COMPLETED", {
      generation_mode: "reused",
      reused_from_version: 2,
      artifact_id: "art_ui",
    }),
    backend: agent("RUNNING", { duration_ms: 3400 }),
  });

  it("draws seven connected agents in pipeline order", () => {
    const { container } = render(<PipelineGraph summary={live} live />);
    const list = screen.getByRole("list", { name: "Agents in pipeline order" });
    const items = within(list)
      .getAllByRole("listitem")
      .map((li) => li.getAttribute("data-stage"));
    expect(items).toEqual(STAGES);
    // Six lines join seven agents.
    expect(edgeStates(container)).toEqual(["reused", "flowing", "idle", "idle", "idle", "idle"]);
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText(/2\/7 done · 1 reused/)).toBeInTheDocument();
  });

  it("pulses the working agent and sends packets along the line into it", () => {
    const { container } = render(<PipelineGraph summary={live} live />);
    const backend = node(/Backend Agent: Working, 3\.4 s/);
    expect(backend).toHaveAttribute("data-state", "working");
    expect(backend.querySelector("[data-testid=pulse]")).not.toBeNull();
    expect(container.querySelectorAll("[data-testid=packet]")).toHaveLength(1);
    expect(container.querySelector("[data-edge=flowing] [data-testid=packet]")).not.toBeNull();
  });

  it("draws reused agents dashed and shows each agent's duration", () => {
    render(<PipelineGraph summary={live} />);
    const ui = node(/UI Agent: Reused, from v2/);
    expect(ui.className).toContain("border-dashed");
    expect(node(/PM Agent: Done, 1\.2 s/)).toHaveTextContent("1.2 s");
    expect(node(/Database Agent: Waiting/)).toHaveTextContent("—");
  });

  it("keeps counting a working agent's time between polls", () => {
    vi.useFakeTimers();
    const fetched = Date.now();
    render(<PipelineGraph summary={live} live updatedAt={fetched} />);
    expect(node(/Backend Agent/)).toHaveTextContent("3.4 s");
    act(() => vi.advanceTimersByTime(600));
    expect(node(/Backend Agent/)).toHaveTextContent("4.0 s");
    vi.useRealTimers();
  });

  it("opens an agent's output when its node has one", () => {
    const onSelect = vi.fn();
    render(<PipelineGraph summary={live} onSelect={onSelect} />);
    fireEvent.click(node(/PM Agent/));
    expect(onSelect).toHaveBeenCalledWith("pm");
    expect(node(/Database Agent/)).toBeDisabled();
  });

  it("shows a failed build: the failing agent in red and later agents skipped", () => {
    const failed = run({
      pm: agent("COMPLETED", { duration_ms: 900 }),
      ui: agent("COMPLETED", { duration_ms: 800 }),
      backend: agent("COMPLETED", { duration_ms: 700 }),
      db: agent("COMPLETED", { duration_ms: 600 }),
      auth: agent("COMPLETED", { duration_ms: 500 }),
      qa: agent("FAILED", { duration_ms: 2500, attempts: 3, error: "2 tests failed" }),
      deploy: agent("SKIPPED"),
    });
    const { container } = render(
      <PipelineGraph summary={{ ...failed, execution_status: "FAILED" }} />,
    );
    expect(edgeStates(container)).toEqual(["done", "done", "done", "done", "failed", "skipped"]);
    expect(node(/QA Agent: Failed, 2\.5 s, 3 attempts/)).toHaveAttribute("data-state", "failed");
    expect(node(/Deploy Agent: Skipped/)).toHaveAttribute("data-state", "skipped");
    expect(screen.queryByText("Live")).toBeNull();
    expect(container.querySelector("[data-testid=packet]")).toBeNull();
  });

  it("renders all agents as waiting before the first summary arrives", () => {
    const { container } = render(<PipelineGraph summary={undefined} />);
    expect(screen.getAllByRole("button")).toHaveLength(7);
    expect(edgeStates(container).every((e) => e === "idle")).toBe(true);
  });
});
