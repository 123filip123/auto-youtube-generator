import type {
  ArchiveDetail,
  ArchiveSummary,
  ConfigPayload,
  CreateRunRequest,
  RunDetail,
  RunSummary,
  ScriptPayload,
} from "./types";

/** An error the server reported, carrying its status so callers can branch. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    // FastAPI puts the message in `detail`; validation errors make it an array.
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((entry) => entry.msg ?? String(entry)).join(", ")
          : response.statusText || `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export const getConfig = () => request<ConfigPayload>("/config");

export const listRuns = () => request<RunSummary[]>("/runs");

export const createRun = (payload: CreateRunRequest) =>
  request<RunDetail>("/runs", { method: "POST", body: JSON.stringify(payload) });

export const getRun = (runId: string) => request<RunDetail>(`/runs/${runId}`);

export const approveScript = (runId: string, script: ScriptPayload) =>
  request<RunDetail>(`/runs/${runId}/script`, {
    method: "POST",
    body: JSON.stringify({ script }),
  });

export const cancelRun = (runId: string) =>
  request<RunDetail>(`/runs/${runId}/cancel`, { method: "POST" });

export const listArchives = () => request<ArchiveSummary[]>("/archives");

export const getArchive = (slug: string) =>
  request<ArchiveDetail>(`/archives/${slug}`);
