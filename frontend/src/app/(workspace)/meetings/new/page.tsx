"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useDemoWorkspace } from "@/features/demo-workspace/demo-workspace-provider";

export default function NewMeetingPage() {
  const router = useRouter();
  const { openNewMeeting } = useDemoWorkspace();

  useEffect(() => {
    openNewMeeting();
    router.replace("/meetings");
  }, [openNewMeeting, router]);

  return null;
}
