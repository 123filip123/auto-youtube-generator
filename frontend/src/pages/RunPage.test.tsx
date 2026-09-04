import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import RunPage from "./RunPage";

function mockRun(body: unknown) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    statusText: "",
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/runs/abc"]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const base = {
  id: "abc",
  topic: "Birds",
  target_seconds: 60,
  created_at: "2026-09-03T00:00:00Z",
  finished_at: null,
  review_script: false,
  overrides: {},
  script: { topic: "Birds", title: "", style: "", sections: [] },
  assets: [],
  asset_total: 0,
  logs: [],
  error: null,
  video_url: null,
  archive_slug: null,
};

describe("RunPage", () => {
  it("shows the topic and the asset counter", async () => {
    mockRun({
      ...base,
      status: "generating_media",
      asset_total: 4,
      assets: [
        { label: "image section 1 prompt 1", ok: true, error: null },
        { label: "audio section 1", ok: false, error: "BadRequestError: nope" },
      ],
    });

    renderPage();

    expect(await screen.findByText("Birds")).toBeInTheDocument();
    expect(screen.getByText("2 of 4")).toBeInTheDocument();
    expect(screen.getByText(/BadRequestError: nope/)).toBeInTheDocument();
  });

  it("shows the error when the run failed", async () => {
    mockRun({ ...base, status: "failed", error: "PipelineError: no images" });
    renderPage();
    expect(await screen.findByText(/PipelineError: no images/)).toBeInTheDocument();
  });

  it("renders the script editor when the run is awaiting review", async () => {
    mockRun({
      ...base,
      status: "awaiting_review",
      review_script: true,
      script: {
        topic: "Birds",
        title: "Birds",
        style: "line art",
        sections: [
          { label: "Intro", narration: "Birds fly.", prompts: ["a bird"], start: 0, end: 3 },
        ],
      },
    });

    renderPage();

    expect(await screen.findByText("Review the script")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Birds fly.")).toBeInTheDocument();
  });

  it("renders the video and an archive link when the run completed", async () => {
    mockRun({
      ...base,
      status: "completed",
      finished_at: "2026-09-03T00:10:00Z",
      video_url: "/media/outputs/video_output/final_video_short.mp4?run=abc",
      archive_slug: "birds",
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("run-video")).toHaveAttribute(
        "src",
        "/media/outputs/video_output/final_video_short.mp4?run=abc",
      ),
    );
    expect(screen.getByRole("link", { name: /open archive/i })).toHaveAttribute(
      "href",
      "/archives/birds",
    );
  });

  it("shows the log lines", async () => {
    mockRun({
      ...base,
      status: "completed",
      logs: ["Generating script...", "Done."],
    });
    renderPage();
    expect(await screen.findByText("Generating script...")).toBeInTheDocument();
  });
});
