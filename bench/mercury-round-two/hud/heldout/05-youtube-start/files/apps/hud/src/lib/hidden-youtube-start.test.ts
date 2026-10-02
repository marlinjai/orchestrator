import { describe, expect, it } from "vitest";

import { embedFor } from "./link-units";

const ID = "dQw4w9WgXcQ";
const base = `https://www.youtube-nocookie.com/embed/${ID}?rel=0`;
const src = (url: string) => embedFor(url)?.src;

describe("YouTube start time", () => {
  it.each([
    [`https://youtu.be/${ID}?t=90`, 90],
    [`https://youtu.be/${ID}?t=90s`, 90],
    [`https://youtu.be/${ID}?t=1m30s`, 90],
    [`https://www.youtube.com/watch?v=${ID}&start=90`, 90],
    [`https://www.youtube.com/watch?v=${ID}&t=2h`, 7200],
    [`https://www.youtube.com/watch?t=1h5s&v=${ID}`, 3605],
    [`https://m.youtube.com/watch?v=${ID}&t=1H2M3S`, 3723],
    [`https://www.youtube.com/shorts/${ID}?t=7`, 7],
    [`https://www.youtube.com/embed/${ID}?start=12`, 12],
    [`https://www.youtube.com/live/${ID}?t=45m`, 2700],
    [`https://youtu.be/${ID}?t=0h0m5s`, 5],
    [`https://youtu.be/${ID}?t=090`, 90],
  ])("%s starts at %d", (url, seconds) => {
    expect(embedFor(url)).toEqual({ provider: "youtube", src: `${base}&start=${seconds}`, video: true });
  });

  it("prefers start over t when start is valid", () => {
    expect(src(`https://youtu.be/${ID}?t=10&start=20`)).toBe(`${base}&start=20`);
    expect(src(`https://youtu.be/${ID}?start=20&t=10`)).toBe(`${base}&start=20`);
  });

  it("falls back to t when start is invalid or zero", () => {
    expect(src(`https://youtu.be/${ID}?start=abc&t=10`)).toBe(`${base}&start=10`);
    expect(src(`https://youtu.be/${ID}?start=0&t=1m`)).toBe(`${base}&start=60`);
  });

  it.each(["", "abc", "1.5", "-10", "30m1h", "1m%2030s", "1h30", "0", "0s", "0h0m0s", "s", "h", "1m1m"])(
    "ignores the invalid or zero value %j",
    (value) => {
      expect(src(`https://youtu.be/${ID}?t=${value}`)).toBe(base);
      expect(src(`https://www.youtube.com/watch?v=${ID}&start=${value}`)).toBe(base);
    },
  );

  it("keeps links without a start time as they were", () => {
    expect(embedFor(`https://www.youtube.com/watch?v=${ID}`)).toEqual({ provider: "youtube", src: base, video: true });
    expect(src(`https://youtu.be/${ID}?si=abcdef&feature=share`)).toBe(base);
  });

  it("still refuses a bad video id", () => {
    expect(embedFor("https://youtu.be/short?t=90")).toBeNull();
    expect(embedFor("https://www.youtube.com/watch?t=90")).toBeNull();
  });

  it("does not touch other providers", () => {
    expect(src("https://vimeo.com/123456?t=90")).toBe("https://player.vimeo.com/video/123456");
    expect(src("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?start=90")).toBe(
      "https://open.spotify.com/embed/track/4uLU6hMCjMI75M1A2tKUQC",
    );
    expect(embedFor("https://example.com/watch?v=dQw4w9WgXcQ&t=90")).toBeNull();
  });
});
