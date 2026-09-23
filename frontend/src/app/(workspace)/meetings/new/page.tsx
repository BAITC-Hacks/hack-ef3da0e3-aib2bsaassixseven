import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Новое совещание" };

export default function NewMeetingPage() {
  return (
    <PageHeader
      description="Форма загрузки записи и настройки участников будет реализована по утверждённому дизайн-референсу."
      title="Новое совещание"
    />
  );
}
