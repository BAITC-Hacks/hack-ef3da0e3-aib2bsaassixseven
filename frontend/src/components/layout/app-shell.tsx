import { WorkspaceHeader } from "@/features/demo-workspace/ui/workspace-header";

import styles from "./app-shell.module.scss";

export function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={styles.shell}>
      <WorkspaceHeader />
      <main className={styles.content}>{children}</main>
    </div>
  );
}
