import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Совещания" };

export default function MeetingsPage() {
  return (
    <PageHeader
      action={
        <Link
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--accent-contrast)]"
          href="/meetings/new"
        >
          Новое совещание
        </Link>
      }
      description="Записи, статусы обработки, протоколы и расшифровки."
      title="Совещания"
    />
  );
}
