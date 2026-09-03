import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import NewRunPage from "./NewRunPage";

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

function mockApi(createResponse: { status: number; body: unknown }) {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return {
        ok: createResponse.status < 300,
        status: createResponse.status,
        statusText: "",
        json: async () => createResponse.body,
      };
    }
    return { ok: true, status: 200, statusText: "", json: async () => config };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
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
    const fetchMock = mockApi({ status: 201, body: { id: "abc" } });
    renderPage();

    await userEvent.type(screen.getByLabelText(/topic/i), "Extinct animals");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/runs/abc"));

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(post[1]!.body as string)).toEqual({
      topic: "Extinct animals",
      num_items: 5,
      review_items: false,
      overrides: {},
    });
  });

  it("sends only the overrides that were filled in", async () => {
    const fetchMock = mockApi({ status: 201, body: { id: "abc" } });
    renderPage();

    await screen.findByLabelText("MAX_RETRIES");
    await userEvent.type(screen.getByLabelText(/topic/i), "Birds");
    await userEvent.type(screen.getByLabelText("MAX_RETRIES"), "9");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    await waitFor(() => expect(navigate).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(post[1]!.body as string).overrides).toEqual({
      MAX_RETRIES: "9",
    });
  });

  it("shows the server's message when a run is already active", async () => {
    mockApi({ status: 409, body: { detail: "run xyz is still generating_media" } });
    renderPage();

    await userEvent.type(screen.getByLabelText(/topic/i), "Birds");
    await userEvent.click(screen.getByRole("button", { name: /start run/i }));

    expect(
      await screen.findByText(/run xyz is still generating_media/i),
    ).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("will not submit a blank topic", async () => {
    const fetchMock = mockApi({ status: 201, body: { id: "abc" } });
    renderPage();

    await userEvent.click(screen.getByRole("button", { name: /start run/i }));
    expect(await screen.findByText(/enter a topic/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(
      false,
    );
  });
});
