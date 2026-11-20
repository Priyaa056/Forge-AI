import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { Sparkline, StatsView } from "@/components/app/DashboardStats";
import { ProjectCard } from "@/components/app/ProjectCard";
import type { DashboardStats, ProjectListItem } from "@/lib/api/types";
import { initials, projectColor } from "@/lib/projects";

// Cards link to the workspace; render links as plain anchors outside a router.
vi.mock("@tanstack/react-router", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-router")>()),
  Link: ({ children, className }: { children: ReactNode; className?: string }) => (
    <a href="#project" className={className}>
      {children}
    </a>
  ),
}));

beforeAll(() => {
  // Recharts measures its container with ResizeObserver, which jsdom lacks.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

describe("project presentation helpers", () => {
  it("builds initials and stable colours", () => {
    expect(initials("Library Management System")).toBe("LM");
    expect(initials("owner@forge.test")).toBe("OF");
    expect(initials("")).toBe("?");
    expect(projectColor("#16a34a", "proj_1")).toBe("#16a34a");
    expect(projectColor(null, "proj_1")).toBe(projectColor(undefined, "proj_1"));
    expect(projectColor("not-a-colour", "proj_1")).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("draws a sparkline, with gaps for days without data", () => {
    const { container } = render(<Sparkline values={[1, 3, null, 2]} color="red" />);
    const line = container.querySelectorAll("path")[0];
    expect(line?.getAttribute("d")).toContain("M");
    const empty = render(<Sparkline values={[null, null]} color="red" />);
    expect(empty.container.querySelector("svg")).toBeNull();
  });

  it("marks a single day of data with a dot on a faint baseline", () => {
    const { getByTestId } = render(<Sparkline values={[null, null, null, 4]} color="red" />);
    expect(getByTestId("sparkline-baseline")).toBeInTheDocument();
    expect(getByTestId("sparkline-dot").getAttribute("stroke-linecap")).toBe("round");
  });
});

const project: ProjectListItem = {
  project_id: "proj_abc",
  name: "Library Management System",
  initial_prompt: "Build a library management system with members, books and loans.",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  run_count: 3,
  current_version: 2,
  current_run_id: "run_2",
  last_status: "COMPLETED",
  last_run: {
    run_id: "run_3",
    mode: "refine",
    duration_ms: 9800,
    agents: {
      pm: { status: "COMPLETED", reused: false },
      ui: { status: "COMPLETED", reused: false },
      backend: { status: "COMPLETED", reused: true },
      db: { status: "COMPLETED", reused: true },
      auth: { status: "COMPLETED", reused: true },
      qa: { status: "COMPLETED", reused: false },
      deploy: { status: "COMPLETED", reused: false },
    },
    qa: { passed: 67, run: 67 },
  },
  refinements: 1,
  theme_color: "#16a34a",
  modules: ["Members", "Books", "Loans", "Fines", "Reservations"],
};

describe("ProjectCard", () => {
  it("shows the live version, modules, the last build's agents and QA", () => {
    render(<ProjectCard project={project} onDelete={() => {}} />);
    expect(screen.getByText("Library Management System")).toBeInTheDocument();
    expect(screen.getByText("LM")).toBeInTheDocument();
    expect(screen.getByText("v2 live")).toBeInTheDocument();
    expect(screen.getByText(/1 refinement/)).toBeInTheDocument();
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
    expect(screen.getByText("Last refinement · 9.8 s")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Backend Agent reused \(unchanged\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("67/67 tests")).toBeInTheDocument();
    expect(screen.getByText("3 builds")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Project actions for Library Management System" }),
    ).toBeInTheDocument();
  });

  it("handles a project without builds", () => {
    render(
      <ProjectCard
        project={{ ...project, current_version: null, last_run: null, modules: [], refinements: 0 }}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("No live version yet")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByText(/refinement/)).not.toBeInTheDocument();
  });
});

const stats: DashboardStats = {
  days: 14,
  projects: 2,
  live_apps: 1,
  builds: 3,
  succeeded: 2,
  failed: 1,
  running: 0,
  refinements: 1,
  success_rate: 66.7,
  avg_build_ms: 9800,
  tests_passed: 121,
  tests_run: 121,
  agent_avg_ms: { pm: 40, ui: 90, backend: 60, db: 30, auth: 30, qa: 6400, deploy: 2900 },
  builds_change_pct: 50,
  success_rate_change: -10,
  daily: Array.from({ length: 14 }, (_, i) => ({
    date: `2026-11-${String(7 + i).padStart(2, "0")}`,
    builds: i === 13 ? 3 : 0,
    succeeded: i === 13 ? 2 : 0,
    failed: i === 13 ? 1 : 0,
    success_rate: i === 13 ? 66.7 : null,
    avg_build_ms: i === 13 ? 9800 : null,
    tests_passed: i === 13 ? 121 : 0,
  })),
};

describe("StatsView", () => {
  it("shows the key metrics with trends", () => {
    render(<StatsView stats={stats} />);
    const metrics = screen.getByLabelText("Key metrics");
    expect(metrics).toHaveTextContent("Builds3");
    expect(metrics).toHaveTextContent("Success rate67%");
    expect(metrics).toHaveTextContent("Avg build time9.8 s");
    expect(metrics).toHaveTextContent("Tests passed121");
    expect(metrics).toHaveTextContent("Live apps1");
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("10 pts")).toBeInTheDocument();
    expect(screen.getByText("2 passed · 1 failed")).toBeInTheDocument();
    expect(screen.getByText("of 2 projects")).toBeInTheDocument();
    expect(screen.getByLabelText("Builds per day")).toHaveTextContent("Last 14 days · 3 builds");
    expect(screen.getByLabelText("Average time per agent")).toHaveTextContent("QA6.4 s");
  });
});
