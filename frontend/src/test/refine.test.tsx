import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChangesView } from "@/components/app/ChangesPanel";
import { RefineForm } from "@/components/app/RefineForm";
import { setToken } from "@/lib/api/client";
import { forgeApi } from "@/lib/api/forge";
import type { RunChanges } from "@/lib/api/types";
import { refineExamples } from "@/lib/refine";

describe("refinement API calls", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("posts the change request for the project and reads a run's changes", async () => {
    setToken("tok-123");
    const fetchMock = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify({ run_id: "run_2", mode: "refine" }), { status: 202 }),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await forgeApi.refineProject("proj_abc", "Remove the fines module.");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/projects\/proj_abc\/refine$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ change_request: "Remove the fines module." });

    await forgeApi.getRunChanges("proj_abc", "run_2");
    expect(fetchMock.mock.calls[1]?.[0]).toMatch(
      /\/api\/projects\/proj_abc\/runs\/run_2\/changes$/,
    );
  });
});

describe("RefineForm", () => {
  it("offers examples built from the app's modules", () => {
    expect(refineExamples(["Members", "Books", "Fines"])).toEqual([
      "Add a notes field to members",
      "Add a manager role who can manage members but not books",
      "Remove the Fines module",
      "Change the primary colour to green",
    ]);
    expect(refineExamples([])).toEqual(["Change the primary colour to green"]);
  });

  it("submits the change request and explains that the live version stays live", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<RefineForm liveVersion={3} moduleLabels={["Members", "Books"]} onSubmit={onSubmit} />);
    expect(
      screen.getByText(/v3 stays live until the refined version passes QA/),
    ).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Refine app" });
    expect(button).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Add a notes field to members" }));
    fireEvent.click(screen.getByRole("button", { name: "Change the primary colour to green" }));
    expect(screen.getByLabelText("What should change?")).toHaveValue(
      "Add a notes field to members. Change the primary colour to green",
    );
    fireEvent.click(button);
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        "Add a notes field to members. Change the primary colour to green",
      ),
    );
  });

  it("asks for a concrete change and shows server errors", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("A build is already running"));
    render(<RefineForm liveVersion={1} onSubmit={onSubmit} />);
    const field = screen.getByLabelText("What should change?");
    fireEvent.change(field, { target: { value: "nicer" } });
    fireEvent.click(screen.getByRole("button", { name: "Refine app" }));
    expect(await screen.findByText(/Describe the change/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(field, { target: { value: "Remove the fines module" } });
    fireEvent.click(screen.getByRole("button", { name: "Refine app" }));
    expect(await screen.findByText("A build is already running")).toBeInTheDocument();
  });
});

const changes: RunChanges = {
  project_id: "proj_abc",
  run_id: "run_2",
  execution_status: "COMPLETED",
  base_run_id: "run_1",
  base_version: 1,
  change_request: "Add a membership type (student, staff) to members.",
  plan: {
    change_request: "Add a membership type (student, staff) to members.",
    base_run_id: "run_1",
    base_version: 1,
    summary: "Field Member.membership_type added. Updates: UI, Backend, Database. Reuses: Auth.",
    applied: ["Field Member.membership_type (enum: student, staff) added"],
    changes: [
      {
        action: "added",
        area: "field",
        target: "Member.membership_type",
        detail: "enum: student, staff",
        agents: ["ui", "backend", "db"],
      },
    ],
    agents: [
      { agent: "pm", action: "plan", reasons: ["Interpreted the change request"] },
      { agent: "ui", action: "update", reasons: ["field Member.membership_type added"] },
      { agent: "backend", action: "update", reasons: ["field Member.membership_type added"] },
      { agent: "db", action: "update", reasons: ["field Member.membership_type added"] },
      { agent: "auth", action: "reuse", reasons: ["No change affects the Auth agent"] },
      { agent: "qa", action: "validate", reasons: ["Runs the generated tests"] },
      { agent: "deploy", action: "package", reasons: ["Health-checks the refined app"] },
    ],
    preserved: { records: 4, fields: 18, modules: 4 },
    unresolved: ["Not supported by the generator: Online payment processing."],
    notes: [],
  },
  agent_actions: { auth: "reused" },
  escalated: [],
  files: {
    added: ["backend/migrations/002_add_membership_type.sql"],
    modified: ["backend/app/models.py", "frontend/src/config/entities.js"],
    removed: [],
    counts: { added: 1, modified: 2, removed: 0, unchanged: 70 },
    by_agent: {},
  },
  regression: {
    base_version: 1,
    requirements_checked: 57,
    requirements_still_met: 57,
    requirements_retired: 0,
    tests_checked: 54,
    tests_still_passing: 54,
    tests_retired: 0,
    failures: [],
  },
  promotion: { state: "promoted", version: 2 },
  error_reports: {},
};

describe("ChangesView", () => {
  it("shows the plan, agents, files and the regression check", () => {
    render(<ChangesView data={changes} />);
    expect(screen.getByText(/REFINING v1 → LIVE AS v2/)).toBeInTheDocument();
    expect(screen.getByText("Member.membership_type")).toBeInTheDocument();
    expect(screen.getByText("Reused")).toBeInTheDocument();
    expect(screen.getAllByText("Updated")).toHaveLength(3);
    expect(screen.getByText("1 added · 2 modified · 0 removed · 70 unchanged")).toBeInTheDocument();
    expect(screen.getByText("backend/migrations/002_add_membership_type.sql")).toBeInTheDocument();
    expect(
      screen.getByText(/57\/57 requirements and 54\/54 tests that passed in v1/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Online payment processing/)).toBeInTheDocument();
    expect(screen.getByText("4 records")).toBeInTheDocument();
  });

  it("shows why nothing changed when the PM agent rejects the request", () => {
    render(
      <ChangesView
        data={{
          ...changes,
          execution_status: "FAILED",
          plan: null,
          files: null,
          regression: null,
          promotion: { state: "not_applicable" },
          error_reports: { pm: "No change to apply: too general. The current version stays live." },
        }}
      />,
    );
    expect(screen.getByText(/The current version stays live/)).toBeInTheDocument();
    expect(screen.queryByText("Agents")).not.toBeInTheDocument();
  });
});
