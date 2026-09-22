import { beforeEach, describe, expect, it, vi } from "vitest";

import { createServerSupabaseClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

import { signIn, signOut, signUp } from "./actions";
import { initialAuthState } from "./state";

vi.mock("@/lib/supabase/server", () => ({
  createServerSupabaseClient: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
}));

const auth = {
  signInWithPassword: vi.fn(),
  signOut: vi.fn(),
  signUp: vi.fn(),
};

function credentials(password = "eightchars") {
  const formData = new FormData();
  formData.set("email", "hacker@example.com");
  formData.set("password", password);
  return formData;
}

describe("auth actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(createServerSupabaseClient).mockResolvedValue({ auth } as never);
    auth.signInWithPassword.mockResolvedValue({ error: null });
    auth.signUp.mockResolvedValue({ data: { session: null }, error: null });
    auth.signOut.mockResolvedValue({ error: null });
  });

  it("signs in with the submitted credentials", async () => {
    await signIn(initialAuthState, credentials());

    expect(auth.signInWithPassword).toHaveBeenCalledWith({
      email: "hacker@example.com",
      password: "eightchars",
    });
    expect(redirect).toHaveBeenCalledWith("/dashboard");
  });

  it("rejects passwords shorter than eight characters", async () => {
    const result = await signIn(initialAuthState, credentials("short"));

    expect(result).toEqual({
      status: "error",
      message: "Password must contain at least 8 characters.",
    });
    expect(auth.signInWithPassword).not.toHaveBeenCalled();
  });

  it("returns a safe message for rejected credentials", async () => {
    auth.signInWithPassword.mockResolvedValue({
      error: { message: "Invalid login credentials" },
    });

    const result = await signIn(initialAuthState, credentials());

    expect(result).toEqual({
      status: "error",
      message: "Email or password is incorrect.",
    });
  });

  it("registers with the confirmation callback", async () => {
    const result = await signUp(initialAuthState, credentials());

    expect(auth.signUp).toHaveBeenCalledWith({
      email: "hacker@example.com",
      password: "eightchars",
      options: {
        emailRedirectTo: "http://localhost:3000/auth/confirm",
      },
    });
    expect(result).toEqual({
      status: "success",
      message: "Check your inbox to confirm the account.",
    });
  });

  it("signs out and returns to the landing page", async () => {
    await signOut();

    expect(auth.signOut).toHaveBeenCalledOnce();
    expect(redirect).toHaveBeenCalledWith("/");
  });
});
