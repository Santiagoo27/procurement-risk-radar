import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskBadge, band } from "./RiskBadge";

describe("RiskBadge", () => {
  it("describes the percentile in words", () => {
    render(<RiskBadge label="Value addition" score={{ probability: 0.42, percentile: 97,
      top_signals: [] }} />);
    expect(screen.getByText("42.0%")).toBeInTheDocument();
    expect(screen.getByText(/higher than 97% of recent contracts/)).toBeInTheDocument();
  });

  it("maps percentiles to bands", () => {
    expect(band(97)).toBe("high");
    expect(band(70)).toBe("elevated");
    expect(band(20)).toBe("typical");
  });
});


describe("RiskBadge top percentile", () => {
  it("never claims to be higher than 100% of contracts", () => {
    render(<RiskBadge label="Value addition" score={{ probability: 0.93, percentile: 100,
      top_signals: [] }} />);
    expect(screen.getByText(/in the top 1% of recent contracts/)).toBeInTheDocument();
    expect(screen.queryByText(/higher than 100%/)).not.toBeInTheDocument();
  });
});
