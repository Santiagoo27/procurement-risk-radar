import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Entity as EntityT, EntityShard, Summary } from "../lib/data";
import Entity from "./Entity";

const summary = {
  min_n: 30,
  national: { value_addition_rate: 0.1, extension_rate: 0.11, predicted_value_addition: null,
    predicted_extension: null },
} as unknown as Summary;

const entities: EntityT[] = [{
  buyer_id: "E1", name: "Alcaldía de Prueba", dpto_code: "05", mpio_code: "05001",
  dpto_slug: "antioquia", n_closed: 120, value_addition_rate: 0.2, extension_rate: 0.05,
  n_open: 3, predicted_value_addition: null, predicted_extension: null,
}];

const shard: EntityShard = {
  E1: { top_open: [{
    id_contrato: "CO1.PCCNTR.1", url: "https://community.secop.gov.co/x", signed_at: "2024-12-01",
    contract_type: "Obra", procurement_method: "Licitación pública", award_value: 40_000_000,
    planned_duration_days: 330,
    value_addition: { probability: 0.42, percentile: 97, top_signals: [
      { feature: "signing_month", label: "Signing month", provided: true, contribution: 0.5 },
      { feature: "log_tender_budget", label: "Tender budget (not provided)", provided: false,
        contribution: 0.1 }] },
    time_extension: { probability: 0.21, percentile: 80, top_signals: [] },
  }, {
    id_contrato: null, url: null, supplier_is_natural_person: true, signed_at: "2024-12-02",
    contract_type: "Prestación de servicios", procurement_method: "Contratación directa",
    award_value: 9_000_000, planned_duration_days: 200,
    value_addition: { probability: 0.3, percentile: 80, top_signals: [] },
    time_extension: { probability: 0.1, percentile: 50, top_signals: [] },
  }] },
};

vi.mock("../lib/data", () => ({
  loadDepartments: () => Promise.resolve([{ code: "05", name: "Antioquia" }]),
  loadMunicipalities: () => Promise.resolve([{ code: "05001", name: "Medellín" }]),
  loadSummary: () => Promise.resolve(summary),
  loadEntities: () => Promise.resolve(entities),
  loadEntityShard: () => Promise.resolve(shard),
}));

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/entity/:buyerId" element={<Entity />} /></Routes>
    </MemoryRouter>,
  );
}

describe("Entity page", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows rates against Colombia and the riskiest open contracts", async () => {
    renderAt("/entity/E1");
    expect(await screen.findByRole("heading", { name: "Alcaldía de Prueba" })).toBeInTheDocument();
    expect(screen.getByText("20.0%")).toBeInTheDocument();
    expect(screen.getAllByText(/n = 120/)).toHaveLength(2);
    const link = screen.getByRole("link", { name: "CO1.PCCNTR.1" });
    expect(link).toHaveAttribute("href", "https://community.secop.gov.co/x");
    expect(screen.getByText("42.0%")).toBeInTheDocument();
    expect(screen.getByText(/Tender budget \(not provided\)/)).toBeInTheDocument();
    expect(screen.getByText(/Medellín, Antioquia/)).toBeInTheDocument();
    expect(screen.getByText(/natural person — identifier withheld/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Try a similar contract/ }))
      .toHaveAttribute("href", "/try?buyer=E1");
  });

  it("shows a not-found message for an unknown buyer", async () => {
    renderAt("/entity/NOPE");
    expect(await screen.findByText(/No buyer with id NOPE/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to the map/ })).toBeInTheDocument();
  });
});
