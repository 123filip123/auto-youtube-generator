import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, approveItems, createRun, getRun, listArchives } from "./api";

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
      num_items: 3,
      review_items: true,
      overrides: {},
      production_models: false,
    });

    expect(run.id).toBe("abc");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      topic: "Birds",
      num_items: 3,
      review_items: true,
      overrides: {},
      production_models: false,
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

  it("sends approved items under an items key", async () => {
    const fetchMock = mockFetch(200, { id: "abc" });
    await approveItems("abc", [
      { title: "Moa", description: "d", image_prompts: ["x"] },
    ]);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      items: [{ title: "Moa", description: "d", image_prompts: ["x"] }],
    });
  });

  it("lists archives", async () => {
    const fetchMock = mockFetch(200, []);
    expect(await listArchives()).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/archives");
  });
});
