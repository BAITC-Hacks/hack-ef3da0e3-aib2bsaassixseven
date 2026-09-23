import type { Metadata } from "next";

import { DashboardView } from "@/features/dashboard/ui/dashboard-view";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return <DashboardView />;
}
