import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Обзор" };

export default function DashboardPage() {
  return (
    <PageHeader
      description="Состояние совещаний и контроль сроков будут собраны на этой странице."
      title="Обзор"
    />
  );
}
