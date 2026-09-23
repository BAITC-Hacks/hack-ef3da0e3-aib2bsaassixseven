import { cookies } from "next/headers";

import { publicEnv } from "@/lib/config/public-env";
import { createServerSupabaseClient } from "@/lib/supabase/server";

export type Viewer = {
  displayName: string;
  email: string;
  isDemo: boolean;
};

export async function getViewer(): Promise<Viewer | null> {
  if (!publicEnv.isSupabaseConfigured) {
    const cookieStore = await cookies();
    if (cookieStore.get("tirke-demo-session")?.value !== "active") {
      return null;
    }
    return {
      displayName: "Vlad",
      email: "demo@tirke.local",
      isDemo: true,
    };
  }

  const supabase = await createServerSupabaseClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) return null;

  const { data: profile } = await supabase
    .from("profiles")
    .select("display_name")
    .eq("id", user.id)
    .maybeSingle();

  return {
    displayName:
      profile?.display_name ||
      user.user_metadata.display_name ||
      user.email?.split("@")[0] ||
      "User",
    email: user.email ?? "",
    isDemo: false,
  };
}
