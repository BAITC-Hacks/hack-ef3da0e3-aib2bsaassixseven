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
      <div className={styles.tabs} aria-label="Режим входа">
        <button
          aria-pressed={mode === "sign-in"}
          onClick={() => setMode("sign-in")}
          type="button"
        >
          Войти
        </button>
        <button
          aria-pressed={mode === "sign-up"}
          onClick={() => setMode("sign-up")}
          type="button"
        >
          Регистрация
        </button>
      </div>

      <form
        action={mode === "sign-in" ? signInAction : signUpAction}
        className={styles.form}
      >
        {mode === "sign-up" ? (
          <label>
            Имя
            <input autoComplete="name" name="displayName" type="text" />
          </label>
        ) : null}
        <label>
          Email
          <input autoComplete="email" name="email" required type="email" />
        </label>
        <label>
          Пароль
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
            ? "Проверяем…"
            : mode === "sign-in"
              ? "Войти"
              : "Создать аккаунт"}
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
          <p>Supabase не настроен — можно проверить весь интерфейс локально.</p>
          <button type="submit">Продолжить в демо-режиме</button>
        </form>
      ) : null}
    </div>
  );
}
