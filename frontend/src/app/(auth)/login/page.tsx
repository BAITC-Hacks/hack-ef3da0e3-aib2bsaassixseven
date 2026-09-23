import type { Metadata } from "next";
import Link from "next/link";

import { AuthForm } from "@/features/auth/ui/auth-form";
import { DitheredShaderBackground } from "@/features/landing/components/dithered-shader";

import styles from "./page.module.scss";

export const metadata: Metadata = { title: "Sign in or create an account" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string | string[] }>;
}) {
  const requestedMode = (await searchParams).mode;
  const initialMode = requestedMode === "sign-up" ? "sign-up" : "sign-in";

  return (
    <main className={styles.page}>
      <DitheredShaderBackground />
      <section className={styles.panel} aria-labelledby="login-title">
        <Link className={styles.brand} href="/">
          Tirke
        </Link>
        <div className={styles.heading}>
          <h1 id="login-title">
            {initialMode === "sign-up"
              ? "Create your account"
              : "Sign in to your workspace"}
          </h1>
          <p>
            {initialMode === "sign-up"
              ? "Create an account to start working with meetings."
              : "Meetings, assignments and approved minutes in one place."}
          </p>
        </div>
        <AuthForm
          allowDemo
          initialMode={initialMode}
        />
      </section>
      <aside className={styles.context} aria-label="About Tirke">
        <p>Russian · Kazakh · Mixed speech</p>
        <strong>Your recording stays inside your team infrastructure.</strong>
      </aside>
    </main>
  );
}
