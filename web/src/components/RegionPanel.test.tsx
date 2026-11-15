import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { Entity, RegionStats } from "../lib/data";
import { LAYERS } from "../lib/scale";
import { RegionPanel } from "./RegionPanel";

const region: RegionStats = {
  code: "05", name: "Antioquia", n_closed: 500, value_addition_rate: 0.12,
  extension_rate: 0.1, n_open: 80, predicted_value_addition: 0.15, predicted_extension: 0.09,
};

function entity(id: string, n: number, rate: number | null): Entity {
  return {
    buyer_id: id, name: `Entity ${id}`, dpto_code: "05", mpio_code: "05001",
    dpto_slug: "antioquia", n_closed: n, value_addition_rate: rate, extension_rate: rate,
    n_open: 0, predicted_value_addition: null, predicted_extension: null,
  };
}

describe("RegionPanel", () => {
  it("ranks only buyers with enough data and shows each sample size", () => {
    render(
      <MemoryRouter>
        <RegionPanel region={region} level="department" layer={LAYERS[0]} minN={30}
          national={0.1}
          entities={[entity("A", 100, 0.3), entity("B", 10, null), entity("C", 50, 0.2)]} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Antioquia" })).toBeInTheDocument();
    const rows = screen.getAllByRole("link", { name: /Entity/ });
    expect(rows.map((r) => r.textContent)).toEqual(["Entity A", "Entity C"]);
    expect(screen.getByText("n = 100")).toBeInTheDocument();
    expect(screen.queryByText("Entity B")).not.toBeInTheDocument();
    expect(screen.getByText("12.0%")).toBeInTheDocument();
  });

  it("explains suppression when the region itself is too small", () => {
    render(
      <MemoryRouter>
        <RegionPanel region={{ ...region, n_closed: 5, value_addition_rate: null }}
          level="municipality" layer={LAYERS[0]} minN={30} national={0.1} entities={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/fewer than 30 closed contracts/i)).toBeInTheDocument();
  });
});
