import { beforeEach, describe, expect, it, vi } from "vitest";

import { createMeetingFromAudio } from "./meetings-api";

const metadata = {
  title: "План запуска",
  meeting_date: "2026-09-23",
  timezone: "Asia/Almaty",
  participants: ["Алия"],
  language_hint: "mixed" as const,
  recording_notice_confirmed: true,
};

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.test");
});

describe("meeting audio upload", () => {
  it("posts recorded WebM to the existing authenticated multipart route", async () => {
    const fetcher = vi.fn(async (_url: string, request: RequestInit) => {
      expect(request.headers).toEqual({ Authorization: "Bearer session-token" });
      const body = request.body as FormData;
      expect(body.get("audio")).toBeInstanceOf(File);
      expect((body.get("audio") as File).name).toBe("meeting-recording.webm");
      expect(JSON.parse(body.get("metadata") as string)).toEqual({
        ...metadata, source_kind: "browser_recording",
      });
      return new Response(JSON.stringify({ id: "meeting-id", status: "queued", source: { kind: "browser_recording" } }), { status: 202 });
    });
    const file = new File(["webm"], "meeting-recording.webm", { type: "audio/webm;codecs=opus" });
    const result = await createMeetingFromAudio(file, metadata, "session-token", "browser_recording", fetcher as typeof fetch);
    expect(result.status).toBe("queued");
    expect(fetcher).toHaveBeenCalledWith("https://api.example.test/api/v1/meetings", expect.any(Object));
  });

  it("keeps upload errors distinct for retry with the same file", async () => {
    const file = new File(["webm"], "meeting-recording.webm", { type: "audio/webm" });
    const fetcher = vi.fn().mockRejectedValue(new TypeError("network offline"));
    await expect(createMeetingFromAudio(file, metadata, "session-token", "browser_recording", fetcher)).rejects.toMatchObject({ code: "network" });
    expect(file.size).toBe(4);
  });

  it("does not send a meeting without an access token", async () => {
    const file = new File(["webm"], "meeting-recording.webm", { type: "audio/webm" });
    const fetcher = vi.fn();
    await expect(createMeetingFromAudio(file, metadata, "", "browser_recording", fetcher)).rejects.toMatchObject({ code: "rejected" });
    expect(fetcher).not.toHaveBeenCalled();
  });
});
