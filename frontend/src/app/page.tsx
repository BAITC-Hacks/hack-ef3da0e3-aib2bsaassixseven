import type { Metadata } from "next";
import Link from "next/link";

import styles from "./page.module.scss";

export const metadata: Metadata = {
  title: "Главная",
  description:
    "Локальная обработка совещаний, расшифровка и подготовка протоколов.",
};

const workspaceLinks = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/meetings", label: "Совещания" },
  { href: "/meetings/new", label: "Новое совещание" },
] as const;

export default function HomePage() {
  return (
    <main className={styles.landing}>
      <div className={styles.background} aria-hidden="true">
        <div className={styles.light} />
        <div className={styles.flutes} />
        <div className={styles.shade} />
      </div>

      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="Hackalem — главная">
          Hackalem
        </Link>

        <nav className={styles.headerNavigation} aria-label="Разделы приложения">
          <Link href="/dashboard">Обзор</Link>
          <Link href="/meetings">Совещания</Link>
          <Link href="/meetings/new">Новая встреча</Link>
        </nav>

        <Link className={styles.workspaceLink} href="/dashboard">
          Открыть кабинет
        </Link>
      </header>

      <nav className={styles.workspaceNavigation} aria-label="Перейти в кабинет">
        <ul>
          {workspaceLinks.map((link) => (
            <li key={link.href}>
              <Link href={link.href}>{link.label}</Link>
            </li>
          ))}
        </ul>
      </nav>

      <p className={styles.welcome}>Добро пожаловать.</p>
    </main>
  );
}
