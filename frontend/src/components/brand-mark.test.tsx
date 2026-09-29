import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandMark } from "@/components/brand-mark";

describe("BrandMark", () => {
  it("renders the shared supplied raster brand icon", () => {
    const { container } = render(<BrandMark compact />);

    expect(container.querySelector("img")?.getAttribute("src")).toContain("medsignal-icon.png");
  });
});
