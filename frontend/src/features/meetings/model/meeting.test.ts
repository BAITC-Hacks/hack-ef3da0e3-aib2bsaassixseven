import { describe, expect, it } from "vitest";

import { transcriptSegmentSchema } from "./meeting";

describe("transcriptSegmentSchema", () => {
  it("accepts a mixed-language diarized segment", () => {
    const segment = transcriptSegmentSchema.parse({
      id: "6b1e810d-c243-4cc8-92e5-01302fd4da82",
      speakerId: null,
      speakerLabel: "SPEAKER_01",
      machineText: "Ертеңге дейін отчётты жіберіңіз.",
      reviewedText: "Ертеңге дейін отчётты жіберіңіз.",
      language: "mixed",
      startedAtMs: 1_250,
      endedAtMs: 4_400,
      confidence: 0.87,
    });

    expect(segment.language).toBe("mixed");
  });

  it("rejects an invalid time range", () => {
    const result = transcriptSegmentSchema.safeParse({
      id: "6b1e810d-c243-4cc8-92e5-01302fd4da82",
      speakerId: null,
      speakerLabel: "SPEAKER_01",
      machineText: "Тест",
      reviewedText: "Тест",
      language: "ru",
      startedAtMs: 4_400,
      endedAtMs: 1_250,
      confidence: null,
    });

    expect(result.success).toBe(false);
  });
});
