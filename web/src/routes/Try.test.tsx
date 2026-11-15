import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Try from "./Try";

const RESULT = {
  bundle_version: "2026-11-14",
  disclaimer: "Scores are statistical estimates for analysis, not allegations of wrongdoing.",
  results: [{
    value_addition: { probability: 0.173, percentile: 90, top_signals: [
      { feature: "signing_month", label: "Signing month", provided: true, contribution: 0.4 },
      { feature: "log_tender_budget", label: "Tender budget (not provided)", provided: false,
        contribution: 0.1 }] },
    time_extension: { probability: 0.035, percentile: 15, top_signals: [] },
    warnings: [],
  }],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderTry(path = "/try?buyer=700221021") {
  render(<MemoryRouter initialEntries={[path]}><Try /></MemoryRouter>);
}

afterEach(() => vi.unstubAllGlobals());

describe("Try page", () => {
  it("shows the waking state until /health responds", async () => {
    let wake!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/health")
      ? new Promise<Response>((r) => { wake = r; })
      : Promise.resolve(json([]))));
    renderTry();
    expect(screen.getByText(/Waking up the model/)).toBeInTheDocument();
    wake(json({ status: "ok", bundle_version: "2026-11-14" }));
    await waitFor(() => expect(screen.queryByText(/Waking up the model/)).not.toBeInTheDocument());
  });

  it("offers a retry when the API does not answer", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
    renderTry();
    expect(await screen.findByText(/could not reach the model/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();
  });

  it("validates fields before calling the API", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.endsWith("/health")
      ? json({ status: "ok" }) : json(RESULT)));
    vi.stubGlobal("fetch", fetchMock);
    renderTry();
    await screen.findByRole("button", { name: /Estimate risk/ });
    fireEvent.change(screen.getByLabelText(/Planned duration/), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: /Estimate risk/ }));
    expect(await screen.findByText(/between 1 and 3650 days/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/predict"))).toBe(false);
  });

  it("renders the result with signals and not-provided wording", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("/health")
      ? json({ status: "ok" }) : json(RESULT))));
    renderTry();
    fireEvent.click(await screen.findByRole("button", { name: /Estimate risk/ }));
    expect(await screen.findByText("17.3%")).toBeInTheDocument();
    expect(screen.getByText(/higher than 90% of recent contracts/)).toBeInTheDocument();
    expect(screen.getByText(/Tender budget \(not provided\)/)).toBeInTheDocument();
    expect(screen.getByText(/not allegations of wrongdoing/)).toBeInTheDocument();
  });
});
