import { describe, expect, it } from "vitest";
import { MASHHAD_CENTER, normalizeBbox } from "../lib/bbox";

describe("normalizeBbox", () => {
  it("orders corners west,south,east,north regardless of drag direction", () => {
    const topRightToBottomLeft = normalizeBbox([59.64, 36.33], [59.6, 36.29]);
    const bottomLeftToTopRight = normalizeBbox([59.6, 36.29], [59.64, 36.33]);
    expect(topRightToBottomLeft).toEqual(bottomLeftToTopRight);
  });

  it("produces west < east and south < north", () => {
    const [w, s, e, n] = normalizeBbox([59.64, 36.29], [59.6, 36.33]);
    expect(w).toBeLessThan(e);
    expect(s).toBeLessThan(n);
  });

  it("centers on Mashhad", () => {
    expect(MASHHAD_CENTER[0]).toBeCloseTo(59.606, 2);
    expect(MASHHAD_CENTER[1]).toBeCloseTo(36.297, 2);
  });
});
