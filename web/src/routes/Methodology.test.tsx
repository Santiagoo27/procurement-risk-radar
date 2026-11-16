import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Summary } from "../lib/data";
import Methodology from "./Methodology";

const metrics = (pr: number, roc: number, p5: number, base: number) => ({
  lightgbm: { pr_auc: pr, roc_auc: roc, precision_at_top: p5, positive_rate: base },
  base_rate: { pr_auc: base, roc_auc: 0.5, precision_at_top: base, positive_rate: base },
});

const state = vi.hoisted(() => ({
  features: [] as string[], byTarget: {} as Record<string, string[]>,
}));

vi.mock("../lib/data", () => ({
  loadAmendmentSize: () => Promise.resolve({
    since: "2026-11-14", n_contracts_observed: 5710920, n_increased: 2485,
    median_increase_pct: 0.2333, p75_increase_pct: 0.5, p90_increase_pct: 0.5,
    share_over_30pct: 0.42, reason: null,
  }),
  loadMonitoring: () => Promise.resolve({
    as_of: "2026-11-22", status: "watch", n_current: 40000,
    windows: { reference: [null, "2023-01-01"], current: ["2026-08-24", "2026-11-22"] },
    feature_drift: [
      { feature: "signing_month", label: "Signing month", psi: 0.41, shifted: true },
      { feature: "n_bidders", label: "Number of bidders", psi: 0.03, shifted: false },
    ],
    score_shift: { reference_mean: 0.10, current_mean: 0.12 },
    realized: { pr_auc: null, n: 12, test_pr_auc: 0.243, reason: "fewer than 500 closed" },
  }),
  loadSummary: () => Promise.resolve({
    min_n: 30, n_closed: 2410377, observed_period: ["2022-01-01", "2025-01-01"],
    as_of: "2026-11-14", bundle_version: "2026-11-14", model_features: state.features,
    model_features_by_target: state.byTarget,
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


describe("Methodology election features", () => {
  it("mentions the election calendar only when the production model uses it", async () => {
    state.features.length = 0;
    const { unmount } = render(<MemoryRouter><Methodology /></MemoryRouter>);
    await screen.findByText("0.243");
    expect(screen.queryByText(/Ley 996 de 2005/)).not.toBeInTheDocument();
    unmount();

    state.features.push("planned_end_in_restriction");
    state.byTarget.has_time_extension = ["planned_end_in_restriction"];
    state.byTarget.has_value_addition = ["n_bidders"];
    render(<MemoryRouter><Methodology /></MemoryRouter>);
    expect(await screen.findByText(/Ley 996 de 2005/)).toBeInTheDocument();
    expect(screen.getByText(/The time-extension model also knows/)).toBeInTheDocument();
  });
});


describe("Methodology model health", () => {
  it("shows the monitoring status and the most shifted feature", async () => {
    render(<MemoryRouter><Methodology /></MemoryRouter>);
    expect(await screen.findByText(/Model health/)).toBeInTheDocument();
    expect(screen.getByText(/Watch/)).toBeInTheDocument();
    expect(screen.getByText("Signing month")).toBeInTheDocument();
    expect(screen.getByText("0.41")).toBeInTheDocument();
    expect(screen.getByText(/fewer than 500 closed/)).toBeInTheDocument();
  });
});


describe("Methodology addition size", () => {
  it("shows the median increase with its sample and start date", async () => {
    render(<MemoryRouter><Methodology /></MemoryRouter>);
    expect(await screen.findByText(/How big are additions/)).toBeInTheDocument();
    expect(screen.getByText(/23\.3%/)).toBeInTheDocument();
    expect(screen.getByText(/2,485 contracts/)).toBeInTheDocument();
    expect(screen.getByText(/since 2026-11-14/)).toBeInTheDocument();
  });
});
