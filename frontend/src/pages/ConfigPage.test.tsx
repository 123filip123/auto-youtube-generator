import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ConfigPage from "./ConfigPage";

function mockConfig() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "",
      json: async () => ({
        values: { IMAGE_QUALITY: "medium", VIDEO_WIDTH: 1080 },
        overridable: [
          {
            name: "IMAGE_QUALITY",
            type: "str",
            choices: ["low", "medium", "high"],
            description: "Higher costs more.",
          },
        ],
      }),
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ConfigPage", () => {
  it("shows every value and marks the overridable ones", async () => {
    mockConfig();
    render(<ConfigPage />);

    const overridable = await screen.findByTestId("row-IMAGE_QUALITY");
    expect(within(overridable).getByText("medium")).toBeInTheDocument();
    expect(within(overridable).getByText(/per run/i)).toBeInTheDocument();

    const fixed = screen.getByTestId("row-VIDEO_WIDTH");
    expect(within(fixed).getByText("1080")).toBeInTheDocument();
    expect(within(fixed).queryByText(/per run/i)).toBeNull();
  });
});
