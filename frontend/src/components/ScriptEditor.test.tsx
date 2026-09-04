import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ScriptEditor from "./ScriptEditor";
import type { ScriptPayload } from "@/lib/types";

const approveScript = vi.fn();
vi.mock("@/lib/api", () => ({
  approveScript: (...args: unknown[]) => approveScript(...args),
}));

const script: ScriptPayload = {
  topic: "wolves",
  title: "Wolves Domesticated Themselves",
  style: "A grey-blue wolf with amber eyes.",
  sections: [
    { label: "HOOK", narration: "Your dog's ancestor could have killed you.", prompts: ["a snarling wolf", "a goofy dog"], start: 0, end: 5 },
    { label: "SETUP", narration: "Wolves found our camps.", prompts: ["wolves near a fire"], start: 5, end: 20 },
  ],
};

beforeEach(() => {
  approveScript.mockReset();
  approveScript.mockResolvedValue({});
});

describe("ScriptEditor", () => {
  it("renders every section with its narration and prompts", () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    expect(screen.getByDisplayValue("HOOK")).toBeInTheDocument();
    expect(screen.getByDisplayValue("SETUP")).toBeInTheDocument();
    expect(screen.getByDisplayValue("a snarling wolf")).toBeInTheDocument();
    expect(screen.getByDisplayValue("wolves near a fire")).toBeInTheDocument();
  });

  it("shows the global style sheet once, not per section", () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    expect(screen.getAllByDisplayValue("A grey-blue wolf with amber eyes.")).toHaveLength(1);
  });

  it("submits edited narration", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.change(screen.getByLabelText("Section 1 narration"), {
      target: { value: "An edited hook." },
    });
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections[0].narration).toBe("An edited hook.");
  });

  it("does not change the prompt count when narration is edited", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.change(screen.getByLabelText("Section 1 narration"), {
      target: { value: "A far far far longer narration than before. ".repeat(10) },
    });
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections[0].prompts).toHaveLength(2);
  });

  it("adds a drawing to one section only", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Add drawing to section 1" }));
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections[0].prompts).toHaveLength(3);
    expect(submitted.sections[1].prompts).toHaveLength(1);
  });

  it("removes a drawing", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove section 1 drawing 1" }));
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections[0].prompts).toEqual(["a goofy dog"]);
  });

  it("removes a whole section", async () => {
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove section 1" }));
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(approveScript).toHaveBeenCalled());
    const [, submitted] = approveScript.mock.calls[0];
    expect(submitted.sections).toHaveLength(1);
    expect(submitted.sections[0].label).toBe("SETUP");
  });

  it("surfaces a server error", async () => {
    approveScript.mockRejectedValue(new Error("boom"));
    render(<ScriptEditor runId="r1" script={script} onApproved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("calls onApproved after a successful submit", async () => {
    const onApproved = vi.fn();
    render(<ScriptEditor runId="r1" script={script} onApproved={onApproved} />);
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(onApproved).toHaveBeenCalled());
  });
});
