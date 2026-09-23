import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  DemoWorkspaceProvider,
  useDemoWorkspace,
} from "@/features/demo-workspace/demo-workspace-provider";
import { NewMeetingModal } from "@/features/meetings/ui/new-meeting-modal";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function ModalHarness() {
  const { meetings, openNewMeeting } = useDemoWorkspace();
  const newestMeeting = meetings[0];

  return (
    <>
      <button onClick={openNewMeeting} type="button">
        Open modal
      </button>
      <output data-testid="newest-participants">
        {newestMeeting?.participantNames.join("|")}
      </output>
      <output data-testid="newest-language">{newestMeeting?.language}</output>
      <NewMeetingModal />
    </>
  );
}

function renderModal() {
  render(
    <DemoWorkspaceProvider
      initialProfile={{
        displayName: "Vlad",
        email: "vlad@example.com",
        role: "Meeting organizer",
        department: "Product team",
      }}
    >
      <ModalHarness />
    </DemoWorkspaceProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Open modal" }));
}

describe("NewMeetingModal", () => {
  it("starts with one username field and no language selector", () => {
    renderModal();

    expect(
      screen.getByRole("textbox", { name: "Participant username 1" }),
    ).toHaveValue("");
    expect(
      screen.queryByRole("combobox", { name: "Recording language" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Add another participant" }),
    );
    expect(
      screen.getByRole("textbox", { name: "Participant username 2" }),
    ).toBeInTheDocument();
  });

  it("resets participant rows when the dialog is closed", () => {
    renderModal();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Participant username 1" }),
      { target: { value: "vlad" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Add another participant" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Open modal" }));

    expect(
      screen.getByRole("textbox", { name: "Participant username 1" }),
    ).toHaveValue("");
    expect(
      screen.queryByRole("textbox", { name: "Participant username 2" }),
    ).not.toBeInTheDocument();
  });

  it("stores trimmed usernames and auto-detects the recording language", () => {
    renderModal();

    fireEvent.change(screen.getByLabelText("Meeting title"), {
      target: { value: "Design review" },
    });
    fireEvent.change(screen.getByLabelText("Date and time"), {
      target: { value: "2026-09-23T17:00" },
    });
    fireEvent.change(
      screen.getByRole("textbox", { name: "Participant username 1" }),
      { target: { value: "  Vlad  " } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Add another participant" }),
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "Participant username 2" }),
      { target: { value: "Yernur" } },
    );
    fireEvent.change(screen.getByLabelText(/Meeting recording/), {
      target: {
        files: [new File(["audio"], "design-review.mp3", { type: "audio/mpeg" })],
      },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    const submitButton = screen.getByRole("button", {
      name: "Start processing",
    });
    fireEvent.submit(submitButton.closest("form")!);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByTestId("newest-participants")).toHaveTextContent(
      "Vlad|Yernur",
    );
    expect(screen.getByTestId("newest-language")).toHaveTextContent("auto");
  });
});
