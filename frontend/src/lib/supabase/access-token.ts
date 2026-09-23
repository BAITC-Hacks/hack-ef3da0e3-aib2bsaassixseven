import { z } from "zod";

import { createBrowserSupabaseClient } from "@/lib/supabase/client";

const accessTokenSchema = z.string().trim().min(1);

type SessionReader = {
  auth: {
    getSession: () => Promise<{
      data: { session: { access_token: string } | null };
      error: unknown;
    }>;
  };
};

export class AccessTokenUnavailableError extends Error {
  constructor() {
    super("Your session expired. Sign in again and retry.");
    this.name = "AccessTokenUnavailableError";
  }
}

export async function getSupabaseAccessToken(
  client: SessionReader = createBrowserSupabaseClient(),
): Promise<string> {
  const { data, error } = await client.auth.getSession();
  const token = accessTokenSchema.safeParse(data.session?.access_token);

  if (error || !token.success) {
    throw new AccessTokenUnavailableError();
  }

  return token.data;
}

export type AccessTokenProvider = () => Promise<string>;
