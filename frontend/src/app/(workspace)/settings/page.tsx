import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Настройки" };

export default function SettingsPage() {
  return (
    <PageHeader
      description="Локальные модели, хранение, уведомления и параметры организации."
      title="Настройки"
    />
  );
}
