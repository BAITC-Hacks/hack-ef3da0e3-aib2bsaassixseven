import type { Metadata } from "next";

import { TasksView } from "@/features/assignments/ui/tasks-view";

export const metadata: Metadata = { title: "Assignments" };

export default function TasksPage() {
  return <TasksView />;
}
