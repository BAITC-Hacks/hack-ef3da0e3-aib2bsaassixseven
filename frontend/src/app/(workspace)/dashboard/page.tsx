import type { Metadata } from "next";

import { DashboardView } from "@/features/dashboard/ui/dashboard-view";

export const metadata: Metadata = { title: "Обзор" };

export default function DashboardPage() {
  return <DashboardView />;
}
