import { describe, expect, it } from "vitest";
import { advance, needsRefill } from "../lib/labelQueue";

describe("advance", () => {
  it("moves to the next item", () => {
    expect(advance([1, 2, 3], 0)).toBe(1);
  });

  it("stops at the end rather than wrapping", () => {
    expect(advance([1, 2, 3], 2)).toBe(3);
  });

  it("handles an empty queue", () => {
    expect(advance([], 0)).toBe(0);
  });
});

describe("needsRefill", () => {
  it("asks for more when the queue is exhausted", () => {
    expect(needsRefill([1, 2], 2)).toBe(true);
  });

  it("does not ask while items remain", () => {
    expect(needsRefill([1, 2], 0)).toBe(false);
  });
});
