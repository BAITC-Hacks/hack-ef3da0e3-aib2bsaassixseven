import type { Metadata } from "next";

import { MeetingDetailView } from "@/features/meetings/ui/meeting-detail-view";

export const metadata: Metadata = { title: "Meeting minutes" };

export default async function MeetingDetailPage({
  params,
}: {
  params: Promise<{ meetingId: string }>;
}) {
  const { meetingId } = await params;

  return <MeetingDetailView meetingId={meetingId} />;
}
