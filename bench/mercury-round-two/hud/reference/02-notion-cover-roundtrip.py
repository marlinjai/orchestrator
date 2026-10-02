import sys
root = sys.argv[1]
p = f"{root}/apps/hud/src/lib/notion-cover-frontmatter.ts"
s = open(p).read()
start = s.index("/** The file name an uploaded cover is saved under")
s = s[:start] + '''/** The inverse of bannerYFromNotion: a missing key is the centred default. */
export function notionPositionFromBannerY(y: number | null | undefined): number {
  if (y == null || !Number.isFinite(y)) return 0.5;
  const clamped = Math.min(1, Math.max(0, y));
  return Math.round((1 - clamped) * 1000) / 1000 + 0;
}

/** The file name an uploaded cover is saved under: unique, so an Obsidian link to it is too. */
export function uploadedCoverName(hashHex: string, ext: string): string {
  if (!/^[0-9a-f]{10,}$/i.test(hashHex)) throw new RangeError("hashHex must be at least ten hexadecimal digits");
  let e = ext.trim().replace(/^\\.+/, "").toLowerCase();
  if (e === "jpeg") e = "jpg";
  if (!["png", "jpg", "webp", "gif"].includes(e)) throw new RangeError(`unsupported cover extension: ${ext}`);
  return `cover-${hashHex.slice(0, 10).toLowerCase()}.${e}`;
}
'''
open(p, "w").write(s)
