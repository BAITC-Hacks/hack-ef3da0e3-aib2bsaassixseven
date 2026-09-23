import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DemoWorkspaceProvider } from "@/features/demo-workspace/demo-workspace-provider";
import { WorkspaceHeader } from "@/features/demo-workspace/ui/workspace-header";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("WorkspaceHeader", () => {
  it("keeps meeting navigation and a single profile entry", () => {
    render(
      <DemoWorkspaceProvider
        initialProfile={{
          displayName: "Vlad",
          email: "vlad@example.com",
          role: "Meeting organizer",
          department: "Product team",
        }}
      >
        <WorkspaceHeader />
      </DemoWorkspaceProvider>,
    );

    const navigation = screen.getByRole("navigation", {
      name: "Primary navigation",
    });
    expect(
      within(navigation).getByRole("link", { name: "Dashboard" }),
    ).toHaveAttribute("href", "/dashboard");
    expect(
      within(navigation).getByRole("link", { name: "Meetings" }),
    ).toHaveAttribute("href", "/meetings");
    expect(
      within(navigation).queryByRole("link", { name: "Tasks" }),
    ).not.toBeInTheDocument();
    expect(
      within(navigation).queryByRole("link", { name: "Settings" }),
    ).not.toBeInTheDocument();

    const newMeetingButton = screen.getByRole("button", {
      name: "New meeting",
    });
    expect(newMeetingButton).toBeEnabled();
    expect(within(newMeetingButton).getByText("+")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(screen.getByRole("link", { name: "Tirke home" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByRole("link", { name: "Open profile" })).toHaveAttribute(
      "href",
      "/settings",
    );
    expect(
      screen
        .getAllByRole("link")
        .filter((link) => link.getAttribute("href") === "/settings"),
    ).toHaveLength(1);
  });
});
