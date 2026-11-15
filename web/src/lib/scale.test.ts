import { describe, expect, it } from "vitest";
import { LAYERS, NO_DATA, RAMP, colorScale } from "./scale";

describe("colorScale", () => {
  it("paints null as the no-data grey", () => {
    const scale = colorScale([0.1, 0.2, 0.3]);
    expect(scale.color(null)).toBe(NO_DATA);
    expect(scale.color(undefined)).toBe(NO_DATA);
  });

  it("uses five monotonic bins from the sequential ramp", () => {
    const values = Array.from({ length: 50 }, (_, i) => i / 100);
    const scale = colorScale(values);
    expect(scale.bins).toHaveLength(5);
    expect(scale.bins.map((b) => b.color)).toEqual(RAMP);
    for (let i = 1; i < scale.bins.length; i++) {
      expect(scale.bins[i].from).toBeGreaterThanOrEqual(scale.bins[i - 1].from);
    }
    expect(scale.color(0)).toBe(RAMP[0]);
    expect(scale.color(0.49)).toBe(RAMP[4]);
  });

  it("handles a layer with no values", () => {
    const scale = colorScale([null, null]);
    expect(scale.bins).toHaveLength(0);
    expect(scale.color(0.3)).toBe(NO_DATA);
  });

  it("marks the predicted layer as an estimate", () => {
    expect(LAYERS.find((l) => l.id === "predicted_value_addition")?.estimate).toBe(true);
    expect(LAYERS[0].id).toBe("observed_value_addition");
  });
});
