import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DemoWorkspaceProvider } from "@/features/demo-workspace/demo-workspace-provider";
import { MeetingDetailView } from "@/features/meetings/ui/meeting-detail-view";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function renderMeeting(meetingId: string) {
  return render(
    <DemoWorkspaceProvider
      initialProfile={{
        displayName: "Vlad",
        email: "vlad@example.com",
        role: "Meeting organizer",
        department: "Product team",
      }}
    >
      <MeetingDetailView meetingId={meetingId} />
    </DemoWorkspaceProvider>,
  );
}

describe("MeetingDetailView", () => {
  it("separates approved minutes into keyboard-operable tabs", () => {
    renderMeeting("weekly-product-sync");

    const summaryTab = screen.getByRole("tab", { name: "Summary" });
    const tasksTab = screen.getByRole("tab", { name: "Tasks" });
    const transcriptTab = screen.getByRole("tab", {
      name: "Full transcript",
    });

    expect(summaryTab).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("tabpanel", { name: "Summary" }),
    ).toBeInTheDocument();

    fireEvent.keyDown(summaryTab, { key: "ArrowRight" });
    expect(tasksTab).toHaveAttribute("aria-selected", "true");
    expect(tasksTab).toHaveFocus();
    expect(
      screen.getByText("Finish the protocol review interface"),
    ).toBeInTheDocument();

    fireEvent.click(transcriptTab);
    expect(transcriptTab).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByText(
        "Давайте до пятницы закончим интерфейс проверки протокола и покажем его всей команде.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeDisabled();
  });

  it("keeps draft edits across tabs and blocks PDF before approval", () => {
    renderMeeting("budget-review");

    const summary = screen.getByRole("textbox", { name: "Meeting summary" });
    fireEvent.change(summary, { target: { value: "Updated review summary" } });
    fireEvent.click(screen.getByRole("tab", { name: "Tasks" }));
    fireEvent.click(screen.getByRole("tab", { name: "Summary" }));

    expect(screen.getByDisplayValue("Updated review summary")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeDisabled();
  });
});
