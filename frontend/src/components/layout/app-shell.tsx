import Link from "next/link";

import styles from "./app-shell.module.scss";

const navigation = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/meetings", label: "Совещания" },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <Link className={styles.brand} href="/dashboard">
          Hackalem
        </Link>
        <nav aria-label="Основная навигация" className={styles.navigation}>
          <ul className={styles.navigationList}>
            {navigation.map((item) => (
              <li key={item.href}>
                <Link className={styles.navigationLink} href={item.href}>
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <main className={styles.content}>{children}</main>
    </div>
  );
}
