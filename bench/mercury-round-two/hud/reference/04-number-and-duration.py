import sys
root = sys.argv[1]
p = f"{root}/apps/hud/src/lib/vault-database-values.ts"
s = open(p).read()
a = """export function numberOf(value: string): number | null {
  let v = value.trim().replace(/[\\s%€$£]/g, "");
  if (!v) return null;
"""
assert a in s, "numberOf head"
s = s.replace(a, """export function numberOf(value: string): number | null {
  let v = value.trim().replace(/[\\s%€$£'\\u2019]/g, "");
  if (!v) return null;
  let negate = false;
  if (v.startsWith("(") && v.endsWith(")")) {
    v = v.slice(1, -1);
    if (!v || /^[+\\-\\u2212]/.test(v)) return null;
    negate = true;
  }
  if (v.startsWith("\\u2212")) v = `-${v.slice(1)}`;
""")
a = """  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
"""
assert a in s, "numberOf tail"
s = s.replace(a, """  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return negate ? -n : n;
}

/** "1h 30m", "90m", "1:30:00" as seconds, or null. */
export function durationOf(value: string): number | null {
  const v = value.trim().toLowerCase();
  if (!v) return null;
  const clock = /^(\\d+):([0-5]\\d)(?::([0-5]\\d))?$/.exec(v);
  if (clock) {
    const [, a, b, c] = clock;
    return c === undefined ? Number(a) * 60 + Number(b) : Number(a) * 3600 + Number(b) * 60 + Number(c);
  }
  const unit = /^(?:(\\d+(?:\\.\\d+)?)d)?\\s*(?:(\\d+(?:\\.\\d+)?)h)?\\s*(?:(\\d+(?:\\.\\d+)?)m)?\\s*(?:(\\d+(?:\\.\\d+)?)s)?$/.exec(v);
  if (!unit || unit.slice(1).every((part) => part === undefined)) return null;
  const [d, h, m, sec] = unit.slice(1).map((part) => (part === undefined ? 0 : Number(part)));
  return d! * 86400 + h! * 3600 + m! * 60 + sec!;
}
""", 1)
open(p, "w").write(s)
