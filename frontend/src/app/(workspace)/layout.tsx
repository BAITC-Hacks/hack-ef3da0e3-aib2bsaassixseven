import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { getViewer } from "@/features/auth/server/get-viewer";
import { DemoWorkspaceProvider } from "@/features/demo-workspace/demo-workspace-provider";
import { NewMeetingModal } from "@/features/meetings/ui/new-meeting-modal";

export default async function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const viewer = await getViewer();
  if (!viewer) redirect("/login");

  return (
    <DemoWorkspaceProvider
      initialProfile={{
        displayName: viewer.displayName,
        email: viewer.email,
        role: "Meeting organizer",
        department: "Project team",
      }}
    >
      <AppShell>{children}</AppShell>
      <NewMeetingModal />
    </DemoWorkspaceProvider>
  );
}
