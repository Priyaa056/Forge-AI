// Browser-safe HTTP client for the FORGE AI platform API (FastAPI).
// Holds only the user's session token; no secrets live in the frontend.

const configuredBase = import.meta.env["VITE_API_BASE_URL"] as string | undefined;
export const API_BASE_URL = (configuredBase && configuredBase.trim()) || "http://127.0.0.1:8000";

const TOKEN_KEY = "forge-token";
const unauthorizedListeners = new Set<() => void>();

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode) — the session lasts for this page only */
  }
}

/** Subscribe to "session expired / rejected" notifications. Returns an unsubscribe function. */
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export function errorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string };
          const field = Array.isArray(entry.loc) ? entry.loc[entry.loc.length - 1] : undefined;
          return field
            ? `${String(field)}: ${entry.msg ?? "invalid"}`
            : (entry.msg ?? "Invalid request");
        })
        .join("; ");
    }
  }
  return `Request failed (${status})`;
}

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** Send the session token (default true). */
  auth?: boolean;
};

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = options.auth === false ? null : getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const init: RequestInit = { method: options.method ?? "GET", headers };
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  if (options.signal) init.signal = options.signal;
  try {
    return await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      0,
      `Cannot reach the FORGE AI API at ${API_BASE_URL}. Make sure the backend is running.`,
    );
  }
}

async function failure(response: Response, auth: boolean): Promise<ApiError> {
  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (response.status === 401 && auth) {
    setToken(null);
    unauthorizedListeners.forEach((listener) => listener());
  }
  return new ApiError(response.status, errorMessage(data, response.status));
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);
  if (!response.ok) throw await failure(response, options.auth !== false);
  const text = await response.text();
  return (text ? JSON.parse(text) : null) as T;
}

/** Download a binary response (e.g. a ZIP) using the session token, then save it in the browser. */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const response = await send(path, {});
  if (!response.ok) throw await failure(response, true);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = match?.[1] ?? fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
