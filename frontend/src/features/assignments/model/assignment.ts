import { z } from "zod";

export const assignmentEvidenceSchema = z
  .object({
    transcriptSegmentId: z.uuid(),
    quote: z.string().min(1),
    startedAtMs: z.number().int().nonnegative(),
    endedAtMs: z.number().int().positive(),
  })
  .refine((evidence) => evidence.endedAtMs > evidence.startedAtMs, {
    message: "Evidence end must be after its start",
    path: ["endedAtMs"],
  });

export const assignmentSchema = z.object({
  id: z.uuid(),
  meetingId: z.uuid(),
  actionText: z.string().min(1),
  assigneeName: z.string().min(1).nullable(),
  dueAt: z.iso.datetime().nullable(),
  dueText: z.string().min(1).nullable(),
  origin: z.enum(["machine", "manual"]),
  reviewState: z.enum(["pending", "confirmed", "edited"]),
  requiresClarification: z.boolean(),
  evidence: assignmentEvidenceSchema.nullable(),
});

export type Assignment = z.infer<typeof assignmentSchema>;
export type AssignmentEvidence = z.infer<typeof assignmentEvidenceSchema>;
