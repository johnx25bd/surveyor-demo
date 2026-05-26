import { describe, expect, it } from "vitest";

import { colourFor, GDV, quantileBreaks } from "./palettes";
import { parseFrame } from "./stream";

describe("quantileBreaks", () => {
  it("returns classes-1 inner breaks, sorted and inside the range", () => {
    const breaks = quantileBreaks([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5);
    expect(breaks.length).toBe(4);
    expect([...breaks].sort((a, b) => a - b)).toEqual(breaks);
    expect(breaks[0]).toBeGreaterThan(1);
    expect(breaks[breaks.length - 1]).toBeLessThan(10);
  });

  it("returns nothing for empty input", () => {
    expect(quantileBreaks([], 5)).toEqual([]);
  });

  it("de-duplicates breaks when values tie (collapses empty classes)", () => {
    expect(quantileBreaks([5, 5, 5, 5], 4)).toEqual([5]);
  });

  it("ignores non-finite values", () => {
    const breaks = quantileBreaks([1, 2, NaN, 4, Infinity], 3);
    expect(breaks.every(Number.isFinite)).toBe(true);
  });
});

describe("colourFor", () => {
  const ramp = GDV.sequential.m2;
  const breaks = [10, 20, 30, 40, 50, 60];

  it("maps a value below the first break to the first colour", () => {
    expect(colourFor(0, breaks, ramp)).toBe(ramp[0]);
  });

  it("maps a value above the last break to the last colour", () => {
    expect(colourFor(999, breaks, ramp)).toBe(ramp[ramp.length - 1]);
  });

  it("stays within the ramp for a mid value", () => {
    expect(ramp).toContain(colourFor(35, breaks, ramp));
  });
});

describe("parseFrame", () => {
  it("parses a named event with JSON data", () => {
    expect(parseFrame('event: view\ndata: {"kind":"chart","handle":"ds_1","encoding":{}}')).toEqual({
      event: "view",
      data: { kind: "chart", handle: "ds_1", encoding: {} },
    });
  });

  it("defaults the event name to message", () => {
    expect(parseFrame('data: {"text":"hi"}')).toEqual({ event: "message", data: { text: "hi" } });
  });

  it("returns null with no data line", () => {
    expect(parseFrame("event: ping")).toBeNull();
  });

  it("returns null on malformed JSON rather than throwing", () => {
    expect(parseFrame("event: x\ndata: {nope")).toBeNull();
  });
});
