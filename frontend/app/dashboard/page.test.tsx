import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createServerSupabaseClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

import DashboardPage from "./page";

vi.mock("@/lib/supabase/server", () => ({
  createServerSupabaseClient: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: vi.fn() }));

vi.mock("@/components/api-status", () => ({
  ApiStatus: () => <div>API status module</div>,
}));

vi.mock("@/app/auth/actions", () => ({ signOut: vi.fn() }));

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders verified account context", async () => {
    vi.mocked(createServerSupabaseClient).mockResolvedValue({
      auth: {
        getClaims: vi.fn().mockResolvedValue({
          data: {
            claims: {
              sub: "11111111-1111-4111-8111-111111111111",
              email: "hacker@example.com",
            },
          },
        }),
      },
    } as never);

    render(await DashboardPage());

    expect(
      screen.getByRole("heading", { name: "Build room" }),
    ).toBeInTheDocument();
    expect(screen.getByText("hacker@example.com")).toBeInTheDocument();
    expect(screen.getByText("API status module")).toBeInTheDocument();
  });

  it("redirects requests without verified claims", async () => {
    vi.mocked(createServerSupabaseClient).mockResolvedValue({
      auth: {
        getClaims: vi.fn().mockResolvedValue({ data: { claims: null } }),
      },
    } as never);

    await DashboardPage();

    expect(redirect).toHaveBeenCalledWith("/login");
  });
});
