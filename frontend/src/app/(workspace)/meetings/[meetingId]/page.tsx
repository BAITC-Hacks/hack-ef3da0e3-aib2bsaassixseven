import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Протокол совещания" };

export default async function MeetingDetailPage({
  params,
}: {
  params: Promise<{ meetingId: string }>;
}) {
  const { meetingId } = await params;

  return (
    <PageHeader
      description={`Карточка совещания ${meetingId}: обработка, транскрипт, саммари, поручения и экспорт.`}
      title="Протокол совещания"
    />
  );
}
