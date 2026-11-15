import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LAYERS } from "../lib/scale";
import { LayerPicker } from "./LayerPicker";

describe("LayerPicker", () => {
  it("disables estimate layers when they are unavailable and says why", () => {
    const onChange = vi.fn();
    render(<LayerPicker layers={LAYERS} value={LAYERS[0].id} onChange={onChange}
      estimateUnavailable="Temporarily unavailable" />);
    const predicted = screen.getByRole("radio", { name: /Predicted risk/ });
    expect(predicted).toBeDisabled();
    expect(predicted).toHaveAttribute("title", "Temporarily unavailable");
    fireEvent.click(predicted);
    expect(onChange).not.toHaveBeenCalled();
  });
});
