import { describe, expect, it } from "vitest";

import * as mod from "./vault-database-values";

const { numberOf, dateOf } = mod;
const durationOf = (mod as Record<string, unknown>).durationOf as (value: string) => number | null;

describe("numberOf additions", () => {
  it("reads accounting negatives", () => {
    expect(numberOf("(1,234.50)")).toBe(-1234.5);
    expect(numberOf("(12%)")).toBe(-12);
    expect(numberOf("( 3 )")).toBe(-3);
    expect(numberOf(" (1.234,5 €) ")).toBe(-1234.5);
    expect(Math.abs(numberOf("(0)") ?? 1)).toBe(0);
  });

  it("rejects a signed value inside parentheses and partial parentheses", () => {
    expect(numberOf("(-3)")).toBeNull();
    expect(numberOf("(+3)")).toBeNull();
    expect(numberOf("(\u22123)")).toBeNull();
    expect(numberOf("(3")).toBeNull();
    expect(numberOf("3)")).toBeNull();
    expect(numberOf("(3) apples")).toBeNull();
    expect(numberOf("()")).toBeNull();
  });

  it("reads the Unicode minus", () => {
    expect(numberOf("\u22123,5")).toBe(-3.5);
    expect(numberOf("\u2212 12 %")).toBe(-12);
    expect(numberOf("\u22121.234,5 €")).toBe(-1234.5);
  });

  it("removes apostrophe thousands separators", () => {
    expect(numberOf("1'234.5")).toBe(1234.5);
    expect(numberOf("12\u2019000")).toBe(12000);
    expect(numberOf("-1'000'000")).toBe(-1000000);
  });

  it("keeps everything it read before", () => {
    expect(numberOf("1.234,5 €")).toBe(1234.5);
    expect(numberOf("12%")).toBe(12);
    expect(numberOf("-3.5")).toBe(-3.5);
    expect(numberOf("1,5")).toBe(1.5);
    expect(numberOf("1,500")).toBe(1500);
    expect(numberOf("")).toBeNull();
    expect(numberOf("abc")).toBeNull();
    expect(dateOf("2024-03-01")).toBe(Date.parse("2024-03-01"));
  });
});

describe("durationOf", () => {
  it.each([
    ["1h 30m", 5400],
    ["90m", 5400],
    ["1.5h", 5400],
    ["2d", 172800],
    ["1D 2H 3M 4S", 93784],
    ["45s", 45],
    ["0.5s", 0.5],
    ["1h30m", 5400],
    ["  2h   15s ", 7215],
    ["1d 1s", 86401],
    ["0m", 0],
    ["0.25h", 900],
  ])("unit form %j", (value, seconds) => {
    expect(durationOf(value)).toBeCloseTo(seconds, 9);
  });

  it.each([
    ["1:30:00", 5400],
    ["2:05", 125],
    ["100:00", 6000],
    ["0:00:07", 7],
    ["12:34:56", 45296],
    [" 0:59 ", 59],
  ])("clock form %j", (value, seconds) => {
    expect(durationOf(value)).toBe(seconds);
  });

  it.each([
    "",
    "   ",
    "1h1h",
    "30m 1h",
    "1s 1m",
    "1:60",
    "1:5",
    "1:00:00:00",
    "1:60:00",
    "-5m",
    "5",
    "5 m",
    "1h30",
    "abc",
    "1.h",
    ".5h",
    "1h,30m",
    "1w",
    ":30",
    "1:30:0",
  ])("rejects %j", (value) => {
    expect(durationOf(value)).toBeNull();
  });
});
