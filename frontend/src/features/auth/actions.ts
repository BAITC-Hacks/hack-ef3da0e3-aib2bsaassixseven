"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";

import type { AuthActionState } from "@/features/auth/model/auth-state";
import { publicEnv } from "@/lib/config/public-env";
import { createServerSupabaseClient } from "@/lib/supabase/server";

const credentialsSchema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
});

function readCredentials(formData: FormData) {
  return credentialsSchema.safeParse({
    email: String(formData.get("email") ?? "").trim(),
    password: String(formData.get("password") ?? ""),
  });
}

export async function signIn(
  _previousState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  if (!publicEnv.isSupabaseConfigured) {
    return {
      status: "error",
      message: "Supabase is not configured. Use demo access below.",
    };
  }

  const credentials = readCredentials(formData);
  if (!credentials.success) {
    return {
      status: "error",
      message: credentials.error.issues[0]?.message ?? "Check your details.",
    };
  }

  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.signInWithPassword(credentials.data);

  if (error) {
    return { status: "error", message: "Incorrect email or password." };
  }

  redirect("/dashboard");
}

export async function signUp(
  _previousState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  if (!publicEnv.isSupabaseConfigured) {
    return {
      status: "error",
      message: "Supabase is not configured. Use demo access below.",
    };
  }

  const credentials = readCredentials(formData);
  if (!credentials.success) {
    return {
      status: "error",
      message: credentials.error.issues[0]?.message ?? "Check your details.",
    };
  }

  const displayName = String(formData.get("displayName") ?? "").trim();
  const supabase = await createServerSupabaseClient();
  const { data, error } = await supabase.auth.signUp({
    ...credentials.data,
    options: {
      data: { display_name: displayName || null },
      emailRedirectTo: new URL(
        "/auth/confirm",
        publicEnv.NEXT_PUBLIC_SITE_URL,
      ).toString(),
    },
  });

  if (error) {
    return {
      status: "error",
      message: "We couldn't create the account. Check your details and Auth configuration.",
    };
  }

  if (data.session) {
    redirect("/dashboard");
  }

  return {
    status: "success",
    message: "Check your inbox to confirm your account.",
  };
}

export async function continueDemo() {
  const cookieStore = await cookies();
  cookieStore.set("tirke-demo-session", "active", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  redirect("/dashboard");
}

export async function signOut() {
  const cookieStore = await cookies();
  cookieStore.delete("tirke-demo-session");

  if (publicEnv.isSupabaseConfigured) {
    const supabase = await createServerSupabaseClient();
    await supabase.auth.signOut();
  }

  redirect("/login");
}
