import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { colorScale } from "../lib/scale";
import { Legend } from "./Legend";

describe("Legend", () => {
  it("lists every bin as a percentage range plus 'not enough data'", () => {
    const scale = colorScale(Array.from({ length: 50 }, (_, i) => i / 100));
    render(<Legend title="Value additions (observed)" scale={scale} />);
    expect(screen.getByText("Value additions (observed)")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(6);
    expect(screen.getByText("Not enough data")).toBeInTheDocument();
    expect(screen.getByText(/^0\.0%/)).toBeInTheDocument();
  });
});
