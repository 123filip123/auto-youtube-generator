import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ArchivesPage from "./ArchivesPage";

function mockJson(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => body,
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ArchivesPage", () => {
  it("lists each archive with its counts and a link", async () => {
    mockJson([
      {
        slug: "top_5_extinct_animals",
        section_count: 5,
        image_count: 15,
        audio_count: 5,
        has_video: true,
        legacy: false,
        modified_at: "2026-08-18T10:00:00+00:00",
      },
    ]);

    render(
      <MemoryRouter>
        <ArchivesPage />
      </MemoryRouter>,
    );

    const link = await screen.findByRole("link", { name: /top_5_extinct_animals/ });
    expect(link).toHaveAttribute("href", "/archives/top_5_extinct_animals");
    expect(screen.getByText("15")).toBeInTheDocument();
  });

  it("says so when there are no archives", async () => {
    mockJson([]);
    render(
      <MemoryRouter>
        <ArchivesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/no archives yet/i)).toBeInTheDocument();
  });

  it("marks a legacy archive", async () => {
    mockJson([
      {
        slug: "old_run",
        section_count: 0,
        image_count: 3,
        audio_count: 0,
        has_video: true,
        legacy: true,
        modified_at: "2026-01-01T00:00:00+00:00",
      },
    ]);
    render(
      <MemoryRouter>
        <ArchivesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/legacy/i)).toBeInTheDocument();
  });
});
