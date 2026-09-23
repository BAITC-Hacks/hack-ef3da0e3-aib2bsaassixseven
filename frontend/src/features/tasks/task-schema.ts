import { z } from "zod";

export const taskStatusSchema = z.enum([
  "open",
  "in_progress",
  "completed",
  "overdue",
  "cancelled",
]);

export const taskPrioritySchema = z.enum(["low", "normal", "high", "urgent"]);

export const taskSchema = z.object({
  id: z.uuid(),
  meetingId: z.uuid(),
  title: z.string().min(1),
  description: z.string(),
  assigneeParticipantId: z.uuid().nullable(),
  assigneeDisplayName: z.string().min(1).nullable(),
  dueAt: z.iso.datetime().nullable(),
  status: taskStatusSchema,
  priority: taskPrioritySchema,
  sourceSegmentIds: z.array(z.uuid()),
  confidence: z.number().min(0).max(1),
  requiresReview: z.boolean(),
});

export type Task = z.infer<typeof taskSchema>;
export type TaskPriority = z.infer<typeof taskPrioritySchema>;
export type TaskStatus = z.infer<typeof taskStatusSchema>;
