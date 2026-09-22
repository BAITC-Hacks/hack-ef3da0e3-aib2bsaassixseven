import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  UnauthorizedApiError,
  fetchCurrentUser,
  type MeResponse,
} from "./api";

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

describe("fetchCurrentUser", () => {
  it("sends the Supabase token to FastAPI", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(meFixture), {
        headers: { "content-type": "application/json" },
        status: 200,
      }),
    );

    const result = await fetchCurrentUser("access-token", fetcher);

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/me",
      expect.objectContaining({
        cache: "no-store",
        headers: { Authorization: "Bearer access-token" },
      }),
    );
    expect(result).toEqual(meFixture);
  });

  it("identifies an expired or rejected session", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 401 }));

    await expect(fetchCurrentUser("expired", fetcher)).rejects.toBeInstanceOf(
      UnauthorizedApiError,
    );
  });

  it("maps other non-success responses to ApiError", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 503 }));

    await expect(fetchCurrentUser("token", fetcher)).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it("rejects malformed response data", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ user: null }), {
        headers: { "content-type": "application/json" },
        status: 200,
      }),
    );

    await expect(fetchCurrentUser("token", fetcher)).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

