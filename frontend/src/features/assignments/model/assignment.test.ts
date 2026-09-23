import { describe, expect, it } from "vitest";

import { assignmentSchema } from "./assignment";

describe("assignmentSchema", () => {
  it("preserves unknown owners and deadlines for human clarification", () => {
    const assignment = assignmentSchema.parse({
      id: "94ae3126-5d44-477c-864b-a6128d279adb",
      meetingId: "9b9246fd-9e31-479e-8493-d24b241a8c0f",
      actionText: "Подготовить итоговый отчёт",
      assigneeName: null,
      dueAt: null,
      dueText: null,
      origin: "machine",
      reviewState: "pending",
      requiresClarification: true,
      evidence: {
        transcriptSegmentId: "cf7661c8-58a3-476d-8198-c906f53e84dd",
        quote: "Нужно подготовить итоговый отчёт.",
        startedAtMs: 12_000,
        endedAtMs: 15_400,
      },
    });

    expect(assignment.assigneeName).toBeNull();
    expect(assignment.requiresClarification).toBe(true);
  });
});
