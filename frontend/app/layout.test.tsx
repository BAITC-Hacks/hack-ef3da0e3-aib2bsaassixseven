import { describe, expect, it } from "vitest";

import RootLayout from "./layout";

describe("RootLayout", () => {
  it("declares smooth scroll behavior for Next route transitions", () => {
    const tree = RootLayout({ children: null });

    expect(tree.props["data-scroll-behavior"]).toBe("smooth");
  });
});
