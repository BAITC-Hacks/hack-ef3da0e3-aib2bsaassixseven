import { describe, expect, it } from "vitest";

import { getPublicEnv } from "./env";

describe("getPublicEnv", () => {
  it("returns safe placeholders when Supabase is not configured", () => {
    expect(getPublicEnv({})).toEqual({
      apiUrl: "http://localhost:8000",
      supabasePublishableKey: "replace-with-publishable-key",
      supabaseUrl: "https://example.supabase.co",
      isSupabaseConfigured: false,
    });
  });

  it("returns configured public values", () => {
    expect(
      getPublicEnv({
        NEXT_PUBLIC_API_URL: "https://api.example.com/",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_live",
        NEXT_PUBLIC_SUPABASE_URL: "https://project.supabase.co/",
      }),
    ).toEqual({
      apiUrl: "https://api.example.com",
      supabasePublishableKey: "sb_publishable_live",
      supabaseUrl: "https://project.supabase.co",
      isSupabaseConfigured: true,
    });
  });
});

