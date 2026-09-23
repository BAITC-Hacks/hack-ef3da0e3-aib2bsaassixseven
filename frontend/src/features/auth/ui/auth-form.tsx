"use client";

import { useActionState, useState } from "react";

import { continueDemo, signIn, signUp } from "@/features/auth/actions";
import { initialAuthState } from "@/features/auth/model/auth-state";

import styles from "./auth-form.module.scss";

type AuthMode = "sign-in" | "sign-up";

export function AuthForm({
  allowDemo,
  initialMode = "sign-in",
}: {
  allowDemo: boolean;
  initialMode?: AuthMode;
}) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
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

  return (
    <div className={styles.auth}>
      <div className={styles.tabs} aria-label="Authentication mode">
        <button
          aria-pressed={mode === "sign-in"}
          onClick={() => setMode("sign-in")}
          type="button"
        >
          Sign in
        </button>
        <button
          aria-pressed={mode === "sign-up"}
          onClick={() => setMode("sign-up")}
          type="button"
        >
          Sign up
        </button>
      </div>

      <form
        action={mode === "sign-in" ? signInAction : signUpAction}
        className={styles.form}
      >
        {mode === "sign-up" ? (
          <label>
            Name
            <input autoComplete="name" name="displayName" type="text" />
          </label>
        ) : null}
        <label>
          Email
          <input autoComplete="email" name="email" required type="email" />
        </label>
        <label>
          Password
          <input
            autoComplete={
              mode === "sign-in" ? "current-password" : "new-password"
            }
            minLength={8}
            name="password"
            required
            type="password"
          />
        </label>
        <button className={styles.submit} disabled={pending} type="submit">
          {pending
            ? "Checking…"
            : mode === "sign-in"
              ? "Sign in"
              : "Create account"}
        </button>
        <p
          aria-live="polite"
          className={styles.message}
          data-status={state.status}
          role={state.status === "error" ? "alert" : "status"}
        >
          {state.message}
        </p>
      </form>

      {allowDemo ? (
        <form action={continueDemo} className={styles.demo}>
          <p>Supabase is not configured. You can explore the full interface locally.</p>
          <button type="submit">Continue in demo mode</button>
        </form>
      ) : null}
    </div>
  );
}
