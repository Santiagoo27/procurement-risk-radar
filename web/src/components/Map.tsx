import { geoMercator, geoPath } from "d3-geo";
import { useMemo, useState } from "react";
import { feature } from "topojson-client";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { GeometryCollection, Topology } from "topojson-specification";
import { pct } from "../lib/format";

export interface RegionProps {
  mpio_code?: string;
  mpio_name?: string;
  dpto_code: string;
  dpto_name: string;
}

interface Props {
  topology: Topology;
  department: string | null;
  colorFor: (code: string) => string;
  valueFor: (code: string) => number | null;
  sampleFor: (code: string) => number;
  selected: string | null;
  onSelect: (code: string, level: "department" | "municipality") => void;
}

const WIDTH = 600;
const HEIGHT = 720;

type RegionFeature = Feature<Geometry, RegionProps>;

function collection(topology: Topology, name: string): RegionFeature[] {
  const object = topology.objects[name] as GeometryCollection<RegionProps>;
  return (feature(topology, object) as FeatureCollection<Geometry, RegionProps>).features;
}

export function ColombiaMap(props: Props) {
  const { topology, department, colorFor, valueFor, sampleFor, selected, onSelect } = props;
  const [hover, setHover] = useState<{ code: string; name: string; x: number; y: number } | null>(
    null);

  const departments = useMemo(() => collection(topology, "departments"), [topology]);
  const municipalities = useMemo(() => collection(topology, "municipalities"), [topology]);

  const level = department ? "municipality" : "department";
  const shapes = department
    ? municipalities.filter((f) => f.properties.dpto_code === department)
    : departments;
  const codeOf = (f: RegionFeature) =>
    (level === "municipality" ? f.properties.mpio_code : f.properties.dpto_code) ?? "";
  const nameOf = (f: RegionFeature) =>
    (level === "municipality" ? f.properties.mpio_name : f.properties.dpto_name) ?? codeOf(f);

  const path = useMemo(() => {
    const target = { type: "FeatureCollection", features: shapes } as FeatureCollection;
    const projection = geoMercator().fitExtent([[8, 8], [WIDTH - 8, HEIGHT - 8]], target);
    return geoPath(projection);
  }, [shapes]);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full"
        role="group" aria-label={department ? "Municipalities map" : "Departments map"}
        onMouseLeave={() => setHover(null)}>
        {shapes.map((f) => {
          const code = codeOf(f);
          const isSelected = selected === code;
          return (
            <path
              key={code}
              d={path(f) ?? undefined}
              fill={colorFor(code)}
              stroke={isSelected ? "#1f2933" : "#ffffff"}
              strokeWidth={isSelected ? 2 : 0.6}
              className="cursor-pointer outline-none transition-opacity hover:opacity-80 focus-visible:stroke-[#1f2933] focus-visible:[stroke-width:3]"
              tabIndex={0}
              role="button"
              aria-pressed={isSelected}
              aria-label={`${nameOf(f)}: ${pct(valueFor(code))}`}
              onClick={() => onSelect(code, level)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(code, level);
                }
              }}
              onMouseMove={(e) => {
                const box = (e.currentTarget.ownerSVGElement as SVGSVGElement)
                  .getBoundingClientRect();
                setHover({ code, name: nameOf(f), x: e.clientX - box.left, y: e.clientY - box.top });
              }}
            />
          );
        })}
      </svg>
      {hover && (
        <div className="pointer-events-none absolute z-10 rounded-md border border-line bg-white px-2 py-1 text-xs shadow-sm"
          style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <div className="font-medium text-ink">{hover.name}</div>
          <div className="text-muted">
            {pct(valueFor(hover.code))} · n = {sampleFor(hover.code).toLocaleString("en-US")}
          </div>
        </div>
      )}
    </div>
  );
}
