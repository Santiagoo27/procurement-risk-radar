import { afterEach, describe, expect, it, vi } from "vitest";
import { DataError, loadSummary, resetDataCache } from "./data";

afterEach(() => {
  vi.unstubAllGlobals();
  resetDataCache();
});

describe("data loaders", () => {
  it("throws a readable DataError when a file fails to load", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 404 })));
    await expect(loadSummary()).rejects.toBeInstanceOf(DataError);
    await expect(loadSummary()).rejects.toThrow(/summary/);
  });

  it("caches successful loads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ n_closed: 3 })));
    vi.stubGlobal("fetch", fetchMock);
    await loadSummary();
    await loadSummary();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
