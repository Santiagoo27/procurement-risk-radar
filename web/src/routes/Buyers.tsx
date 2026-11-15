import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { LayerPicker } from "../components/LayerPicker";
import {
  loadDepartments, loadEntities, loadMunicipalities, loadSummary,
  type Entity, type RegionStats, type Summary,
} from "../lib/data";
import { count, pct } from "../lib/format";
import { LAYERS } from "../lib/scale";

const METRICS = LAYERS.filter((l) => !l.estimate);
const MINIMUMS = [30, 100, 500];
const PAGE = 50;

function fold(text: string | null | undefined): string {
  return (text ?? "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

interface Loaded {
  summary: Summary;
  entities: Entity[];
  departments: RegionStats[];
  municipalities: RegionStats[];
}

export default function Buyers() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const dpto = params.get("dpto") ?? "";
  const mpio = params.get("mpio") ?? "";
  const metric = METRICS.find((m) => m.id === params.get("metric")) ?? METRICS[0];
  const min = Number(params.get("min") ?? 100) || 100;
  const q = params.get("q") ?? "";

  const update = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    setParams(next, { replace: true });
    setPage(0);
  };

  useEffect(() => {
    Promise.all([loadSummary(), loadEntities(), loadDepartments(), loadMunicipalities()])
      .then(([summary, entities, departments, municipalities]) =>
        setData({ summary, entities, departments, municipalities }))
      .catch((e: Error) => setError(e.message));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = fold(q).trim();
    return data.entities
      .filter((e) => e.n_closed >= min && e[metric.field] !== null)
      .filter((e) => !dpto || e.dpto_code === dpto)
      .filter((e) => !mpio || e.mpio_code === mpio)
      .filter((e) => !needle || needle.split(/\s+/).every((w) => fold(e.name).includes(w)))
      .sort((a, b) => (b[metric.field] ?? 0) - (a[metric.field] ?? 0));
  }, [data, q, min, metric, dpto, mpio]);

  if (error) return <p className="text-red-700">{error}</p>;
  if (!data) return <p className="text-muted">Loading…</p>;

  const national = metric.field === "extension_rate"
    ? data.summary.national.extension_rate : data.summary.national.value_addition_rate;
  const mpioName = new Map(data.municipalities.map((m) => [m.code, m.name]));
  const departments = [...data.departments].filter((d) => d.name)
    .sort((a, b) => (a.name ?? "").localeCompare(b.name ?? ""));
  const municipalities = data.municipalities.filter((m) => m.dpto_code === dpto && m.name)
    .sort((a, b) => (a.name ?? "").localeCompare(b.name ?? ""));
  const shown = rows.slice(page * PAGE, (page + 1) * PAGE);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Buyers</h1>
        <p className="max-w-3xl rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          A high rate means this buyer's contracts often change after signing compared with what
          was planned. It is not a finding of wrongdoing: amendments are legal and often
          justified. Rates use closed contracts signed 2022–2024.
        </p>
      </header>

      <section className="flex flex-wrap items-end gap-3">
        <label className="flex w-full min-w-0 flex-col text-sm sm:w-auto">
          <span className="font-medium">Department</span>
          <select value={dpto} onChange={(e) => update({ dpto: e.target.value, mpio: "" })}
            className="w-full min-w-0 max-w-full rounded-md border border-line bg-white px-2 py-1.5 sm:w-64">
            <option value="">All of Colombia</option>
            {departments.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </select>
        </label>
        {dpto && (
          <label className="flex min-w-0 flex-col text-sm">
            <span className="font-medium">Municipality</span>
            <select value={mpio} onChange={(e) => update({ mpio: e.target.value })}
              className="w-40 max-w-full rounded-md border border-line bg-white px-2 py-1.5 sm:w-52">
              <option value="">All</option>
              {municipalities.map((m) => <option key={m.code} value={m.code}>{m.name}</option>)}
            </select>
          </label>
        )}
        <label className="flex flex-col text-sm">
          <span className="font-medium">Minimum contracts</span>
          <select value={min} onChange={(e) => update({ min: e.target.value })}
            className="rounded-md border border-line bg-white px-2 py-1.5">
            {MINIMUMS.map((m) => <option key={m} value={m}>{m}+</option>)}
          </select>
        </label>
        <label className="flex flex-1 flex-col text-sm">
          <span className="font-medium">Search by name</span>
          <input value={q} onChange={(e) => update({ q: e.target.value })}
            placeholder="e.g. hospital, alcaldía…"
            className="min-w-48 rounded-md border border-line bg-white px-2 py-1.5" />
        </label>
      </section>

      <LayerPicker layers={METRICS} value={metric.id}
        onChange={(id) => update({ metric: id === METRICS[0].id ? "" : id })} />

      <p className="text-sm text-muted">
        {count(rows.length)} buyers · Colombia: {pct(national)}
      </p>

      <div className="overflow-x-auto rounded-lg border border-line bg-white">
        <table className="w-full text-sm">
          <thead className="bg-paper text-left text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">Buyer</th>
              <th className="hidden px-3 py-2 font-medium sm:table-cell">Municipality</th>
              <th className="px-3 py-2 text-right font-medium">{metric.short}</th>
              <th className="hidden px-3 py-2 text-right font-medium sm:table-cell">vs Colombia</th>
              <th className="px-3 py-2 text-right font-medium">Contracts (n)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line tabular-nums">
            {shown.map((e) => {
              const value = e[metric.field] ?? 0;
              const diff = national === null ? null : (value - national) * 100;
              return (
                <tr key={e.buyer_id}>
                  <td className="max-w-80 px-3 py-2">
                    <Link className="text-accent hover:underline" to={`/entity/${e.buyer_id}`}>
                      {e.name ?? e.buyer_id}
                    </Link>
                  </td>
                  <td className="hidden px-3 py-2 text-muted sm:table-cell">
                    {mpioName.get(e.mpio_code ?? "") ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right">{pct(value)}</td>
                  <td className="hidden px-3 py-2 text-right text-muted sm:table-cell">
                    {diff === null ? "—" : `${diff >= 0 ? "+" : ""}${diff.toFixed(1)} pp`}
                  </td>
                  <td className="px-3 py-2 text-right">{count(e.n_closed)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="p-4 text-sm text-muted">No buyer matches these filters.</p>
        )}
      </div>

      {pages > 1 && (
        <nav className="flex items-center gap-3 text-sm" aria-label="Pagination">
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}
            className="rounded border border-line px-2 py-1 disabled:opacity-40">Previous</button>
          <span className="text-muted">Page {page + 1} of {pages}</span>
          <button type="button" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}
            className="rounded border border-line px-2 py-1 disabled:opacity-40">Next</button>
        </nav>
      )}
    </div>
  );
}
