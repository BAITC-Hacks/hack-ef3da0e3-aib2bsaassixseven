import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";
import { ButtonLink } from "@/components/ui/button-link";

export const metadata: Metadata = { title: "Совещания" };

export default function MeetingsPage() {
  return (
    <PageHeader
      action={
        <ButtonLink href="/meetings/new">
          Новое совещание
        </ButtonLink>
      }
      description="Записи, статусы обработки, протоколы и расшифровки."
      title="Совещания"
    />
  );
}
