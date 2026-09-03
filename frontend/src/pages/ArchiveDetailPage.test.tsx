import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ArchiveDetailPage from "./ArchiveDetailPage";

function mockJson(body: unknown, ok = true, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok, status, statusText: "", json: async () => body })),
  );
}

afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/archives/birds"]}>
      <Routes>
        <Route path="/archives/:slug" element={<ArchiveDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ArchiveDetailPage", () => {
  it("renders the video, images and audio", async () => {
    mockJson({
      slug: "birds",
      video_url: "/media/generated_data/birds/final_video_short.mp4",
      items: [
        {
          title: "Dodo",
          description: "A bird.",
          image_prompts: ["a"],
          image_urls: ["/media/generated_data/birds/images/item_01_prompt_01.png"],
          titled_image_urls: [],
          audio_url: "/media/generated_data/birds/audio/item_01.mp3",
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Dodo")).toBeInTheDocument();
    expect(screen.getByTestId("archive-video")).toHaveAttribute(
      "src",
      "/media/generated_data/birds/final_video_short.mp4",
    );
    expect(screen.getByAltText("Dodo image 1")).toHaveAttribute(
      "src",
      "/media/generated_data/birds/images/item_01_prompt_01.png",
    );
    expect(screen.getByTestId("audio-1")).toHaveAttribute(
      "src",
      "/media/generated_data/birds/audio/item_01.mp3",
    );
  });

  it("copes with an archive that has no video", async () => {
    mockJson({ slug: "old", video_url: null, items: [] });
    renderPage();
    expect(await screen.findByText(/no video/i)).toBeInTheDocument();
  });

  it("shows the error for a missing archive", async () => {
    mockJson({ detail: "no archive birds" }, false, 404);
    renderPage();
    expect(await screen.findByText(/no archive birds/i)).toBeInTheDocument();
  });
});
