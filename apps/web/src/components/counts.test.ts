import { describe, expect, it } from "vitest";
import { isTerminal, orderedCounts } from "../lib/counts";

describe("orderedCounts", () => {
  it("lists every known class even when the count is zero", () => {
    const rows = orderedCounts({ street_name: 3 });
    expect(rows.map((r) => r.signClass)).toContain("city_entry");
    expect(rows.find((r) => r.signClass === "city_entry")?.count).toBe(0);
  });

  it("keeps the four real classes ahead of unknown", () => {
    const rows = orderedCounts({ unknown: 9, street_name: 1 });
    expect(rows[rows.length - 1].signClass).toBe("unknown");
  });

  it("includes unknown when it is present", () => {
    expect(orderedCounts({ unknown: 2 }).find((r) => r.signClass === "unknown")?.count).toBe(2);
  });
});

describe("isTerminal", () => {
  it("treats succeeded, partial, and failed as terminal", () => {
    expect(isTerminal("succeeded")).toBe(true);
    expect(isTerminal("partial")).toBe(true);
    expect(isTerminal("failed")).toBe(true);
  });

  it("treats queued and running as non-terminal", () => {
    expect(isTerminal("queued")).toBe(false);
    expect(isTerminal("running")).toBe(false);
  });
});
