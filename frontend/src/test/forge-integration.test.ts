import { QueryClient } from "@tanstack/react-query";
import { createRouter, rootRouteId } from "@tanstack/react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  errorMessage,
  getToken,
  onUnauthorized,
  request,
  setToken,
} from "@/lib/api/client";
import { routeTree } from "@/routeTree.gen";

describe("FORGE AI routes", () => {
  const router = createRouter({ routeTree, context: { queryClient: new QueryClient() } });

  it.each(["/", "/login", "/signup", "/app", "/app/new", "/app/projects/proj_123"])(
    "matches a page for %s",
    (path) => {
      const matches = router.matchRoutes(path);
      expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
    },
  );

  it("passes the project id to the workspace route", () => {
    const matches = router.matchRoutes("/app/projects/proj_abc");
    expect(matches.at(-1)?.params).toMatchObject({ projectId: "proj_abc" });
  });
});

describe("API error messages", () => {
  it("uses FastAPI string details", () => {
    expect(errorMessage({ detail: "Incorrect email or password." }, 401)).toBe(
      "Incorrect email or password.",
    );
  });

  it("formats validation errors", () => {
    expect(
      errorMessage({ detail: [{ loc: ["body", "user_prompt"], msg: "Field required" }] }, 422),
    ).toBe("user_prompt: Field required");
  });

  it("falls back to the status code", () => {
    expect(errorMessage(null, 500)).toBe("Request failed (500)");
  });
});

describe("API client", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the session token and parses JSON", async () => {
    setToken("tok-123");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(request<{ ok: boolean }>("/api/projects")).resolves.toEqual({ ok: true });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok-123");
  });

  it("clears the session and notifies listeners on 401", async () => {
    setToken("expired");
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: "Session expired" }), { status: 401 }),
        ),
    );

    await expect(request("/api/projects")).rejects.toMatchObject({
      status: 401,
      message: "Session expired",
    });
    expect(getToken()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
  });

  it("does not send a token for public auth calls", async () => {
    setToken("tok-123");
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await request("/api/auth/login", { method: "POST", body: {}, auth: false });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["Authorization"]).toBeUndefined();
  });

  it("reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await request("/api/system").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toMatch(/Cannot reach the FORGE AI API/);
  });
});
