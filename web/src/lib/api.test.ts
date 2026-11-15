import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiTimeout, ApiValidation, UnknownBuyer, predict } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("api.predict", () => {
  it("maps 404 to UnknownBuyer", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "unknown buyer_id" }), { status: 404 })));
    await expect(predict({ buyer_id: "X" })).rejects.toBeInstanceOf(UnknownBuyer);
  });

  it("maps 422 details to per-field messages", async () => {
    const detail = [{ loc: ["body", "contracts", 0, "award_value"], msg: "too big", type: "x" }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail }), { status: 422 })));
    const error = await predict({ buyer_id: "X" }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiValidation);
    expect((error as ApiValidation).fields).toEqual({ award_value: "too big" });
  });

  it("times out", async () => {
    vi.stubGlobal("fetch", vi.fn((_: string, init: RequestInit) => new Promise((_r, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("aborted",
        "AbortError")));
    })));
    await expect(predict({ buyer_id: "X" }, { timeoutMs: 20 })).rejects.toBeInstanceOf(ApiTimeout);
  });
});
