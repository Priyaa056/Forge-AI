import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DeleteProjectDialog } from "@/components/app/DeleteProject";
import { setToken } from "@/lib/api/client";
import { forgeApi } from "@/lib/api/forge";

describe("deleteProject API call", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("sends an authenticated DELETE for the selected project id only", async () => {
    setToken("tok-123");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ deleted: true, project_id: "proj_abc" }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(forgeApi.deleteProject("proj_abc")).resolves.toMatchObject({ deleted: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/projects\/proj_abc$/);
    expect(init.method).toBe("DELETE");
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok-123");
  });

  it("surfaces the server's reason when deletion is refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "A build is still running for this project." }), {
          status: 409,
        }),
      ),
    );
    await expect(forgeApi.deleteProject("proj_abc")).rejects.toMatchObject({
      status: 409,
      message: "A build is still running for this project.",
    });
  });
});

describe("DeleteProjectDialog", () => {
  const props = {
    projectName: "AgriTrack",
    open: true,
    pending: false,
    error: null,
    onCancel: vi.fn(),
    onConfirm: vi.fn(),
  };

  it("names the project and asks for confirmation", () => {
    render(<DeleteProjectDialog {...props} />);
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText("Delete “AgriTrack”?")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Are you sure you want to delete this project? This action cannot be undone.",
      ),
    ).toBeInTheDocument();
  });

  it("cancels without deleting and confirms with Delete", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(<DeleteProjectDialog {...props} onCancel={onCancel} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("shows the failure and keeps the dialog while deleting", () => {
    render(<DeleteProjectDialog {...props} pending error="Could not delete" />);
    expect(screen.getByText("Could not delete")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Deleting/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });
});
