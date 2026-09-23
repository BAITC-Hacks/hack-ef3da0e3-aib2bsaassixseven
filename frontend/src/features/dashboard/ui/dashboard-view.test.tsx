import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  DashboardView,
  dashboardStatusLabel,
} from "@/features/dashboard/ui/dashboard-view";
import { DemoWorkspaceProvider } from "@/features/demo-workspace/demo-workspace-provider";

function renderDashboard() {
  return render(
    <DemoWorkspaceProvider
      initialProfile={{
        displayName: "Влад",
        email: "vlad@example.com",
        role: "Meeting organizer",
        department: "Product team",
      }}
    >
      <DashboardView />
    </DemoWorkspaceProvider>,
  );
}

describe("DashboardView", () => {
  it("shows an English, meeting-centered dashboard", () => {
    renderDashboard();

    expect(
      screen.getByRole("heading", { name: "Good afternoon, Влад" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Recent meetings" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all" })).toHaveAttribute(
      "href",
      "/meetings",
    );
    expect(screen.queryByRole("link", { name: /tasks/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Upcoming tasks")).not.toBeInTheDocument();
  });

  it("shows participant names instead of task bullets or meeting metadata", () => {
    renderDashboard();

    const meeting = screen.getByRole("article", {
      name: "Weekly product sync",
    });

    expect(
      within(meeting).getByText("Влад, Алия, Ернур, Ерасыл"),
    ).toBeInTheDocument();
    expect(
      within(meeting).queryByText("Finish the protocol review interface"),
    ).not.toBeInTheDocument();
    expect(within(meeting).queryByRole("list")).not.toBeInTheDocument();
    expect(within(meeting).getByText("Closed")).toBeInTheDocument();
    expect(
      within(meeting).getByRole("link", { name: "Weekly product sync" }),
    ).toHaveAttribute("href", "/meetings/weekly-product-sync");
  });

  it("keeps participants visible for queued meetings", () => {
    renderDashboard();

    const meeting = screen.getByRole("article", { name: "Customer interview" });
    expect(within(meeting).getByText("Алия, Заказчик")).toBeInTheDocument();
    expect(within(meeting).getByText("Future")).toBeInTheDocument();
  });
});

describe("dashboardStatusLabel", () => {
  it.each([
    ["queued", "Future"],
    ["processing", "In process"],
    ["review_required", "In process"],
    ["approved", "Closed"],
    ["failed", "Failed"],
  ] as const)("maps %s to %s without changing the domain state", (state, label) => {
    expect(dashboardStatusLabel(state)).toBe(label);
  });
});
