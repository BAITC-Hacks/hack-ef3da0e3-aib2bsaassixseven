"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./site-header.module.scss";

const navigation = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/meetings", label: "Meetings" },
] as const;

export function HeaderNavigation() {
  const pathname = usePathname();

  return (
    <nav className={styles.navigation} aria-label="Primary navigation">
      {navigation.map((item) => {
        const isActive =
          pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            aria-current={isActive ? "page" : undefined}
            href={item.href}
            key={item.href}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
