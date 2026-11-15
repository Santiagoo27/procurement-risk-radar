import { fireEvent, render, screen } from "@testing-library/react";
import type { Topology } from "topojson-specification";
import { describe, expect, it, vi } from "vitest";
import { ColombiaMap } from "./Map";

const topology = {
  type: "Topology",
  arcs: [],
  objects: {
    departments: { type: "GeometryCollection", geometries: [
      { type: "Polygon", arcs: [], properties: { dpto_code: "05", dpto_name: "Antioquia" } },
    ] },
    municipalities: { type: "GeometryCollection", geometries: [] },
  },
} as unknown as Topology;
// An empty arc list renders an empty path, which is enough to test the semantics.

describe("ColombiaMap", () => {
  it("exposes regions as keyboard buttons with a pressed state", () => {
    const onSelect = vi.fn();
    render(<ColombiaMap topology={topology} department={null} selected="05"
      colorFor={() => "#000"} valueFor={() => 0.1} sampleFor={() => 50} onSelect={onSelect} />);
    const region = screen.getByRole("button", { name: /Antioquia: 10.0%/ });
    expect(region).toHaveAttribute("aria-pressed", "true");
    expect(region.getAttribute("class")).toMatch(/focus-visible:/);
    fireEvent.keyDown(region, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("05", "department");
  });
});
