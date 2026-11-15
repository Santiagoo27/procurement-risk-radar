import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { RiskBadge } from "../components/RiskBadge";
import { Signals } from "../components/Signals";
import {
  loadDepartments, loadEntities, loadEntityShard, loadMunicipalities, loadSummary,
  type Entity as EntityT, type OpenContract, type Summary,
} from "../lib/data";
import { cop, count, days, isoDate, pct } from "../lib/format";

interface Loaded {
  summary: Summary;
  entity: EntityT | null;
  contracts: OpenContract[];
  location: string | null;
}

export default function Entity() {
  const { buyerId = "" } = useParams();
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    (async () => {
      const [summary, entities, departments, municipalities] = await Promise.all([
        loadSummary(), loadEntities(), loadDepartments(), loadMunicipalities()]);
      const entity = entities.find((e) => e.buyer_id === buyerId) ?? null;
      let contracts: OpenContract[] = [];
      if (entity && entity.n_open > 0) {
        const shard = await loadEntityShard(entity.dpto_slug);
        contracts = shard[buyerId]?.top_open ?? [];
      }
      const dpto = departments.find((d) => d.code === entity?.dpto_code)?.name;
      const mpio = municipalities.find((m) => m.code === entity?.mpio_code)?.name;
      const location = [mpio, dpto].filter(Boolean).join(", ") || null;
      if (!cancelled) setData({ summary, entity, contracts, location });
    })().catch((e: Error) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [buyerId]);

  if (error) return <p className="text-red-700">{error}</p>;
  if (!data) return <p className="text-muted">Loading…</p>;

  const { summary, entity, contracts, location } = data;
  if (!entity) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Buyer not found</h1>
        <p className="text-muted">No buyer with id {buyerId} is in the data.</p>
        <Link className="text-accent underline" to="/">Back to the map</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Link className="text-sm text-accent hover:underline" to="/">← Map</Link>
        <h1 className="text-2xl font-semibold">{entity.name ?? entity.buyer_id}</h1>
        <p className="text-sm text-muted">
          {location && <>{location} · </>}SECOP entity code {entity.buyer_id}
        </p>
      </div>

      <section className="grid gap-3 sm:grid-cols-2">
        <Rate label="Contracts that received a value addition" value={entity.value_addition_rate}
          national={summary.national.value_addition_rate} n={entity.n_closed}
          minN={summary.min_n} />
        <Rate label="Contracts whose term was extended" value={entity.extension_rate}
          national={summary.national.extension_rate} n={entity.n_closed} minN={summary.min_n} />
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold">Riskiest open contracts</h2>
          <Link className="text-sm text-accent hover:underline" to={`/try?buyer=${entity.buyer_id}`}>
            Try a similar contract →
          </Link>
        </div>
        {contracts.length === 0 ? (
          <p className="rounded-md bg-white p-4 text-sm text-muted">
            No open contract of this buyer with a recorded value could be listed. Recent
            contracts also need tender data that SECOP has not republished yet.
          </p>
        ) : (
          <ul className="space-y-3">
            {contracts.map((c, i) => <ContractCard key={c.id_contrato ?? `person-${i}`}
              contract={c} />)}
          </ul>
        )}
      </section>
    </div>
  );
}

function Rate({ label, value, national, n, minN }: {
  label: string; value: number | null; national: number | null; n: number; minN: number;
}) {
  return (
    <div className="rounded-lg border border-line bg-white p-4">
      <p className="text-sm text-muted">{label}</p>
      {value === null ? (
        <p className="mt-1 text-sm text-muted">
          Not enough data (fewer than {minN} closed contracts, n = {count(n)}).
        </p>
      ) : (
        <>
          <p className="text-3xl font-semibold tabular-nums">{pct(value)}</p>
          <p className="text-xs text-muted">
            n = {count(n)} closed contracts signed 2022–2024 · Colombia: {pct(national)}
          </p>
        </>
      )}
    </div>
  );
}

function ContractCard({ contract: c }: { contract: OpenContract }) {
  return (
    <li className="rounded-lg border border-line bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        {c.id_contrato === null ? (
          <span className="font-medium text-muted">
            Contract with a natural person — identifier withheld
          </span>
        ) : c.url ? (
          <a className="font-medium text-accent hover:underline" href={c.url} target="_blank"
            rel="noreferrer">{c.id_contrato}</a>
        ) : <span className="font-medium">{c.id_contrato}</span>}
        <span className="text-sm text-muted">Signed {isoDate(c.signed_at)}</span>
      </div>
      <p className="mt-1 text-sm text-muted">
        {[c.contract_type, c.procurement_method, cop(c.award_value),
          days(c.planned_duration_days)].filter(Boolean).join(" · ")}
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <RiskBadge label="Value addition" score={c.value_addition} />
          <Signals signals={c.value_addition.top_signals} />
        </div>
        <div className="space-y-2">
          <RiskBadge label="Time extension" score={c.time_extension} />
          <Signals signals={c.time_extension.top_signals} />
        </div>
      </div>
    </li>
  );
}
