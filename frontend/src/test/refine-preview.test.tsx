import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RefineFlow } from "@/components/app/RefineFlow";
import { forgeApi } from "@/lib/api/forge";
import type { RefinePreview } from "@/lib/api/types";

const preview: RefinePreview = {
  applicable: true,
  message: null,
  draft_id: "draft_abc123",
  base_run_id: "run_1",
  base_version: 2,
  change_request: "Remove the fines module.",
  plan: {
    change_request: "Remove the fines module.",
    base_run_id: "run_1",
    base_version: 2,
    summary: "Fine records removed; module 'Fines' removed. Updates: UI, Backend, Database, Auth.",
    applied: ["Fine records removed"],
    changes: [
      { action: "removed", area: "entity", target: "Fine", detail: "", agents: ["ui", "backend"] },
    ],
    agents: [
      { agent: "pm", action: "plan", reasons: ["Interpreted the change request"] },
      { agent: "ui", action: "update", reasons: ["Fine records removed"] },
      { agent: "backend", action: "update", reasons: ["Fine records removed"] },
      { agent: "db", action: "update", reasons: ["Fine records removed"] },
      { agent: "auth", action: "update", reasons: ["Fine records removed"] },
      { agent: "qa", action: "validate", reasons: ["Regression check"] },
      { agent: "deploy", action: "package", reasons: ["Health check"] },
    ],
    preserved: { records: 3 },
    unresolved: [],
    notes: [],
  },
  warnings: ["All fines records will be permanently deleted: the migration drops the fines table."],
  migration: {
    file: "backend/migrations/003_remove_fines_module.sql",
    sql: "DROP TABLE IF EXISTS fines CASCADE;",
  },
  files: {
    added: ["backend/migrations/003_remove_fines_module.sql"],
    modified: ["backend/app/main.py"],
    removed: ["backend/app/routers/fines.py"],
    counts: { added: 1, modified: 1, removed: 1, unchanged: 60 },
    by_agent: {},
  },
  notes: ["QA and Deploy also update the generated tests and deployment files during the build."],
};

async function openPreview(onApplied = vi.fn()) {
  render(
    <RefineFlow
      projectId="proj_abc"
      liveVersion={2}
      moduleLabels={["Members", "Fines"]}
      onApplied={onApplied}
    />,
  );
  fireEvent.change(screen.getByLabelText("What should change?"), {
    target: { value: "Remove the fines module." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
  await screen.findByLabelText("Change plan preview");
  return onApplied;
}

describe("RefineFlow plan preview", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the plan, data warnings, migration and code changes before anything changes", async () => {
    const previewSpy = vi.spyOn(forgeApi, "previewRefinement").mockResolvedValue(preview);
    const applySpy = vi.spyOn(forgeApi, "applyRefinementPlan");
    await openPreview();
    expect(previewSpy).toHaveBeenCalledWith("proj_abc", "Remove the fines module.");
    expect(applySpy).not.toHaveBeenCalled();
    expect(screen.getByText(/v2 → v3 · NOTHING CHANGED YET/)).toBeInTheDocument();
    expect(screen.getByText("This change deletes data")).toBeInTheDocument();
    expect(screen.getByText(/drops the fines table/)).toBeInTheDocument();
    expect(
      screen.getByText("backend/migrations/003_remove_fines_module.sql", { selector: "summary" }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 added · 1 modified · 1 removed · 60 unchanged")).toBeInTheDocument();
    expect(screen.getByText("backend/app/routers/fines.py")).toBeInTheDocument();
  });

  it("applies the previewed plan only after the data loss is acknowledged", async () => {
    vi.spyOn(forgeApi, "previewRefinement").mockResolvedValue(preview);
    const applySpy = vi.spyOn(forgeApi, "applyRefinementPlan").mockResolvedValue({
      project_id: "proj_abc",
      run_id: "run_9",
      mode: "refine",
      approved_plan: true,
    });
    const onApplied = await openPreview();
    const apply = screen.getByRole("button", { name: "Apply changes" });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByLabelText("I understand this data will be deleted"));
    fireEvent.click(apply);
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith("run_9"));
    expect(applySpy).toHaveBeenCalledWith("proj_abc", "draft_abc123");
  });

  it("returns to the request for editing, and explains requests that cannot be applied", async () => {
    vi.spyOn(forgeApi, "previewRefinement")
      .mockResolvedValueOnce(preview)
      .mockResolvedValueOnce({
        ...preview,
        applicable: false,
        draft_id: null,
        plan: null,
        warnings: [],
        migration: null,
        files: null,
        message:
          "No change to apply: “Make it nicer” is too general. The current version stays live.",
      });
    await openPreview();
    fireEvent.click(screen.getByRole("button", { name: "Edit request" }));
    const field = screen.getByLabelText("What should change?");
    expect(field).toHaveValue("Remove the fines module.");

    fireEvent.change(field, { target: { value: "Make it nicer please" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview changes" }));
    expect(await screen.findByText(/too general/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply changes" })).not.toBeInTheDocument();
  });
});
