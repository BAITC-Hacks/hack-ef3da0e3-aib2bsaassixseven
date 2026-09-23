import Link from "next/link";

import styles from "./button-link.module.scss";

export function ButtonLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link className={styles.buttonLink} href={href}>
      {children}
    </Link>
  );
}
