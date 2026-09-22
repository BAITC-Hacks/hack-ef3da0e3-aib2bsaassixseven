import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  UnauthorizedApiError,
  fetchCurrentUser,
  type MeResponse,
} from "@/lib/api";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

import { ApiStatus } from "./api-status";

vi.mock("@/lib/supabase/client", () => ({
  createBrowserSupabaseClient: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, fetchCurrentUser: vi.fn() };
});

const meFixture: MeResponse = {
  user: {
    id: "11111111-1111-4111-8111-111111111111",
    email: "hacker@example.com",
    role: "authenticated",
  },
  profile: {
    id: "11111111-1111-4111-8111-111111111111",
    display_name: "Hacker",
    created_at: "2026-09-22T00:00:00Z",
    updated_at: "2026-09-22T00:00:00Z",
  },
};

function sessionClient(accessToken: string | null = "access-token") {
  return {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: {
          session: accessToken ? { access_token: accessToken } : null,
        },
        error: null,
      }),
    },
  };
}

describe("ApiStatus", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(createBrowserSupabaseClient).mockReturnValue(
      sessionClient() as never,
    );
  });

  it("shows a loading state while checking FastAPI", () => {
    vi.mocked(fetchCurrentUser).mockReturnValue(new Promise(() => {}));

    render(<ApiStatus />);

    expect(screen.getByText("Checking protected API…")).toBeInTheDocument();
  });

  it("renders the authenticated profile", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(meFixture);

    render(<ApiStatus />);

    expect(await screen.findByText("Hacker")).toBeInTheDocument();
    expect(screen.getByText("hacker@example.com")).toBeInTheDocument();
  });

  it("links back to login when the session is rejected", async () => {
    vi.mocked(fetchCurrentUser).mockRejectedValue(new UnauthorizedApiError());

    render(<ApiStatus />);

    expect(await screen.findByText("Session expired")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("retries after FastAPI is unavailable", async () => {
    vi.mocked(fetchCurrentUser)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(meFixture);

    render(<ApiStatus />);

    expect(await screen.findByText("FastAPI is offline")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry connection" }));

    expect(await screen.findByText("Hacker")).toBeInTheDocument();
    expect(fetchCurrentUser).toHaveBeenCalledTimes(2);
  });
});
