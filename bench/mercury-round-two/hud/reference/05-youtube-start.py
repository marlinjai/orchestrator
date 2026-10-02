import sys
root = sys.argv[1]
p = f"{root}/apps/hud/src/lib/link-units.ts"
s = open(p).read()
a = """    return id
      ? { provider: "youtube", src: `https://www.youtube-nocookie.com/embed/${id}?rel=0`, video: true }
      : null;
"""
assert a in s
s = s.replace(a, """    if (!id) return null;
    const seconds = (raw: string | null): number => {
      if (raw === null) return 0;
      if (/^\\d+s?$/i.test(raw)) return Number.parseInt(raw, 10);
      const parts = /^(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?$/i.exec(raw);
      if (!parts || (parts[1] === undefined && parts[2] === undefined && parts[3] === undefined)) return 0;
      return Number(parts[1] ?? 0) * 3600 + Number(parts[2] ?? 0) * 60 + Number(parts[3] ?? 0);
    };
    const start = seconds(u.searchParams.get("start")) || seconds(u.searchParams.get("t"));
    return {
      provider: "youtube",
      src: `https://www.youtube-nocookie.com/embed/${id}?rel=0${start > 0 ? `&start=${start}` : ""}`,
      video: true,
    };
""")
open(p, "w").write(s)
