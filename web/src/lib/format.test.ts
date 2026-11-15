import { describe, expect, it } from "vitest";
import { cop, days, isoDate, pct } from "./format";

describe("format", () => {
  it("shows a percentage or 'not enough data'", () => {
    expect(pct(0.1234)).toBe("12.3%");
    expect(pct(null)).toBe("not enough data");
    expect(pct(undefined)).toBe("not enough data");
    expect(pct(0)).toBe("0.0%");
  });
  it("formats COP compactly", () => {
    expect(cop(40_000_000)).toBe("$40M COP");
    expect(cop(1_250_000_000)).toBe("$1.25B COP");
    expect(cop(950_000)).toBe("$950K COP");
    expect(cop(null)).toBe("—");
  });
  it("formats days and dates", () => {
    expect(days(330)).toBe("330 days");
    expect(days(1)).toBe("1 day");
    expect(days(null)).toBe("—");
    expect(isoDate("2025-01-15")).toBe("15 Jan 2025");
  });
});
