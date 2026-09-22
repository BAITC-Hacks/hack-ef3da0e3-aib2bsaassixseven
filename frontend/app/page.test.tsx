import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("gives the team direct paths into the starter", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", { name: "Ship before the clock runs out." }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open dashboard" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(
      screen.getByRole("link", { name: "Configure Supabase" }),
    ).toHaveAttribute("href", "#setup");
  });
});

