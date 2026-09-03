import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StageProgress from "./StageProgress";
import type { RunDetail } from "@/lib/types";

function makeRun(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    id: "abc",
    topic: "Birds",
    num_items: 2,
    status: "generating_media",
    created_at: "2026-09-03T00:00:00Z",
    finished_at: null,
    review_items: false,
    overrides: {},
    items: [],
    assets: [],
    asset_total: 0,
    logs: [],
    error: null,
    video_url: null,
    archive_slug: null,
    ...overrides,
  };
}

describe("StageProgress", () => {
  it("marks stages before the current one as done", () => {
    render(<StageProgress run={makeRun()} />);
    expect(screen.getByTestId("stage-generating_list")).toHaveTextContent("done");
    expect(screen.getByTestId("stage-generating_media")).toHaveTextContent("running");
    expect(screen.getByTestId("stage-archiving")).toHaveTextContent("pending");
  });

  it("hides the review stage when review was not requested", () => {
    render(<StageProgress run={makeRun()} />);
    expect(screen.queryByTestId("stage-awaiting_review")).toBeNull();
  });

  it("shows the review stage when review was requested", () => {
    render(<StageProgress run={makeRun({ review_items: true })} />);
    expect(screen.getByTestId("stage-awaiting_review")).toBeInTheDocument();
  });

  it("marks every stage done when the run completed", () => {
    render(<StageProgress run={makeRun({ status: "completed" })} />);
    expect(screen.getByTestId("stage-archiving")).toHaveTextContent("done");
  });

  it("leaves unreached stages pending when the run failed", () => {
    render(
      <StageProgress
        run={makeRun({ status: "failed", error: "PipelineError: no images" })}
      />,
    );
    expect(screen.getByTestId("stage-archiving")).toHaveTextContent("pending");
  });
});
