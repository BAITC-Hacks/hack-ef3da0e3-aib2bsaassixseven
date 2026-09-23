import { createBrowserClient } from "@supabase/ssr";

import { publicEnv } from "@/lib/config/public-env";

export function createBrowserSupabaseClient() {
  return createBrowserClient(
    publicEnv.NEXT_PUBLIC_SUPABASE_URL,
    publicEnv.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  );
}
