import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NewRunPage from "./NewRunPage";

const createRun = vi.fn();
const getConfig = vi.fn();
vi.mock("@/lib/api", () => ({
  createRun: (...args: unknown[]) => createRun(...args),
  getConfig: (...args: unknown[]) => getConfig(...args),
}));

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const config = {
  values: { IMAGE_QUALITY: "medium", MAX_RETRIES: 5 },
  overridable: [
    {
      name: "IMAGE_QUALITY",
      type: "str",
      choices: ["low", "medium", "high"],
      description: "Higher costs more.",
    },
    { name: "MAX_RETRIES", type: "int", choices: null, description: "Attempts." },
  ],
};

beforeEach(() => {
  getConfig.mockResolvedValue(config);
});

afterEach(() => {
  createRun.mockReset();
  getConfig.mockReset();
  navigate.mockReset();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <NewRunPage />
    </MemoryRouter>,
  );
}

describe("NewRunPage", () => {
  it("creates a run and navigates to it", async () => {
    createRun.mockResolvedValue({ id: "abc" });
    renderPage();

    await userEvent.type(screen.getByLabelText(/topic/i), "Extinct animals");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/runs/abc"));

    expect(createRun.mock.calls[0][0]).toEqual({
      topic: "Extinct animals",
      target_seconds: 85,
      review_script: false,
      overrides: {},
    });
  });

  it("submits a target length in seconds", async () => {
    createRun.mockResolvedValue({ id: "abc" });
    render(<NewRunPage />, { wrapper: MemoryRouter });
    fireEvent.change(screen.getByLabelText("Topic"), {
      target: { value: "how dogs evolved from wolves" },
    });
    fireEvent.change(screen.getByLabelText("Target length (seconds)"), {
      target: { value: "60" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => expect(createRun).toHaveBeenCalled());
    expect(createRun.mock.calls[0][0]).toMatchObject({
      topic: "how dogs evolved from wolves",
      target_seconds: 60,
      review_script: false,
    });
  });

  it("sends only the overrides that were filled in", async () => {
    createRun.mockResolvedValue({ id: "abc" });
    renderPage();

    await screen.findByLabelText("MAX_RETRIES");
    await userEvent.type(screen.getByLabelText(/topic/i), "Birds");
    await userEvent.type(screen.getByLabelText("MAX_RETRIES"), "9");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(createRun.mock.calls[0][0].overrides).toEqual({
      MAX_RETRIES: "9",
    });
  });

  it("shows the server's message when a run is already active", async () => {
    createRun.mockRejectedValue(new Error("run xyz is still generating_media"));
    renderPage();

    await userEvent.type(screen.getByLabelText(/topic/i), "Birds");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    expect(
      await screen.findByText(/run xyz is still generating_media/i),
    ).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("will not submit a blank topic", async () => {
    createRun.mockResolvedValue({ id: "abc" });
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: /start run/i }));
    expect(await screen.findByText(/enter a topic/i)).toBeInTheDocument();
    expect(createRun).not.toHaveBeenCalled();
  });
});
