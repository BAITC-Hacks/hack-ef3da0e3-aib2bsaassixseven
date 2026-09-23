import { z } from "zod";

export const meetingStatusSchema = z.enum([
  "draft",
  "uploaded",
  "processing",
  "review",
  "completed",
  "failed",
]);

export const participantSchema = z.object({
  id: z.uuid(),
  displayName: z.string().min(1),
  speakerLabel: z.string().min(1).nullable(),
});

export const transcriptSegmentSchema = z.object({
  id: z.uuid(),
  speakerId: z.uuid().nullable(),
  speakerLabel: z.string().min(1),
  text: z.string().min(1),
  language: z.enum(["ru", "kk", "mixed", "unknown"]),
  startedAtMs: z.number().int().nonnegative(),
  endedAtMs: z.number().int().nonnegative(),
  confidence: z.number().min(0).max(1).nullable(),
});

export const meetingSchema = z.object({
  id: z.uuid(),
  title: z.string().min(1),
  status: meetingStatusSchema,
  recordedAt: z.iso.datetime().nullable(),
  createdAt: z.iso.datetime(),
  participantCount: z.number().int().nonnegative(),
  durationSeconds: z.number().int().nonnegative().nullable(),
});

export type Meeting = z.infer<typeof meetingSchema>;
export type MeetingStatus = z.infer<typeof meetingStatusSchema>;
export type Participant = z.infer<typeof participantSchema>;
export type TranscriptSegment = z.infer<typeof transcriptSegmentSchema>;
