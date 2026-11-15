import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Summary } from "../lib/data";
import Methodology from "./Methodology";

const metrics = (pr: number, roc: number, p5: number, base: number) => ({
  lightgbm: { pr_auc: pr, roc_auc: roc, precision_at_top: p5, positive_rate: base },
  base_rate: { pr_auc: base, roc_auc: 0.5, precision_at_top: base, positive_rate: base },
});

vi.mock("../lib/data", () => ({
  loadSummary: () => Promise.resolve({
    min_n: 30, n_closed: 2410377, observed_period: ["2022-01-01", "2025-01-01"],
    as_of: "2026-11-14", bundle_version: "2026-11-14",
    model_metrics: {
      has_value_addition: metrics(0.243, 0.758, 0.344, 0.079),
      has_time_extension: metrics(0.323, 0.763, 0.448, 0.113),
    },
  } as unknown as Summary),
}));

describe("Methodology page", () => {
  it("shows the model metrics from summary.json and the disclaimer", async () => {
    render(<MemoryRouter><Methodology /></MemoryRouter>);
    expect(await screen.findByText("0.243")).toBeInTheDocument();
    expect(screen.getByText("0.323")).toBeInTheDocument();
    expect(screen.getByText("34.4%")).toBeInTheDocument();
    expect(screen.getAllByText(/not allegations of wrongdoing/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /model card/i })).toHaveAttribute("href",
      expect.stringContaining("docs/model-card.md"));
  });
});
