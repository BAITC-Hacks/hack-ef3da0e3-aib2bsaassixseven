import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardView } from "@/features/dashboard/ui/dashboard-view";
import { DemoWorkspaceProvider } from "@/features/demo-workspace/demo-workspace-provider";

describe("DashboardView", () => {
  it("shows the signed-in user's next actions and workspace navigation", () => {
    render(
      <DemoWorkspaceProvider
        initialProfile={{
          displayName: "Влад",
          email: "vlad@example.com",
          role: "Организатор совещаний",
          department: "Проектная команда",
        }}
      >
        <DashboardView />
      </DemoWorkspaceProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Добрый день, Влад" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Новое совещание" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Все совещания" }),
    ).toHaveAttribute("href", "/meetings");
    expect(
      screen.getByRole("link", { name: "Все поручения" }),
    ).toHaveAttribute("href", "/tasks");
    expect(screen.getByText("Обсуждение бюджета пилота")).toBeInTheDocument();
  });
});
