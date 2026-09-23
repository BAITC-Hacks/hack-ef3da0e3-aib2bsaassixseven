import { describe, expect, it } from "vitest";

import {
  formatDueDate,
  formatMeetingDate,
} from "@/features/demo-workspace/lib/format";

describe("demo workspace date formatting", () => {
  it("formats meeting timestamps without locale-dependent output", () => {
    expect(formatMeetingDate("2026-09-23T10:00")).toBe(
      "23 Sep 2026 at 10:00",
    );
    expect(formatMeetingDate("2026-09-23T10:00:00+05:00")).toBe(
      "23 Sep 2026 at 10:00",
    );
  });

  it("formats deadlines without shifting the calendar date", () => {
    expect(formatDueDate("2026-09-24")).toBe("24 Sep");
    expect(formatDueDate(null)).toBe("Not set");
  });
});
