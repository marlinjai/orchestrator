import { describe, expect, it, vi } from "vitest";

import { AUTH_BRAIN_ACTIVE_CONTEXT_URL, switchActiveCompany } from "./switch-company";

function responding(status: number, headers?: Record<string, string>) {
  const res = {
    ok: status >= 200 && status < 300,
    status,
    headers: headers ? new Headers(headers) : new Headers(),
  } as Response;
  return vi.fn().mockResolvedValue(res);
}

describe("no company given", () => {
  it.each(["", "   ", "\n\t"])("makes no request for %j", async (id) => {
    const fetchImpl = responding(200);
    expect(await switchActiveCompany(id, fetchImpl)).toEqual({
      ok: false,
      retryable: false,
      message: "No company selected.",
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("sends a non-empty id untrimmed", async () => {
    const fetchImpl = responding(200);
    expect(await switchActiveCompany(" tnt_1 ", fetchImpl)).toEqual({ ok: true });
    expect(fetchImpl).toHaveBeenCalledWith(
      AUTH_BRAIN_ACTIVE_CONTEXT_URL,
      expect.objectContaining({ body: JSON.stringify({ tenant_id: " tnt_1 " }) }),
    );
  });
});

describe("session expired", () => {
  it("401 is not retryable and says to sign in", async () => {
    expect(await switchActiveCompany("tnt_1", responding(401))).toEqual({
      ok: false,
      retryable: false,
      message: "Your session has expired. Sign in again.",
    });
  });
});

describe("rate limited", () => {
  it("names the seconds from Retry-After", async () => {
    expect(await switchActiveCompany("tnt_1", responding(429, { "Retry-After": "30" }))).toEqual({
      ok: false,
      retryable: true,
      message: "Too many attempts. Try again in 30 seconds.",
    });
    expect(await switchActiveCompany("tnt_1", responding(429, { "retry-after": " 120 " }))).toEqual({
      ok: false,
      retryable: true,
      message: "Too many attempts. Try again in 120 seconds.",
    });
  });

  it("uses the singular for one second", async () => {
    const result = await switchActiveCompany("tnt_1", responding(429, { "Retry-After": "1" }));
    expect(result).toEqual({ ok: false, retryable: true, message: "Too many attempts. Try again in 1 second." });
  });

  it.each(["0", "-5", "1.5", "soon", "Wed, 21 Oct 2026 07:28:00 GMT", "", "12s"])(
    "falls back for Retry-After %j",
    async (value) => {
      const result = await switchActiveCompany("tnt_1", responding(429, { "Retry-After": value }));
      expect(result).toEqual({ ok: false, retryable: true, message: "Too many attempts. Try again shortly." });
    },
  );

  it("falls back without the header and without a headers object", async () => {
    const expected = { ok: false, retryable: true, message: "Too many attempts. Try again shortly." };
    expect(await switchActiveCompany("tnt_1", responding(429))).toEqual(expected);
    const bare = vi.fn().mockResolvedValue({ ok: false, status: 429 } as Response);
    expect(await switchActiveCompany("tnt_1", bare)).toEqual(expected);
  });
});

describe("unchanged results", () => {
  it("keeps 403, 400, the generic fallback and the network error", async () => {
    expect(await switchActiveCompany("tnt_1", responding(403))).toEqual({
      ok: false,
      retryable: false,
      message: "You no longer have access to that company.",
    });
    expect(await switchActiveCompany("tnt_1", responding(400))).toEqual({
      ok: false,
      retryable: false,
      message: "That company selection is not valid right now.",
    });
    expect(await switchActiveCompany("tnt_1", responding(503))).toEqual({
      ok: false,
      retryable: true,
      message: "Switch failed (HTTP 503). Try again.",
    });
    const failing = vi.fn().mockRejectedValue(new TypeError("network"));
    expect(await switchActiveCompany("tnt_1", failing)).toEqual({
      ok: false,
      retryable: true,
      message: "Couldn't reach the identity service. Check your connection and try again.",
    });
  });
});
