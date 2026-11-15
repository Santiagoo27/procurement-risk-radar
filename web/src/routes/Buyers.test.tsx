import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Entity, RegionStats, Summary } from "../lib/data";
import Buyers from "./Buyers";

function entity(id: string, name: string, dpto: string, n: number, va: number,
  ext: number): Entity {
  return {
    buyer_id: id, name, dpto_code: dpto, mpio_code: `${dpto}001`, dpto_slug: "x", n_closed: n,
    value_addition_rate: va, extension_rate: ext, n_open: 0, predicted_value_addition: null,
    predicted_extension: null,
  };
}

const entities = [
  entity("A", "ALCALDÍA DE MEDELLÍN", "05", 500, 0.3, 0.05),
  entity("B", "HOSPITAL DE BELLO", "05", 200, 0.1, 0.4),
  entity("C", "PEQUEÑA ENTIDAD", "05", 40, 0.9, 0.9),
  entity("D", "GOBERNACIÓN DEL VALLE", "76", 800, 0.2, 0.1),
];

vi.mock("../lib/data", () => ({
  loadSummary: () => Promise.resolve({
    min_n: 30, national: { value_addition_rate: 0.1, extension_rate: 0.11 },
  } as unknown as Summary),
  loadEntities: () => Promise.resolve(entities),
  loadDepartments: () => Promise.resolve([
    { code: "05", name: "Antioquia" }, { code: "76", name: "Valle Del Cauca" },
  ] as RegionStats[]),
  loadMunicipalities: () => Promise.resolve([
    { code: "05001", name: "Medellín", dpto_code: "05" },
    { code: "76001", name: "Cali", dpto_code: "76" },
  ] as RegionStats[]),
}));

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function renderAt(path = "/buyers") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/buyers" element={<><Buyers /><LocationProbe /></>} /></Routes>
    </MemoryRouter>,
  );
}

const names = () => screen.getAllByRole("link").map((a) => a.textContent);

describe("Buyers page", () => {
  it("excludes buyers below the minimum sample and shows n on every row", async () => {
    renderAt();
    await screen.findByText("ALCALDÍA DE MEDELLÍN");
    expect(names()).toEqual(["ALCALDÍA DE MEDELLÍN", "GOBERNACIÓN DEL VALLE",
      "HOSPITAL DE BELLO"]);
    const rows = screen.getAllByRole("row").slice(1);
    rows.forEach((row) => expect(within(row).getByText(/^\d[\d,]*$/)).toBeInTheDocument());
    expect(screen.getByText(/not a finding of wrongdoing/)).toBeInTheDocument();
  });

  it("filters by department and keeps the state in the URL", async () => {
    renderAt();
    await screen.findByText("ALCALDÍA DE MEDELLÍN");
    fireEvent.change(screen.getByLabelText("Department"), { target: { value: "76" } });
    expect(names()).toEqual(["GOBERNACIÓN DEL VALLE"]);
    expect(screen.getByTestId("location").textContent).toContain("dpto=76");
  });

  it("re-sorts when the metric changes", async () => {
    renderAt();
    await screen.findByText("ALCALDÍA DE MEDELLÍN");
    fireEvent.click(screen.getByRole("radio", { name: "Time extensions" }));
    expect(names()[0]).toBe("HOSPITAL DE BELLO");
  });

  it("searches without accents and restores state from the URL", async () => {
    renderAt("/buyers?min=30&q=medellin");
    await screen.findByText("ALCALDÍA DE MEDELLÍN");
    expect(names()).toEqual(["ALCALDÍA DE MEDELLÍN"]);
  });

  it("lowering the minimum includes smaller buyers", async () => {
    renderAt("/buyers?min=30");
    await screen.findByText("PEQUEÑA ENTIDAD");
    expect(names()[0]).toBe("PEQUEÑA ENTIDAD");
  });
});
