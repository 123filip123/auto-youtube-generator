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
  it("renders the video, title, style and section media", async () => {
    mockJson({
      slug: "birds",
      topic: "extinct birds",
      title: "Birds That Vanished",
      style: "A round flightless bird.",
      video_url: "/media/generated_data/birds/final_video_short.mp4",
      legacy: false,
      sections: [
        {
          label: "Dodo",
          narration: "A bird.",
          prompts: ["a"],
          start: 0,
          end: 5,
          image_urls: ["/media/generated_data/birds/images/item_01_prompt_01.png"],
          composed_image_urls: [],
          audio_url: "/media/generated_data/birds/audio/item_01.mp3",
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Birds That Vanished")).toBeInTheDocument();
    expect(screen.getByText("A round flightless bird.")).toBeInTheDocument();
    expect(screen.getByText("Dodo")).toBeInTheDocument();
    expect(screen.getByText("A bird.")).toBeInTheDocument();
    expect(screen.getByTestId("archive-video")).toHaveAttribute(
      "src",
      "/media/generated_data/birds/final_video_short.mp4",
    );
  });

  it("copes with an archive that has no video", async () => {
    mockJson({
      slug: "old",
      topic: "old",
      title: "old",
      style: "",
      video_url: null,
      legacy: false,
      sections: [],
    });
    renderPage();
    expect(await screen.findByText(/no video/i)).toBeInTheDocument();
  });

  it("shows the error for a missing archive", async () => {
    mockJson({ detail: "no archive birds" }, false, 404);
    renderPage();
    expect(await screen.findByText(/no archive birds/i)).toBeInTheDocument();
  });

  it("groups images under their section label", async () => {
    mockJson({
      slug: "wolves",
      topic: "wolves",
      title: "Wolves Domesticated Themselves",
      style: "A grey-blue wolf.",
      video_url: "/media/generated_data/wolves/final_video_short.mp4",
      legacy: false,
      sections: [
        {
          label: "HOOK",
          narration: "One line.",
          start: 0,
          end: 5,
          prompts: ["p1"],
          image_urls: ["/i1.png"],
          composed_image_urls: [],
          audio_url: "/a.mp3",
        },
      ],
    });
    renderPage();
    expect(await screen.findByText("HOOK")).toBeInTheDocument();
    expect(screen.getByText("One line.")).toBeInTheDocument();
  });

  it("renders both the raw and composed images for a section", async () => {
    mockJson({
      slug: "wolves",
      topic: "wolves",
      title: "Wolves Domesticated Themselves",
      style: "A grey-blue wolf.",
      video_url: null,
      legacy: false,
      sections: [
        {
          label: "HOOK",
          narration: "One line.",
          start: 0,
          end: 5,
          prompts: ["p1"],
          image_urls: ["/raw.png"],
          composed_image_urls: ["/composed.png"],
          audio_url: null,
        },
      ],
    });
    const { container } = renderPage();
    await screen.findByText("HOOK");
    const srcs = Array.from(container.querySelectorAll("img")).map((img) =>
      img.getAttribute("src"),
    );
    expect(srcs).toContain("/raw.png");
    expect(srcs).toContain("/composed.png");
  });

  it("does not render a composed-frames group when there are none yet", async () => {
    mockJson({
      slug: "wolves",
      topic: "wolves",
      title: "Wolves Domesticated Themselves",
      style: "A grey-blue wolf.",
      video_url: null,
      legacy: false,
      sections: [
        {
          label: "HOOK",
          narration: "One line.",
          start: 0,
          end: 5,
          prompts: ["p1"],
          image_urls: ["/raw.png"],
          composed_image_urls: [],
          audio_url: null,
        },
      ],
    });
    renderPage();
    await screen.findByText("HOOK");
    expect(screen.queryByText(/composed frames/i)).not.toBeInTheDocument();
  });

  it("shows the drawing prompts for a section", async () => {
    mockJson({
      slug: "wolves",
      topic: "wolves",
      title: "Wolves Domesticated Themselves",
      style: "A grey-blue wolf.",
      video_url: null,
      legacy: false,
      sections: [
        {
          label: "HOOK",
          narration: "One line.",
          start: 0,
          end: 5,
          prompts: ["a wolf approaching a fire"],
          image_urls: [],
          composed_image_urls: [],
          audio_url: null,
        },
      ],
    });
    renderPage();
    expect(
      await screen.findByText("a wolf approaching a fire"),
    ).toBeInTheDocument();
  });

  it("explains a legacy archive instead of rendering empty sections", async () => {
    mockJson({
      slug: "old_run",
      topic: "old",
      title: "old run",
      style: "",
      video_url: "/v.mp4",
      legacy: true,
      sections: [],
    });
    renderPage();
    expect(await screen.findByText(/older format/i)).toBeInTheDocument();
  });
});
