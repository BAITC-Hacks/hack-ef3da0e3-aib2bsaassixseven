import { describe, expect, it } from "vitest";

import {
  AccessTokenUnavailableError,
  getSupabaseAccessToken,
} from "./access-token";

describe("getSupabaseAccessToken", () => {
  it("returns a non-empty browser session token", async () => {
    const client = {
      auth: {
        getSession: async () => ({
          data: { session: { access_token: "token" } },
          error: null,
        }),
      },
    };
    await expect(getSupabaseAccessToken(client)).resolves.toBe("token");
  });

  it("uses a user-safe error when no session exists", async () => {
    const client = {
      auth: {
        getSession: async () => ({ data: { session: null }, error: null }),
      },
    };
    await expect(getSupabaseAccessToken(client)).rejects.toBeInstanceOf(
      AccessTokenUnavailableError,
    );
  });
});
