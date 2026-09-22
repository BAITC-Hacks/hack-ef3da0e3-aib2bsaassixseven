"use server";

import { redirect } from "next/navigation";

import { createServerSupabaseClient } from "@/lib/supabase/server";

export type AuthActionState = {
  status: "idle" | "error" | "success";
  message: string;
};

export const initialAuthState: AuthActionState = {
  status: "idle",
  message: "",
};

function readCredentials(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!email || !email.includes("@")) {
    return { ok: false, error: "Enter a valid email address." } as const;
  }
  if (password.length < 8) {
    return {
      ok: false,
      error: "Password must contain at least 8 characters.",
    } as const;
  }
  return { ok: true, email, password } as const;
}

export async function signIn(
  previousState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const credentials = readCredentials(formData);
  if (!credentials.ok) {
    return { status: "error", message: credentials.error };
  }

  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.signInWithPassword({
    email: credentials.email,
    password: credentials.password,
  });
  if (error) {
    return { status: "error", message: "Email or password is incorrect." };
  }

  redirect("/dashboard");
  return { status: "success", message: "Signed in." };
}

export async function signUp(
  previousState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const credentials = readCredentials(formData);
  if (!credentials.ok) {
    return { status: "error", message: credentials.error };
  }

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  const supabase = await createServerSupabaseClient();
  const { data, error } = await supabase.auth.signUp({
    email: credentials.email,
    password: credentials.password,
    options: {
      emailRedirectTo: new URL("/auth/confirm", siteUrl).toString(),
    },
  });

  if (error) {
    return { status: "error", message: "Account creation failed." };
  }
  if (data.session) {
    redirect("/dashboard");
  }
  return {
    status: "success",
    message: "Check your inbox to confirm the account.",
  };
}

export async function signOut() {
  const supabase = await createServerSupabaseClient();
  await supabase.auth.signOut();
  redirect("/");
}
