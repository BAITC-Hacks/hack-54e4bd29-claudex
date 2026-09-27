import { describe, expect, it } from "vitest";

import { centerFor, pointLabel, volumeClass } from "./geography";

describe("map geography", () => {
  it("does not confuse Almaty city with Almaty region", () => {
    expect(centerFor("Алматы", "almaty city")).toEqual([43.24, 76.89]);
    expect(centerFor("Алматинская область", "almaty region")).toEqual([45, 78.3]);
  });

  it("does not place unknown partial names on the map", () => {
    expect(centerFor("Новый алматинский округ", "unknown")).toBeNull();
  });

  it("uses neutral volume classes and explicit states", () => {
    expect(volumeClass(80, 100)).toBe("volume-high");
    expect(volumeClass(null, 100)).toBe("empty");
    expect(pointLabel({ id: "1", name: "Регион", code: "r", value: null, state: "suppressed" })).toBe("Скрыто");
  });
});
