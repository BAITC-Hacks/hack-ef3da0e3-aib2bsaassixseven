"use client";

import { useQuery } from "@tanstack/react-query";

import { getInsights, getMeeting, getTranscript, listMeetings } from "./client";

export const meetingQueryKeys = {
  all: ["meetings"] as const,
  detail: (meetingId: string) => ["meetings", meetingId] as const,
  transcript: (meetingId: string) =>
    ["meetings", meetingId, "transcript"] as const,
  insights: (meetingId: string) =>
    ["meetings", meetingId, "insights"] as const,
};

export function useMeetingsQuery() {
  return useQuery({
    queryKey: meetingQueryKeys.all,
    queryFn: () => listMeetings({ limit: 100 }),
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (meeting) =>
          meeting.status === "queued" || meeting.status === "processing",
      )
        ? 2_000
        : false,
  });
}

export function useMeetingQuery(meetingId: string) {
  return useQuery({
    queryKey: meetingQueryKeys.detail(meetingId),
    queryFn: () => getMeeting(meetingId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "processing" ? 2_000 : false;
    },
    retry: (failureCount, error) => {
      if (
        typeof error === "object" &&
        error !== null &&
        "code" in error &&
        error.code === "meeting_not_found"
      ) {
        return false;
      }
      return failureCount < 2;
    },
  });
}

export function useMeetingResultsQuery(
  meetingId: string,
  enabled: boolean,
) {
  const transcript = useQuery({
    queryKey: meetingQueryKeys.transcript(meetingId),
    queryFn: () => getTranscript(meetingId),
    enabled,
  });
  const insights = useQuery({
    queryKey: meetingQueryKeys.insights(meetingId),
    queryFn: () => getInsights(meetingId),
    enabled,
  });

  return { transcript, insights };
}
