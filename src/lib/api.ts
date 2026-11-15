// Backend API client — relative paths only (Caddy gateway: XTransformPort)
import type { UserInfo, WorkspaceInfo } from "./types";

const PORT = "8321";
const Q = `XTransformPort=${PORT}`;

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("audlens.token");
}

export function getWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("audlens.workspace");
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as WorkspaceInfo | string;
    return typeof parsed === "string" ? parsed : parsed.id ?? null;
  } catch {
    return raw;
  }
}

export function setAuth(token: string, user: UserInfo, workspace: WorkspaceInfo): void {
  localStorage.setItem("audlens.token", token);
  localStorage.setItem("audlens.user", JSON.stringify(user));
  localStorage.setItem("audlens.workspace", JSON.stringify(workspace));
}

export function clearAuth(): void {
  localStorage.removeItem("audlens.token");
  localStorage.removeItem("audlens.user");
  localStorage.removeItem("audlens.workspace");
}

export function loadUser(): UserInfo | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("audlens.user");
    return raw ? (JSON.parse(raw) as UserInfo) : null;
  } catch {
    return null;
  }
}

export function loadWorkspace(): WorkspaceInfo | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("audlens.workspace");
    return raw ? (JSON.parse(raw) as WorkspaceInfo) : null;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  method: "GET" | "POST" | "PUT" | "DELETE",
  path: string,
  opts: { body?: unknown; retryAuth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const ws = getWorkspaceId();
  if (ws) headers["X-Workspace-Id"] = ws;

  const sep = path.includes("?") ? "&" : "?";
  const res = await fetch(`/api/v1${path}${sep}${Q}`, {
    method,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (res.status === 204) return {} as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail =
      data && typeof data === "object" && "detail" in (data as Record<string, unknown>)
        ? String((data as Record<string, unknown>).detail)
        : `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

async function requestBlob(path: string): Promise<{ blob: Blob; filename: string }> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const ws = getWorkspaceId();
  if (ws) headers["X-Workspace-Id"] = ws;
  const sep = path.includes("?") ? "&" : "?";
  const res = await fetch(`/api/v1${path}${sep}${Q}`, { method: "POST", headers });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data && typeof data === "object" && "detail" in (data as Record<string, unknown>)) {
        detail = String((data as Record<string, unknown>).detail);
      }
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const match = /filename="?([^";]+)"?/i.exec(cd);
  return { blob, filename: match?.[1] ?? "report.pdf" };
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, { body }),
  postBlob: (path: string) => requestBlob(path),
};

export async function ensureBackend(): Promise<boolean> {
  try {
    const res = await fetch("/api/py-health");
    const data = await res.json();
    return !!data.ok;
  } catch {
    return false;
  }
}
