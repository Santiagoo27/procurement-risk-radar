import { useEffect, useMemo, useState } from "react";
import type { Topology } from "topojson-specification";
import { Legend } from "../components/Legend";
import { LayerPicker } from "../components/LayerPicker";
import { ColombiaMap } from "../components/Map";
import { RegionPanel } from "../components/RegionPanel";
import {
  loadDepartments, loadEntities, loadMunicipalities, loadSummary, loadTopology,
  type Entity, type RegionStats, type Summary,
} from "../lib/data";
import { count, pct } from "../lib/format";
import { LAYERS, colorScale, valueOf } from "../lib/scale";

interface Loaded {
  summary: Summary;
  departments: RegionStats[];
  municipalities: RegionStats[];
  entities: Entity[];
  topology: Topology;
}

export default function Home() {
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layerId, setLayerId] = useState(LAYERS[0].id);
  const [department, setDepartment] = useState<string | null>(null);
  const [municipality, setMunicipality] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([loadSummary(), loadDepartments(), loadMunicipalities(), loadEntities(),
      loadTopology()])
      .then(([summary, departments, municipalities, entities, topology]) =>
        setData({ summary, departments, municipalities, entities, topology }))
      .catch((e: Error) => setError(e.message));
  }, []);

  const layer = LAYERS.find((l) => l.id === layerId) ?? LAYERS[0];
  const byCode = useMemo(() => {
    const map = new Map<string, RegionStats>();
    data?.departments.forEach((d) => map.set(`d:${d.code}`, d));
    data?.municipalities.forEach((m) => map.set(`m:${m.code}`, m));
    return map;
  }, [data]);

  const level = department ? "m" : "d";
  const visible = useMemo(() => {
    if (!data) return [];
    return department
      ? data.municipalities.filter((m) => m.dpto_code === department)
      : data.departments;
  }, [data, department]);
  const scale = useMemo(() => colorScale(visible.map((r) => valueOf(r, layer))), [visible, layer]);

  if (error) return <p className="text-red-700">{error}</p>;
  if (!data) return <p className="text-muted">Loading the map…</p>;

  const { summary } = data;
  const predictedUnavailable = summary.predicted_layer_available
    ? undefined
    : "The predicted-risk layer is temporarily unavailable: SECOP's tender dataset, which the " +
      "model needs for contracts signed since 2025, is being republished. Only " +
      `${count(summary.n_open_scored)} open contracts could be scored, too few to be ` +
      "representative.";
  const nationalValue = layer.estimate
    ? summary.national.predicted_value_addition
    : layer.field === "extension_rate"
      ? summary.national.extension_rate
      : summary.national.value_addition_rate;

  const regionKey = municipality ? `m:${municipality}` : department ? `d:${department}` : null;
  const region = regionKey ? byCode.get(regionKey) : undefined;
  const regionEntities = data.entities.filter((e) =>
    municipality ? e.mpio_code === municipality : e.dpto_code === department);
  const lift = (summary.model_metrics.has_value_addition?.lightgbm?.precision_at_top ?? 0)
    / (summary.model_metrics.has_value_addition?.lightgbm?.positive_rate ?? 1);

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold sm:text-3xl">
          Which public contracts end up costing more than signed?
        </h1>
        <p className="max-w-3xl text-muted">
          About one in ten Colombian public contracts later receives a value addition. This map
          shows where, and a machine-learning model estimates the risk for contracts that are
          still running, using only what is known when they are signed.
        </p>
        <dl className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-3">
          <Stat label="Closed contracts analysed (2022–2024)" value={count(summary.n_closed)} />
          <Stat label="Received a value addition" value={pct(summary.national.value_addition_rate)} />
          <Stat label="Of the 5% the model ranks riskiest, got a value addition"
            value={pct(summary.model_metrics.has_value_addition?.lightgbm?.precision_at_top ?? null)}
            note={`${lift.toFixed(1)}× the base rate, on contracts signed 2023-07 to 2024-12`} />
        </dl>
      </section>

      <section className="space-y-3">
        <LayerPicker layers={LAYERS} value={layer.id} onChange={setLayerId}
          estimateUnavailable={predictedUnavailable} />
        <p className="text-sm text-muted">{layer.description}</p>
        {predictedUnavailable && (
          <p className="text-xs text-muted">{predictedUnavailable}</p>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section className="rounded-lg border border-line bg-white p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-sm font-medium">
              {department ? byCode.get(`d:${department}`)?.name : "Colombia"} ·{" "}
              {department ? "municipalities" : "departments"}
            </p>
            {department && (
              <button type="button" className="text-sm text-accent hover:underline"
                onClick={() => { setDepartment(null); setMunicipality(null); }}>
                ← Back to Colombia
              </button>
            )}
          </div>
          <ColombiaMap
            topology={data.topology}
            department={department}
            selected={municipality ?? department}
            colorFor={(code) => scale.color(valueOf(byCode.get(`${level}:${code}`), layer))}
            valueFor={(code) => valueOf(byCode.get(`${level}:${code}`), layer)}
            sampleFor={(code) => {
              const r = byCode.get(`${level}:${code}`);
              return (layer.estimate ? r?.n_open : r?.n_closed) ?? 0;
            }}
            onSelect={(code, lvl) => {
              if (lvl === "department") { setDepartment(code); setMunicipality(null); }
              else setMunicipality(code);
            }}
          />
          <div className="mt-2 space-y-1">
            <Legend title={layer.label} scale={scale} />
            <p className="text-xs text-muted">
              Grey: fewer than {summary.min_n} {layer.estimate ? "open contracts scored"
                : "closed SECOP II contracts"}. Many small municipalities still publish in
              SECOP I, which is not included.
              {layer.estimate && " The estimate covers open contracts whose tender data is available."}
            </p>
          </div>
        </section>

        <aside className="rounded-lg border border-line bg-white p-4">
          {region ? (
            <RegionPanel region={region} level={municipality ? "municipality" : "department"}
              layer={layer} minN={summary.min_n} national={nationalValue}
              entities={regionEntities} />
          ) : (
            <div className="space-y-2 text-sm text-muted">
              <h2 className="text-base font-semibold text-ink">Explore a region</h2>
              <p>Select a department to see its municipalities and its buyers.</p>
              <p>
                Regions are placed by where the buying entity is registered. Rates are hidden
                when fewer than {summary.min_n} contracts are available.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-line bg-white p-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="text-2xl font-semibold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-muted">{note}</dd>}
    </div>
  );
}
