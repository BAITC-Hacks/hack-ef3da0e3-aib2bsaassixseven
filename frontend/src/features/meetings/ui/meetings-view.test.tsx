import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DemoWorkspaceProvider } from "@/features/demo-workspace/demo-workspace-provider";
import { WorkspaceHeader } from "@/features/demo-workspace/ui/workspace-header";
import { MeetingsView } from "@/features/meetings/ui/meetings-view";

vi.mock("next/navigation", () => ({
  usePathname: () => "/meetings",
}));

function renderMeetings() {
  return render(
    <DemoWorkspaceProvider
      initialProfile={{
        displayName: "Vlad",
        email: "vlad@example.com",
        role: "Meeting organizer",
        department: "Product team",
      }}
    >
      <WorkspaceHeader />
      <MeetingsView />
    </DemoWorkspaceProvider>,
  );
}

describe("MeetingsView", () => {
  it("keeps one global meeting action and a concise search field", () => {
    renderMeetings();

    expect(
      screen.getAllByRole("button", { name: "New meeting" }),
    ).toHaveLength(1);
    expect(
      screen.queryByRole("button", { name: "Add a recording" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search meetings" })).toHaveAttribute(
      "placeholder",
      "Search",
    );
  });

  it("continues to filter meetings by title", () => {
    renderMeetings();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search meetings" }), {
      target: { value: "budget" },
    });

    expect(
      screen.getByRole("link", { name: "Pilot budget review" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Weekly product sync" }),
    ).not.toBeInTheDocument();
  });
});
