import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { DISCLAIMER } from "../components/Disclaimer";
import { RiskBadge } from "../components/RiskBadge";
import { Signals } from "../components/Signals";
import {
  ApiValidation, UnknownBuyer, predict, searchBuyers, wakeUp,
  type BuyerHit, type ContractInput, type PredictResponse,
} from "../lib/api";

type ApiState = "waking" | "ready" | "unavailable";

const METHODS = ["Contratación directa", "Mínima cuantía", "Licitación pública",
  "Selección Abreviada de Menor Cuantía", "Selección abreviada subasta inversa",
  "Concurso de méritos abierto", "Contratación régimen especial"];
const TYPES = ["Prestación de servicios", "Obra", "Suministros", "Compraventa", "Consultoría",
  "Interventoría", "Arrendamiento de inmuebles", "Otro"];

interface Form {
  signed_at: string;
  procurement_method: string;
  contract_type: string;
  award_value: string;
  tender_budget: string;
  planned_duration_days: string;
  n_bidders: string;
  supplier_is_natural_person: string;
}

const EMPTY: Form = {
  signed_at: new Date().toISOString().slice(0, 10), procurement_method: "Contratación directa",
  contract_type: "Prestación de servicios", award_value: "40000000", tender_budget: "",
  planned_duration_days: "330", n_bidders: "", supplier_is_natural_person: "yes",
};

function validate(form: Form): Record<string, string> {
  const errors: Record<string, string> = {};
  const money = (key: keyof Form) => {
    if (form[key] === "") return;
    const v = Number(form[key]);
    if (!Number.isFinite(v) || v < 0 || v > 1e15) errors[key] = "Enter an amount between 0 and 1e15 COP.";
  };
  money("award_value");
  money("tender_budget");
  if (form.planned_duration_days !== "") {
    const d = Number(form.planned_duration_days);
    if (!Number.isFinite(d) || d < 1 || d > 3650) {
      errors.planned_duration_days = "Enter a duration between 1 and 3650 days.";
    }
  }
  if (form.n_bidders !== "") {
    const n = Number(form.n_bidders);
    if (!Number.isInteger(n) || n < 0 || n > 100_000) errors.n_bidders = "Enter a whole number ≥ 0.";
  }
  const year = Number(form.signed_at.slice(0, 4));
  if (form.signed_at && (year < 2000 || year >= 2100)) {
    errors.signed_at = "Enter a date between 2000 and 2099.";
  }
  return errors;
}

function toInput(buyerId: string, form: Form): ContractInput {
  const num = (v: string) => (v === "" ? undefined : Number(v));
  const bool = (v: string) => (v === "" ? undefined : v === "yes");
  return {
    buyer_id: buyerId,
    signed_at: form.signed_at || undefined,
    procurement_method: form.procurement_method || undefined,
    contract_type: form.contract_type || undefined,
    award_value: num(form.award_value),
    tender_budget: num(form.tender_budget),
    planned_duration_days: num(form.planned_duration_days),
    n_bidders: num(form.n_bidders),
    supplier_is_natural_person: bool(form.supplier_is_natural_person),
  };
}

export default function Try() {
  const [params] = useSearchParams();
  const [api, setApi] = useState<ApiState>("waking");
  const [buyer, setBuyer] = useState<BuyerHit | null>(
    params.get("buyer") ? { buyer_id: params.get("buyer")!, buyer_name: null,
      buyer_department: null, buyer_city: null } : null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<BuyerHit[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const connect = useCallback(() => {
    setApi("waking");
    wakeUp().then(() => setApi("ready")).catch(() => setApi("unavailable"));
  }, []);
  useEffect(connect, [connect]);

  useEffect(() => {
    if (query.trim().length < 2 || api !== "ready") { setHits([]); return; }
    const timer = setTimeout(() => searchBuyers(query).then(setHits).catch(() => setHits([])),
      300);
    return () => clearTimeout(timer);
  }, [query, api]);

  const field = (key: keyof Form) => ({
    id: key,
    value: form[key],
    onChange: (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value }),
    "aria-invalid": Boolean(errors[key]),
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFailure(null);
    setResult(null);
    const found = validate(form);
    if (!buyer) found.buyer = "Choose a buyer first.";
    setErrors(found);
    if (Object.keys(found).length || !buyer) return;
    setBusy(true);
    try {
      setResult(await predict(toInput(buyer.buyer_id, form)));
    } catch (error) {
      if (error instanceof ApiValidation) {
        const shown = new Set(["signed_at", "planned_duration_days", "procurement_method",
          "contract_type", "award_value", "tender_budget", "n_bidders"]);
        const fields: Record<string, string> = {};
        const other: string[] = [];
        for (const [key, msg] of Object.entries(error.fields)) {
          if (key === "buyer_id") fields.buyer = msg;
          else if (shown.has(key)) fields[key] = msg;
          else other.push(msg);
        }
        setErrors(fields);
        if (other.length) setFailure(`The model rejected the request: ${other.join("; ")}`);
      }
      else if (error instanceof UnknownBuyer) setErrors({ buyer: error.message });
      else setFailure((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const score = result?.results[0];
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Try it</h1>
          <p className="text-muted">
            Describe a contract as it would look on the day it is signed. The live model returns
            the probability of a later value addition or time extension.
          </p>
        </div>

        {api === "waking" && (
          <p role="status" className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">
            Waking up the model — the free server sleeps when idle, so this can take up to a
            minute.
          </p>
        )}
        {api === "unavailable" && (
          <div role="alert" className="flex items-center justify-between gap-3 rounded-md bg-red-50 p-3 text-sm text-red-900">
            <span>We could not reach the model. It may be restarting.</span>
            <button type="button" onClick={connect}
              className="rounded border border-red-300 px-2 py-1">Retry</button>
          </div>
        )}

        <form onSubmit={submit} className="space-y-4 rounded-lg border border-line bg-white p-4"
          noValidate>
          <div className="space-y-1">
            <label htmlFor="buyer-search" className="text-sm font-medium">Buyer</label>
            {buyer ? (
              <div className="flex items-center justify-between rounded-md bg-paper px-3 py-2 text-sm">
                <span>{buyer.buyer_name ?? `Entity ${buyer.buyer_id}`}</span>
                <button type="button" className="text-accent hover:underline"
                  onClick={() => setBuyer(null)}>Change</button>
              </div>
            ) : (
              <>
                <input id="buyer-search" value={query} onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by name, e.g. medellin distrito"
                  className="w-full rounded-md border border-line px-3 py-2" />
                {hits.length > 0 && (
                  <ul className="max-h-56 overflow-auto rounded-md border border-line text-sm">
                    {hits.map((h) => (
                      <li key={h.buyer_id}>
                        <button type="button" onClick={() => { setBuyer(h); setHits([]); }}
                          className="w-full px-3 py-1.5 text-left hover:bg-paper">
                          {h.buyer_name}
                          <span className="block text-xs text-muted">
                            {[h.buyer_city, h.buyer_department].filter(Boolean).join(", ")}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
            {errors.buyer && <p className="text-sm text-red-700">{errors.buyer}</p>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Signing date" error={errors.signed_at}>
              <input type="date" {...field("signed_at")} className={INPUT} />
            </Field>
            <Field label="Planned duration (days)" error={errors.planned_duration_days}>
              <input type="number" inputMode="numeric" {...field("planned_duration_days")}
                className={INPUT} />
            </Field>
            <Field label="Procurement method" error={errors.procurement_method}>
              <select {...field("procurement_method")} className={INPUT}>
                {METHODS.map((m) => <option key={m}>{m}</option>)}
              </select>
            </Field>
            <Field label="Contract type" error={errors.contract_type}>
              <select {...field("contract_type")} className={INPUT}>
                {TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="Awarded value (COP)" error={errors.award_value}>
              <input type="number" inputMode="numeric" {...field("award_value")} className={INPUT} />
            </Field>
            <Field label="Tender budget (COP, optional)" error={errors.tender_budget}>
              <input type="number" inputMode="numeric" {...field("tender_budget")} className={INPUT} />
            </Field>
            <Field label="Number of bidders (optional)" error={errors.n_bidders}>
              <input type="number" inputMode="numeric" {...field("n_bidders")} className={INPUT} />
            </Field>
            <Field label="Supplier is a natural person">
              <select {...field("supplier_is_natural_person")} className={INPUT}>
                <option value="yes">Yes</option><option value="no">No</option>
                <option value="">Unknown</option>
              </select>
            </Field>
          </div>

          <button type="submit" disabled={busy || api !== "ready"}
            className="rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-50">
            {busy ? "Scoring…" : "Estimate risk"}
          </button>
          {failure && (
            <div role="alert" className="flex items-center justify-between gap-3 text-sm text-red-700">
              <span>{failure}</span>
              <button type="submit" className="shrink-0 rounded border border-red-300 px-2 py-1">
                Try again
              </button>
            </div>
          )}
        </form>
      </section>

      <aside className="space-y-4 rounded-lg border border-line bg-white p-4" aria-live="polite">
        <h2 className="text-lg font-semibold">Result</h2>
        {!score ? (
          <p className="text-sm text-muted">Fill in the form and press “Estimate risk”.</p>
        ) : (
          <>
            <div className="space-y-2">
              <RiskBadge label="Value addition" score={score.value_addition} />
              <Signals signals={score.value_addition.top_signals} />
            </div>
            <div className="space-y-2">
              <RiskBadge label="Time extension" score={score.time_extension} />
              <Signals signals={score.time_extension.top_signals} />
            </div>
            {score.warnings.length > 0 && (
              <ul className="list-disc pl-5 text-xs text-muted">
                {score.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            )}
            <p className="text-xs text-muted">{result?.disclaimer ?? DISCLAIMER}</p>
          </>
        )}
      </aside>
    </div>
  );
}

const INPUT = "w-full rounded-md border border-line bg-white px-3 py-2 aria-[invalid=true]:border-red-500";

function Field({ label, error, children }: {
  label: string; error?: string; children: React.ReactElement<{ id: string }>;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={children.props.id} className="text-sm font-medium">{label}</label>
      {children}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
