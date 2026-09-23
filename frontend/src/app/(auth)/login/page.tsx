import type { Metadata } from "next";
import Link from "next/link";

import { AuthForm } from "@/features/auth/ui/auth-form";
import { publicEnv } from "@/lib/config/public-env";

import styles from "./page.module.scss";

export const metadata: Metadata = { title: "Вход и регистрация" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string | string[] }>;
}) {
  const requestedMode = (await searchParams).mode;
  const initialMode = requestedMode === "sign-up" ? "sign-up" : "sign-in";

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="login-title">
        <Link className={styles.brand} href="/">
          Tirke
        </Link>
        <div className={styles.heading}>
          <h1 id="login-title">
            {initialMode === "sign-up"
              ? "Создать аккаунт"
              : "Вход в рабочий кабинет"}
          </h1>
          <p>
            {initialMode === "sign-up"
              ? "Зарегистрируйтесь, чтобы начать работу с совещаниями."
              : "Совещания, поручения и проверенные протоколы в одном месте."}
          </p>
        </div>
        <AuthForm
          allowDemo={!publicEnv.isSupabaseConfigured}
          initialMode={initialMode}
        />
      </section>
      <aside className={styles.context} aria-label="О продукте">
        <p>Русский · Қазақша · Смешанная речь</p>
        <strong>Запись остаётся внутри инфраструктуры команды.</strong>
      </aside>
    </main>
  );
}
