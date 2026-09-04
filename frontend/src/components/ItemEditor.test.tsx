import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItemEditor from "./ItemEditor";

const items = [
  {
    title: "Dodo",
    description: "A bird. It could not fly.",
    style: "A round flightless bird.",
    beats: [
      { narration: "A bird.", prompt: "a" },
      { narration: "It could not fly.", prompt: "b" },
    ],
    image_prompts: ["a", "b"],
  },
  {
    title: "Moa",
    description: "A taller bird.",
    style: "A very tall bird.",
    beats: [{ narration: "A taller bird.", prompt: "c" }],
    image_prompts: ["c"],
  },
];

function mockPost(status = 200, body: unknown = { id: "abc" }) {
  // The parameters are declared so the recorded calls stay typed, which is
  // what lets the assertions below read init.body.
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
    ok: status < 300,
    status,
    statusText: "",
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("ItemEditor", () => {
  it("posts the edited items", async () => {
    const fetchMock = mockPost();
    const onApproved = vi.fn();
    render(<ItemEditor runId="abc" items={items} onApproved={onApproved} />);

    const title = screen.getByLabelText("Item 1 title");
    await userEvent.clear(title);
    await userEvent.type(title, "Great Auk");
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(onApproved).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].title).toBe("Great Auk");
    expect(body.items[1].title).toBe("Moa");
  });

  it("adds and removes beats", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    await userEvent.click(screen.getAllByRole("button", { name: /add beat/i })[1]);
    await userEvent.type(screen.getByLabelText("Item 2 beat 2 drawing"), "new prompt");
    await userEvent.click(
      screen.getByRole("button", { name: "Remove item 1 beat 2" }),
    );
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].beats).toHaveLength(1);
    expect(body.items[0].beats[0].prompt).toBe("a");
    expect(body.items[1].beats[1].prompt).toBe("new prompt");
  });

  it("edits a beat's narration and shows the derived description", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    const narration = screen.getByLabelText("Item 1 beat 1 narration");
    await userEvent.clear(narration);
    await userEvent.type(narration, "A very odd bird.");

    expect(
      screen.getByText("A very odd bird. It could not fly."),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].beats[0].narration).toBe("A very odd bird.");
  });

  it("edits the style sheet", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    const style = screen.getByLabelText("Item 1 style");
    await userEvent.clear(style);
    await userEvent.type(style, "A spotted bird.");
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items[0].style).toBe("A spotted bird.");
  });

  it("removes an item", async () => {
    const fetchMock = mockPost();
    render(<ItemEditor runId="abc" items={items} onApproved={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Remove item 1" }));
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(body.items).toHaveLength(1);
    expect(body.items[0].title).toBe("Moa");
  });

  it("shows the server's rejection message", async () => {
    mockPost(400, { detail: "item 1 is missing a usable 'image_prompts' list" });
    const onApproved = vi.fn();
    render(<ItemEditor runId="abc" items={items} onApproved={onApproved} />);

    await userEvent.click(screen.getByRole("button", { name: /approve/i }));

    expect(await screen.findByText(/image_prompts/)).toBeInTheDocument();
    expect(onApproved).not.toHaveBeenCalled();
  });
});
