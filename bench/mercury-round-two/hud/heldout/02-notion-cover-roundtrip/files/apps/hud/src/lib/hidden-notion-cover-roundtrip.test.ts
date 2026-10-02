import { describe, expect, it } from "vitest";

import * as mod from "./notion-cover-frontmatter";

const { bannerYFromNotion, uploadedCoverName } = mod;
const notionPositionFromBannerY = (mod as Record<string, unknown>).notionPositionFromBannerY as (
  y: number | null | undefined,
) => number;

describe("notionPositionFromBannerY", () => {
  it("returns the centred default for a missing or unusable value", () => {
    expect(notionPositionFromBannerY(null)).toBe(0.5);
    expect(notionPositionFromBannerY(undefined)).toBe(0.5);
    expect(notionPositionFromBannerY(Number.NaN)).toBe(0.5);
    expect(notionPositionFromBannerY(Number.POSITIVE_INFINITY)).toBe(0.5);
  });

  it("inverts and rounds to three decimals", () => {
    expect(notionPositionFromBannerY(0.041)).toBe(0.959);
    expect(notionPositionFromBannerY(0.4)).toBe(0.6);
    expect(notionPositionFromBannerY(0.12916)).toBe(0.871);
    expect(notionPositionFromBannerY(0)).toBe(1);
  });

  it("clamps out of range values and never returns negative zero", () => {
    expect(notionPositionFromBannerY(-3)).toBe(1);
    expect(notionPositionFromBannerY(7)).toBe(0);
    expect(Object.is(notionPositionFromBannerY(1), 0)).toBe(true);
    expect(Object.is(notionPositionFromBannerY(7), 0)).toBe(true);
  });

  it("round trips every three-decimal position", () => {
    for (let i = 0; i <= 1000; i++) {
      const p = i / 1000;
      expect(notionPositionFromBannerY(bannerYFromNotion(p))).toBe(p);
    }
  });
});

describe("uploadedCoverName", () => {
  it("keeps the existing shape", () => {
    expect(uploadedCoverName("3f2a9c1b04deadbeef", "jpg")).toBe("cover-3f2a9c1b04.jpg");
    expect(uploadedCoverName("0123456789", "png")).toBe("cover-0123456789.png");
  });

  it("lower-cases the hash and normalises the extension", () => {
    expect(uploadedCoverName("3F2A9C1B04DEADBEEF", ".JPEG")).toBe("cover-3f2a9c1b04.jpg");
    expect(uploadedCoverName("ABCDEF0123", " ..WebP ")).toBe("cover-abcdef0123.webp");
    expect(uploadedCoverName("abcdef0123", "GIF")).toBe("cover-abcdef0123.gif");
    expect(uploadedCoverName("abcdef0123", "jpeg")).toBe("cover-abcdef0123.jpg");
  });

  it("rejects a hash that is too short or not hexadecimal", () => {
    expect(() => uploadedCoverName("3f2a9c1b0", "png")).toThrow(RangeError);
    expect(() => uploadedCoverName("", "png")).toThrow(RangeError);
    expect(() => uploadedCoverName("3f2a9c1b0g", "png")).toThrow(RangeError);
    expect(() => uploadedCoverName("3f2a9c1b04deadbeez", "png")).toThrow(RangeError);
    expect(() => uploadedCoverName("../../etc/x", "png")).toThrow(RangeError);
  });

  it("rejects an extension outside the allowed set", () => {
    for (const ext of ["svg", "", ".", "png/../x", "jpe", "html", "p ng"]) {
      expect(() => uploadedCoverName("3f2a9c1b04", ext)).toThrow(RangeError);
    }
  });
});
