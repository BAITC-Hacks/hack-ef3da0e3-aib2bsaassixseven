import type { Metadata } from "next";

import { TasksView } from "@/features/assignments/ui/tasks-view";

export const metadata: Metadata = { title: "Поручения" };

export default function TasksPage() {
  return <TasksView />;
}
