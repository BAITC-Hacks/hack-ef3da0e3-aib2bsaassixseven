"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";

import type { AuthActionState } from "@/features/auth/model/auth-state";
import { publicEnv } from "@/lib/config/public-env";
import { createServerSupabaseClient } from "@/lib/supabase/server";

const credentialsSchema = z.object({
  email: z.email("Введите корректный email."),
  password: z.string().min(8, "Пароль должен содержать минимум 8 символов."),
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
      message: "Supabase не настроен. Используйте демо-вход ниже.",
    };
  }

  const credentials = readCredentials(formData);
  if (!credentials.success) {
    return {
      status: "error",
      message: credentials.error.issues[0]?.message ?? "Проверьте данные.",
    };
  }

  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.signInWithPassword(credentials.data);

  if (error) {
    return { status: "error", message: "Неверный email или пароль." };
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
      message: "Supabase не настроен. Используйте демо-вход ниже.",
    };
  }

  const credentials = readCredentials(formData);
  if (!credentials.success) {
    return {
      status: "error",
      message: credentials.error.issues[0]?.message ?? "Проверьте данные.",
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
      message: "Не удалось создать аккаунт. Проверьте данные и настройки Auth.",
    };
  }

  if (data.session) {
    redirect("/dashboard");
  }

  return {
    status: "success",
    message: "Проверьте почту и подтвердите регистрацию.",
  };
}

export async function continueDemo() {
  if (publicEnv.isSupabaseConfigured) {
    redirect("/login");
  }

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
