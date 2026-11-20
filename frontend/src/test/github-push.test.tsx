import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GitHubPushDialog } from "@/components/app/GitHubPush";
import { setToken } from "@/lib/api/client";
import { forgeApi } from "@/lib/api/forge";
import type { GitHubLink } from "@/lib/api/types";
import { repoSlug } from "@/lib/github";

describe("pushToGitHub API call", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("posts the push options for the selected project with the platform session", async () => {
    setToken("tok-123");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ pushed: true, changed: true, full_name: "me/farm" }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await forgeApi.pushToGitHub("proj_abc", { token: "gh-test", mode: "new", name: "farm" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/projects\/proj_abc\/github\/push$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      token: "gh-test",
      mode: "new",
      name: "farm",
    });
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok-123");
  });

  it("keeps the platform session when GitHub rejects the token", async () => {
    setToken("tok-123");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "GitHub rejected the access token." }), {
          status: 400,
        }),
      ),
    );
    await expect(
      forgeApi.pushToGitHub("proj_abc", { token: "bad", mode: "new", name: "farm" }),
    ).rejects.toMatchObject({ status: 400, message: "GitHub rejected the access token." });
    expect(window.localStorage.getItem("forge-token")).toBe("tok-123");
  });
});

describe("GitHubPushDialog", () => {
  const base = {
    open: true,
    projectName: "AgriTrack Farm",
    version: 3,
    pending: false,
    error: null,
    onCancel: vi.fn(),
    onSubmit: vi.fn(),
  };
  const token = () => screen.getByLabelText(/GitHub access token/);
  const pushButton = () => screen.getByRole("button", { name: "Push" });

  it("derives a valid repository name", () => {
    expect(repoSlug("AgriTrack – Smart Farm!")).toBe("agritrack-smart-farm");
    expect(repoSlug("***")).toBe("forge-app");
  });

  it("creates a private repository by default and needs a token first", () => {
    const onSubmit = vi.fn();
    render(<GitHubPushDialog {...base} onSubmit={onSubmit} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Repository name")).toHaveValue("agritrack-farm");
    expect(screen.getByRole("checkbox")).toBeChecked();
    expect(token()).toHaveAttribute("type", "password");
    expect(pushButton()).toBeDisabled();

    fireEvent.change(token(), { target: { value: " gh-test " } });
    fireEvent.click(pushButton());
    expect(onSubmit).toHaveBeenCalledWith({
      token: "gh-test",
      mode: "new",
      name: "agritrack-farm",
      private: true,
    });
  });

  it("pushes to an existing repository and branch", () => {
    const onSubmit = vi.fn();
    render(<GitHubPushDialog {...base} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByLabelText(/Existing repository/));
    fireEvent.change(token(), { target: { value: "gh-test" } });
    expect(pushButton()).toBeDisabled(); // owner/name still missing
    fireEvent.change(screen.getByPlaceholderText("owner/repository"), {
      target: { value: "octo-org/farm" },
    });
    fireEvent.change(screen.getByLabelText(/Branch/), { target: { value: "forge" } });
    fireEvent.change(screen.getByLabelText(/Commit message/), { target: { value: "v3" } });
    fireEvent.click(pushButton());
    expect(onSubmit).toHaveBeenCalledWith({
      token: "gh-test",
      mode: "existing",
      repository: "octo-org/farm",
      branch: "forge",
      message: "v3",
    });
  });

  it("updates the linked repository by default", () => {
    const link: GitHubLink = {
      full_name: "me/agritrack",
      html_url: "https://github.com/me/agritrack",
      branch: "main",
      last_commit: "abc",
      commit_url: "https://github.com/me/agritrack/commit/abc",
      pushed_version: 2,
      pushed_at: new Date().toISOString(),
    };
    const onSubmit = vi.fn();
    render(<GitHubPushDialog {...base} link={link} onSubmit={onSubmit} />);
    expect(screen.getByLabelText(/Linked repository/)).toBeChecked();
    expect(screen.getByRole("link", { name: "me/agritrack" })).toHaveAttribute(
      "href",
      "https://github.com/me/agritrack",
    );
    fireEvent.change(token(), { target: { value: "gh-test" } });
    fireEvent.click(pushButton());
    expect(onSubmit).toHaveBeenCalledWith({
      token: "gh-test",
      mode: "existing",
      repository: "me/agritrack",
      branch: "main",
    });
  });

  it("rejects invalid names and shows errors while keeping the form", () => {
    const { rerender } = render(<GitHubPushDialog {...base} />);
    fireEvent.change(token(), { target: { value: "gh-test" } });
    fireEvent.change(screen.getByLabelText("Repository name"), { target: { value: "bad name" } });
    expect(screen.getByText(/letters, numbers/)).toBeInTheDocument();
    expect(pushButton()).toBeDisabled();

    rerender(<GitHubPushDialog {...base} pending error="GitHub rejected the access token." />);
    expect(screen.getByText("GitHub rejected the access token.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pushing/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("clears the token when the dialog is closed", () => {
    const { rerender } = render(<GitHubPushDialog {...base} />);
    fireEvent.change(token(), { target: { value: "gh-test" } });
    rerender(<GitHubPushDialog {...base} open={false} />);
    rerender(<GitHubPushDialog {...base} open />);
    expect(token()).toHaveValue("");
  });
});
