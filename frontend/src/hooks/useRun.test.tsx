import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRun } from "./useRun";

function mockSequence(bodies: unknown[]) {
  let index = 0;
  const fetchMock = vi.fn(async () => {
    const body = bodies[Math.min(index, bodies.length - 1)];
    index += 1;
    return { ok: true, status: 200, statusText: "", json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useRun", () => {
  it("does nothing without a run id", () => {
    const fetchMock = mockSequence([{}]);
    const { result } = renderHook(() => useRun(null, 5));
    expect(result.current.run).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("polls until the run reaches a terminal status", async () => {
    const fetchMock = mockSequence([
      { id: "abc", status: "generating_media" },
      { id: "abc", status: "generating_media" },
      { id: "abc", status: "completed" },
    ]);

    const { result } = renderHook(() => useRun("abc", 5));
    await waitFor(() => expect(result.current.run?.status).toBe("completed"));

    const settled = fetchMock.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(fetchMock.mock.calls.length).toBe(settled);
  });

  it("keeps polling through a transient failure", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValue({
        ok: true,
        status: 200,
        statusText: "",
        json: async () => ({ id: "abc", status: "completed" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    // A slower interval than the other tests, so the error state is still
    // observable when waitFor looks; the retry would otherwise clear it first.
    const { result } = renderHook(() => useRun("abc", 100));
    await waitFor(() => expect(result.current.error).toBe("network down"));
    await waitFor(() => expect(result.current.run?.status).toBe("completed"));
    expect(result.current.error).toBeNull();
  });
});
