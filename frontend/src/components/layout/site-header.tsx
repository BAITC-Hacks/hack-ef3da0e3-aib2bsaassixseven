import Link from "next/link";

import { HeaderNavigation } from "./header-navigation";
import styles from "./site-header.module.scss";

export function SiteHeader({
  action,
  overlay = false,
}: {
  action: React.ReactNode;
  overlay?: boolean;
}) {
  return (
    <header className={styles.header} data-overlay={overlay || undefined}>
      <Link className={styles.brand} href="/" aria-label="Tirke home">
        Tirke
      </Link>
      <HeaderNavigation />
      <div className={styles.action}>{action}</div>
    </header>
  );
}
