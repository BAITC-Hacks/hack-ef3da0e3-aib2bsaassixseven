import { describe, expect, it } from "vitest";

import { transcriptSegmentSchema } from "./meeting-schema";

describe("transcriptSegmentSchema", () => {
  it("accepts a mixed-language diarized segment", () => {
    const segment = transcriptSegmentSchema.parse({
      id: "6b1e810d-c243-4cc8-92e5-01302fd4da82",
      speakerId: null,
      speakerLabel: "SPEAKER_01",
      text: "Ертеңге дейін отчётты жіберіңіз.",
      language: "mixed",
      startedAtMs: 1_250,
      endedAtMs: 4_400,
      confidence: 0.87,
    });

    expect(segment.language).toBe("mixed");
  });
});
