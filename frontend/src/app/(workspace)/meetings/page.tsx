import type { Metadata } from "next";

import { MeetingsView } from "@/features/meetings/ui/meetings-view";

export const metadata: Metadata = { title: "Совещания" };

export default function MeetingsPage() {
  return <MeetingsView />;
}
