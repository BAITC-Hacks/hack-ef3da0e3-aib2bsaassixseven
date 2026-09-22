"use client";

import { useActionState, useState } from "react";

import { signIn, signUp } from "@/app/auth/actions";
import { initialAuthState } from "@/app/auth/state";

export function AuthForm() {
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [signInState, signInAction, signInPending] = useActionState(
    signIn,
    initialAuthState,
  );
  const [signUpState, signUpAction, signUpPending] = useActionState(
    signUp,
    initialAuthState,
  );
  const state = mode === "sign-in" ? signInState : signUpState;
  const pending = mode === "sign-in" ? signInPending : signUpPending;
  const action = mode === "sign-in" ? signInAction : signUpAction;

  return (
    <div className="auth-panel">
      <div className="auth-tabs" aria-label="Authentication mode">
        <button
          aria-pressed={mode === "sign-in"}
          className="auth-tab"
          onClick={() => setMode("sign-in")}
          type="button"
        >
          Sign in
        </button>
        <button
          aria-pressed={mode === "sign-up"}
          className="auth-tab"
          onClick={() => setMode("sign-up")}
          type="button"
        >
          Create account
        </button>
      </div>

      <form action={action} className="auth-form">
        <label htmlFor="email">Email</label>
        <input
          autoComplete="email"
          id="email"
          name="email"
          placeholder="team@hackathon.dev"
          required
          type="email"
        />

        <label htmlFor="password">Password</label>
        <input
          autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
          id="password"
          minLength={8}
          name="password"
          required
          type="password"
        />

        <button className="primary-button" disabled={pending} type="submit">
          {pending
            ? "Connecting…"
            : mode === "sign-in"
              ? "Enter launchpad"
              : "Create account"}
        </button>

        <p
          aria-live="polite"
          className={`form-message ${state.status}`}
          role={state.status === "error" ? "alert" : "status"}
        >
          {state.message}
        </p>
      </form>
    </div>
  );
}
