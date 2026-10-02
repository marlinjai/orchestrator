import sys
root = sys.argv[1]
p = f"{root}/apps/hud/src/lib/switch-company.ts"
s = open(p).read()
a = """): Promise<SwitchResult> {
  let res: Response;
"""
assert a in s
s = s.replace(a, """): Promise<SwitchResult> {
  if (tenantId.trim() === "") {
    return { ok: false, retryable: false, message: "No company selected." };
  }
  let res: Response;
""")
a = """  if (res.status === 403) {"""
assert a in s
s = s.replace(a, """  if (res.status === 401) {
    return { ok: false, retryable: false, message: "Your session has expired. Sign in again." };
  }
  if (res.status === 429) {
    const raw = res.headers?.get("retry-after")?.trim() ?? "";
    const seconds = /^\\d+$/.test(raw) ? Number(raw) : 0;
    const when = seconds > 0 ? `in ${seconds} ${seconds === 1 ? "second" : "seconds"}` : "shortly";
    return { ok: false, retryable: true, message: `Too many attempts. Try again ${when}.` };
  }
""" + a)
open(p, "w").write(s)
