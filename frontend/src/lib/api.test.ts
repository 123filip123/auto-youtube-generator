import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, approveScript, createRun, getRun, listArchives } from "./api";

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("posts a new run to /api/runs", async () => {
    const fetchMock = mockFetch(201, { id: "abc", topic: "Birds" });
    const run = await createRun({
      topic: "Birds",
      target_seconds: 85,
      review_script: true,
      overrides: {},
    });

    expect(run.id).toBe("abc");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      topic: "Birds",
      target_seconds: 85,
      review_script: true,
      overrides: {},
    });
  });

  it("gets one run by id", async () => {
    const fetchMock = mockFetch(200, { id: "abc" });
    await getRun("abc");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/runs/abc");
  });

  it("wraps the server's detail message in an ApiError", async () => {
    mockFetch(409, { detail: "run abc is still generating_media" });
    await expect(getRun("abc")).rejects.toThrowError(ApiError);
    await expect(getRun("abc")).rejects.toThrow("run abc is still generating_media");
  });

  it("flattens FastAPI's validation error array", async () => {
    mockFetch(422, { detail: [{ msg: "topic must not be blank" }] });
    await expect(getRun("abc")).rejects.toThrow("topic must not be blank");
  });

  it("sends the approved script under a script key", async () => {
    const fetchMock = mockFetch(200, { id: "abc" });
    const script = {
      topic: "Birds",
      title: "Moa",
      style: "A tall bird.",
      sections: [
        { label: "HOOK", narration: "d", prompts: ["x"], start: 0, end: 0 },
      ],
    };
    await approveScript("abc", script);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      script,
    });
  });

  it("lists archives", async () => {
    const fetchMock = mockFetch(200, []);
    expect(await listArchives()).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/archives");
  });
});
