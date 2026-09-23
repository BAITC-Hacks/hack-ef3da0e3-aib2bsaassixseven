import { z } from "zod";

const nonBlankTextSchema = z
  .string()
  .min(1)
  .refine((value) => value.trim().length > 0, "Text must not be blank");

const personNameSchema = z
  .string()
  .min(1)
  .max(100)
  .refine((value) => value.trim().length > 0, "Name must not be blank");

export const meetingIdSchema = z.uuid();
export const speakerIdSchema = z.string().regex(/^speaker_[1-9][0-9]*$/);

export const meetingStatusSchema = z.enum([
  "queued",
  "processing",
  "review_required",
  "approved",
  "failed",
]);

export const meetingStageSchema = z.enum([
  "uploading_to_gpu",
  "ingesting",
  "transcribing",
  "diarizing",
  "analyzing",
  "saving_results",
  "exporting",
]);

export const meetingLanguageHintSchema = z.enum(["auto", "ru", "kk", "mixed"]);

const ordinaryMeetingSourceSchema = z
  .object({
    kind: z.enum(["uploaded_audio", "browser_recording"]),
    label: z.null().optional(),
    fixture_id: z.null().optional(),
  })
  .strict();

const demoMeetingSourceSchema = z
  .object({
    kind: z.literal("demo_fixture"),
    label: z.literal("Подготовленный пример · обработка выполнена заранее"),
    fixture_id: nonBlankTextSchema,
  })
  .strict();

export const meetingSourceSchema = z.discriminatedUnion("kind", [
  ordinaryMeetingSourceSchema,
  demoMeetingSourceSchema,
]);

export const meetingFailureSchema = z
  .object({
    code: z.enum([
      "invalid_audio",
      "processing_failed",
      "storage_failed",
      "source_expired",
      "gpu_unavailable",
      "invalid_result",
    ]),
    message: nonBlankTextSchema,
  })
  .strict();

export const meetingSchema = z
  .object({
    id: meetingIdSchema,
    title: nonBlankTextSchema.max(120),
    meeting_date: z.iso.date(),
    timezone: nonBlankTextSchema,
    participants: z.array(personNameSchema).max(30),
    recording_notice_confirmed: z.literal(true),
    language_hint: meetingLanguageHintSchema,
    created_at: z.iso.datetime({ offset: true }),
    updated_at: z.iso.datetime({ offset: true }),
    attempt: z.number().int().positive(),
    revision: z.number().int().nonnegative(),
    status: meetingStatusSchema,
    stage: meetingStageSchema.nullable(),
    source_available: z.boolean(),
    cleanup_status: z.enum(["pending", "deleted", "expired"]),
    temporary_expires_at: z.iso.datetime({ offset: true }).nullable(),
    source: meetingSourceSchema,
    failure: meetingFailureSchema.nullable(),
  })
  .strict();

export const meetingPageSchema = z
  .object({
    items: z.array(meetingSchema),
    next_cursor: z.string().min(1).max(256).nullable(),
  })
  .strict();

export const speakerSchema = z
  .object({
    speaker_id: speakerIdSchema,
    display_name: personNameSchema.nullable(),
    identity_status: z.enum(["unreviewed", "named", "unknown"]),
  })
  .strict()
  .superRefine((speaker, context) => {
    const hasName = speaker.display_name !== null;
    if ((speaker.identity_status === "named") !== hasName) {
      context.addIssue({
        code: "custom",
        message: "Only named speakers can have a display name",
        path: ["display_name"],
      });
    }
  });

export const transcriptSegmentSchema = z
  .object({
    id: z.uuid(),
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().nonnegative(),
    speaker_id: speakerIdSchema,
    language: z.enum(["ru", "kk", "unknown"]),
    text: nonBlankTextSchema,
    edited: z.boolean(),
  })
  .strict()
  .refine((segment) => segment.end_ms > segment.start_ms, {
    message: "Segment end must be after its start",
    path: ["end_ms"],
  });

export const transcriptSchema = z
  .object({
    schema_version: z.literal(1),
    meeting_id: meetingIdSchema,
    revision: z.number().int().nonnegative(),
    speakers: z.array(speakerSchema),
    segments: z.array(transcriptSegmentSchema),
  })
  .strict()
  .superRefine((transcript, context) => {
    const speakerIds = transcript.speakers.map((speaker) => speaker.speaker_id);
    const knownSpeakers = new Set(speakerIds);
    if (knownSpeakers.size !== speakerIds.length) {
      context.addIssue({
        code: "custom",
        message: "Speaker IDs must be unique",
        path: ["speakers"],
      });
    }

    const segmentIds = transcript.segments.map((segment) => segment.id);
    if (new Set(segmentIds).size !== segmentIds.length) {
      context.addIssue({
        code: "custom",
        message: "Segment IDs must be unique",
        path: ["segments"],
      });
    }

    let previousStart = -1;
    transcript.segments.forEach((segment, index) => {
      if (!knownSpeakers.has(segment.speaker_id)) {
        context.addIssue({
          code: "custom",
          message: "Segment references an unknown speaker",
          path: ["segments", index, "speaker_id"],
        });
      }
      if (segment.start_ms < previousStart) {
        context.addIssue({
          code: "custom",
          message: "Segments must be ordered by start time",
          path: ["segments", index, "start_ms"],
        });
      }
      previousStart = segment.start_ms;
    });
  });

export const evidenceSchema = z
  .object({
    segment_id: z.uuid(),
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().nonnegative(),
  })
  .strict()
  .refine((evidence) => evidence.end_ms > evidence.start_ms, {
    message: "Evidence end must be after its start",
    path: ["end_ms"],
  });

export const summaryItemSchema = z
  .object({
    id: z.uuid(),
    text: nonBlankTextSchema,
    evidence: z.array(evidenceSchema).min(1),
  })
  .strict();

export const actionItemSchema = summaryItemSchema
  .extend({
    assignee_speaker_id: speakerIdSchema.nullable(),
    assignee_name: personNameSchema.nullable(),
    due_date: z.iso.date().nullable(),
    due_date_text: nonBlankTextSchema.nullable(),
  })
  .superRefine((item, context) => {
    if (item.assignee_speaker_id !== null && item.assignee_name !== null) {
      context.addIssue({
        code: "custom",
        message: "Choose either a speaker or an external assignee",
        path: ["assignee_name"],
      });
    }
  });

export const insightsSchema = z
  .object({
    schema_version: z.literal(1),
    meeting_id: meetingIdSchema,
    revision: z.number().int().nonnegative(),
    summary: z.array(summaryItemSchema),
    action_items: z.array(actionItemSchema),
  })
  .strict()
  .superRefine((insights, context) => {
    for (const [field, items] of [
      ["summary", insights.summary],
      ["action_items", insights.action_items],
    ] as const) {
      const identifiers = items.map((item) => item.id);
      if (new Set(identifiers).size !== identifiers.length) {
        context.addIssue({
          code: "custom",
          message: "Insight IDs must be unique",
          path: [field],
        });
      }
    }
  });

export const segmentEditSchema = z
  .object({
    segment_id: z.uuid(),
    text: nonBlankTextSchema.nullable().optional(),
    speaker_id: speakerIdSchema.nullable().optional(),
  })
  .strict()
  .refine(
    (edit) => edit.text != null || edit.speaker_id != null,
    "A segment edit needs text or a speaker",
  );

export const reviewRequestSchema = z
  .object({
    base_revision: z.number().int().nonnegative(),
    speaker_mappings: z.array(speakerSchema),
    segment_edits: z.array(segmentEditSchema),
    summary: z.array(summaryItemSchema),
    action_items: z.array(actionItemSchema),
  })
  .strict()
  .superRefine((review, context) => {
    const speakerIds = review.speaker_mappings.map((item) => item.speaker_id);
    if (new Set(speakerIds).size !== speakerIds.length) {
      context.addIssue({
        code: "custom",
        message: "Speaker mappings must be unique",
        path: ["speaker_mappings"],
      });
    }

    const segmentIds = review.segment_edits.map((item) => item.segment_id);
    if (new Set(segmentIds).size !== segmentIds.length) {
      context.addIssue({
        code: "custom",
        message: "Segment edits must be unique",
        path: ["segment_edits"],
      });
    }
  });

export const reviewResponseSchema = z
  .object({
    revision: z.number().int().positive(),
    status: z.literal("review_required"),
  })
  .strict();

export const approvalRequestSchema = z
  .object({ base_revision: z.number().int().nonnegative() })
  .strict();

export const meetingUploadMetadataSchema = z
  .object({
    title: nonBlankTextSchema.max(120),
    meeting_date: z.iso.date(),
    timezone: nonBlankTextSchema,
    participants: z.array(personNameSchema).max(30),
    recording_notice_confirmed: z.literal(true),
    language_hint: meetingLanguageHintSchema.default("auto"),
    source_kind: z.enum(["uploaded_audio", "browser_recording"]).default("uploaded_audio"),
  })
  .strict()
  .superRefine((metadata, context) => {
    if (new Set(metadata.participants).size !== metadata.participants.length) {
      context.addIssue({
        code: "custom",
        message: "Participants must be unique",
        path: ["participants"],
      });
    }
  });

export const meetingListParamsSchema = z
  .object({
    limit: z.number().int().min(1).max(100).optional(),
    cursor: z.string().min(1).max(256).optional(),
  })
  .strict();

export const meetingApiErrorCodeSchema = z.enum([
  "invalid_request",
  "meeting_not_found",
  "invalid_state",
  "file_too_large",
  "unsupported_media_type",
  "storage_failed",
  "attempts_exhausted",
  "source_expired",
  "cleanup_pending",
  "delete_failed",
  "stale_revision",
  "review_required",
  "export_failed",
  "queue_unavailable",
  "gpu_unavailable",
  "invalid_result",
]);

export const meetingApiErrorPayloadSchema = z
  .object({
    detail: nonBlankTextSchema,
    code: meetingApiErrorCodeSchema,
  })
  .strict();

export type Meeting = z.infer<typeof meetingSchema>;
export type MeetingPage = z.infer<typeof meetingPageSchema>;
export type MeetingStatus = z.infer<typeof meetingStatusSchema>;
export type MeetingStage = z.infer<typeof meetingStageSchema>;
export type Transcript = z.infer<typeof transcriptSchema>;
export type TranscriptSpeaker = z.infer<typeof speakerSchema>;
export type TranscriptSegment = z.infer<typeof transcriptSegmentSchema>;
export type Insights = z.infer<typeof insightsSchema>;
export type SummaryItem = z.infer<typeof summaryItemSchema>;
export type ActionItem = z.infer<typeof actionItemSchema>;
export type ReviewRequest = z.input<typeof reviewRequestSchema>;
export type ReviewResponse = z.infer<typeof reviewResponseSchema>;
export type MeetingUploadMetadata = z.input<typeof meetingUploadMetadataSchema>;
export type MeetingListParams = z.input<typeof meetingListParamsSchema>;
export type MeetingApiDomainErrorCode = z.infer<typeof meetingApiErrorCodeSchema>;
