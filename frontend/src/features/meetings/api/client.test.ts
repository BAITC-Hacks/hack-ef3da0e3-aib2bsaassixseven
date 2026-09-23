import { describe, expect, it, vi } from "vitest";

import { normalizeApiUrl } from "@/lib/config/public-env";

import {
  approveMeeting,
  createMeeting,
  deleteMeeting,
  downloadMeetingPdf,
  getInsights,
  getMeeting,
  getTranscript,
  listMeetings,
  MeetingApiError,
  retryMeeting,
  updateReview,
  type MeetingApiOptions,
} from "./client";

const meetingId = "81df6d39-16dd-4227-98b0-d45e531e091e";
const segmentId = "76424ccb-f8d4-46f2-b7fc-81e888a01775";
const summaryId = "dc2c962f-8914-4fca-932d-5fbbcc4933cb";

const meeting = {
  id: meetingId,
  title: "План запуска",
  meeting_date: "2026-09-23",
  timezone: "Asia/Almaty",
  participants: ["Алия"],
  recording_notice_confirmed: true,
  language_hint: "auto",
  created_at: "2026-09-23T09:00:00Z",
  updated_at: "2026-09-23T09:00:00Z",
  attempt: 1,
  revision: 0,
  status: "queued",
  stage: null,
  source_available: true,
  cleanup_status: "pending",
  temporary_expires_at: "2026-09-24T09:00:00Z",
  source: { kind: "uploaded_audio" },
  failure: null,
} as const;

const transcript = {
  schema_version: 1,
  meeting_id: meetingId,
  revision: 0,
  speakers: [
    { speaker_id: "speaker_1", display_name: null, identity_status: "unreviewed" },
  ],
  segments: [
    {
      id: segmentId,
      start_ms: 100,
      end_ms: 900,
      speaker_id: "speaker_1",
      language: "ru",
      text: "Подготовить план.",
      edited: false,
    },
  ],
} as const;

const insights = {
  schema_version: 1,
  meeting_id: meetingId,
  revision: 0,
  summary: [
    {
      id: summaryId,
      text: "Нужно подготовить план.",
      evidence: [{ segment_id: segmentId, start_ms: 100, end_ms: 900 }],
    },
  ],
  action_items: [],
} as const;

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function options(fetcher: typeof fetch): MeetingApiOptions {
  return {
    apiUrl: "http://localhost:8000",
    fetcher,
    getAccessToken: async () => "session-token",
  };
}

describe("meeting API client", () => {
  it("normalizes both service origins and versioned API URLs", () => {
    expect(normalizeApiUrl("http://localhost:8000")).toBe(
      "http://localhost:8000/api/v1",
    );
    expect(normalizeApiUrl("http://localhost:8000/api/v1/")).toBe(
      "http://localhost:8000/api/v1",
    );
  });

  it("uploads video through the authenticated multipart endpoint", async () => {
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      expect(String(url)).toBe("http://localhost:8000/api/v1/meetings");
      const headers = new Headers(init?.headers);
      expect(headers.get("Authorization")).toBe("Bearer session-token");
      expect(headers.has("Content-Type")).toBe(false);
      const form = init?.body as FormData;
      expect((form.get("audio") as File).name).toBe("meeting.mp4");
      expect(JSON.parse(String(form.get("metadata")))).toMatchObject({
        language_hint: "auto",
        source_kind: "uploaded_audio",
      });
      return json(meeting, 202);
    }) as typeof fetch;

    await expect(
      createMeeting(
        new File(["video"], "meeting.mp4", { type: "video/mp4" }),
        {
          title: meeting.title,
          meeting_date: meeting.meeting_date,
          timezone: meeting.timezone,
          participants: [...meeting.participants],
          recording_notice_confirmed: true,
        },
        options(fetcher),
      ),
    ).resolves.toMatchObject({ id: meetingId });
  });

  it("covers every JSON endpoint with validated responses", async () => {
    const responses = [
      json({ items: [meeting], next_cursor: null }),
      json(meeting),
      json(transcript),
      json(insights),
      json({ revision: 1, status: "review_required" }),
      json({ ...meeting, status: "approved" }),
      json(meeting, 202),
      new Response(null, { status: 204 }),
    ];
    const fetcher = vi.fn(async () => responses.shift()!) as typeof fetch;
    const config = options(fetcher);

    await listMeetings({ limit: 20 }, config);
    await getMeeting(meetingId, config);
    await getTranscript(meetingId, config);
    await getInsights(meetingId, config);
    await updateReview(
      meetingId,
      {
        base_revision: 0,
        speaker_mappings: [
          { speaker_id: "speaker_1", display_name: "Алия", identity_status: "named" },
        ],
        segment_edits: [],
        summary: insights.summary.map((item) => ({
          ...item,
          evidence: item.evidence.map((entry) => ({ ...entry })),
        })),
        action_items: [],
      },
      config,
    );
    await approveMeeting(meetingId, 1, config);
    await retryMeeting(meetingId, config);
    await deleteMeeting(meetingId, config);

    expect(fetcher).toHaveBeenCalledTimes(8);
  });

  it("downloads an authenticated PDF blob and rejects unsafe error payloads", async () => {
    const pdfFetcher = vi.fn(async () =>
      new Response(new Blob(["%PDF-1.7\n%%EOF"], { type: "application/pdf" }), {
        status: 200,
        headers: { "Content-Type": "application/pdf" },
      }),
    ) as typeof fetch;
    await expect(downloadMeetingPdf(meetingId, options(pdfFetcher))).resolves.toHaveProperty(
      "size",
    );

    const errorFetcher = vi.fn(async () =>
      json({ detail: "private backend detail", code: "stale_revision" }, 409),
    ) as typeof fetch;
    await expect(getMeeting(meetingId, options(errorFetcher))).rejects.toMatchObject({
      code: "stale_revision",
      message: "This meeting changed elsewhere. Reload it before saving again.",
    } satisfies Partial<MeetingApiError>);
  });
});
