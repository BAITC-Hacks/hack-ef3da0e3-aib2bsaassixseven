import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Поручения" };

export default function TasksPage() {
  return (
    <PageHeader
      description="Ответственные, сроки, приоритеты и статусы исполнения поручений."
      title="Поручения"
    />
  );
}
