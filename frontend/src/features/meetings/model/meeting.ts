import { z } from "zod";

export const meetingStatusSchema = z.enum([
  "queued",
  "processing",
  "review_required",
  "approved",
  "failed",
]);

export const processingStageSchema = z.enum([
  "preparing",
  "uploading_to_gpu",
  "transcribing",
  "diarizing",
  "extracting",
  "saving_results",
]);

export const participantSchema = z.object({
  id: z.uuid(),
  displayName: z.string().min(1),
  speakerLabel: z.string().min(1).nullable(),
});

export const transcriptSegmentSchema = z
  .object({
    id: z.uuid(),
    speakerId: z.uuid().nullable(),
    speakerLabel: z.string().min(1),
    machineText: z.string().min(1),
    reviewedText: z.string().min(1),
    language: z.enum(["ru", "kk", "mixed", "unknown"]),
    startedAtMs: z.number().int().nonnegative(),
    endedAtMs: z.number().int().positive(),
    confidence: z.number().min(0).max(1).nullable(),
  })
  .refine((segment) => segment.endedAtMs > segment.startedAtMs, {
    message: "Segment end must be after its start",
    path: ["endedAtMs"],
  });

export const meetingSchema = z.object({
  id: z.uuid(),
  title: z.string().min(1),
  status: meetingStatusSchema,
  processingStage: processingStageSchema.nullable(),
  recordedAt: z.iso.datetime().nullable(),
  createdAt: z.iso.datetime(),
  participantCount: z.number().int().nonnegative(),
  durationSeconds: z.number().int().nonnegative().nullable(),
});

export type Meeting = z.infer<typeof meetingSchema>;
export type MeetingStatus = z.infer<typeof meetingStatusSchema>;
export type ProcessingStage = z.infer<typeof processingStageSchema>;
export type Participant = z.infer<typeof participantSchema>;
export type TranscriptSegment = z.infer<typeof transcriptSegmentSchema>;
