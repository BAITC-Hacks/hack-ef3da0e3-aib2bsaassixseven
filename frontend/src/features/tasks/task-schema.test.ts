import { describe, expect, it } from "vitest";

import { taskSchema } from "./task-schema";

describe("taskSchema", () => {
  it("keeps uncertain extraction results in secretary review", () => {
    const task = taskSchema.parse({
      id: "94ae3126-5d44-477c-864b-a6128d279adb",
      meetingId: "9b9246fd-9e31-479e-8493-d24b241a8c0f",
      title: "Подготовить отчёт",
      description: "Собрать итоговые показатели проекта.",
      assigneeParticipantId: null,
      assigneeDisplayName: null,
      dueAt: null,
      status: "open",
      priority: "normal",
      sourceSegmentIds: [],
      confidence: 0.54,
      requiresReview: true,
    });

    expect(task.requiresReview).toBe(true);
  });
});
