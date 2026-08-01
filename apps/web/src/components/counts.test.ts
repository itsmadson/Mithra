import { describe, expect, it } from "vitest";
import { isTerminal } from "../lib/counts";

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
