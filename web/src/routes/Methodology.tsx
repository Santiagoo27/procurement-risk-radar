import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { DISCLAIMER } from "../components/Disclaimer";
import { loadSummary, type Summary } from "../lib/data";
import { count, pct } from "../lib/format";

const REPO = "https://github.com/Santiagoo27/procurement-risk-radar";
const doc = (path: string) => `${REPO}/blob/main/${path}`;

export default function Methodology() {
  const [summary, setSummary] = useState<Summary | null>(null);
  useEffect(() => { loadSummary().then(setSummary).catch(() => setSummary(null)); }, []);

  return (
    <article className="max-w-3xl space-y-8 leading-relaxed">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Methodology</h1>
        <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {DISCLAIMER} A score says how often contracts with similar characteristics were
          amended in the past. It is not evidence about any specific contract, buyer or supplier.
        </p>
      </header>

      <Section title="What is predicted">
        <p>
          For each public contract, at the moment it is signed, the model estimates two
          probabilities. The first is that the contract will later receive a <b>value addition</b>.
          The second is that its term will be <b>extended</b>. Only information available on the
          signing day is used: the buyer, the contract type and procurement method, the awarded
          value and tender budget, the planned duration, the number of bidders, and the buyer's
          and supplier's track record up to that day.
        </p>
      </Section>

      <Section title="Data">
        <p>
          Contracts, amendments and tenders come from SECOP II open data published by Colombia
          Compra Eficiente on datos.gov.co.
          {summary && <> The map uses {count(summary.n_closed)} contracts signed between
          2022 and 2024 that have already ended.</>}
        </p>
        <p>
          SECOP records <i>that</i> an amendment happened but not always <i>what</i> it was. The
          data audit found that 71% of value additions are filed as generic modifications. They
          are recovered from the amendment text with a keyword matcher, which was correct in 84%
          of a hand-checked sample. SECOP does not publish the amount of each addition, so the
          model predicts whether one happens, not how large it is.
        </p>
      </Section>

      <Section title="No look-ahead">
        <p>
          A contract counts as finished once its planned end date is more than 180 days in the
          past. The contract status field in SECOP is not kept up to date, so it is not used.
          The buyer and supplier history only includes contracts whose outcome was already
          known on the signing day. The model is trained on contracts signed up to 2022, tuned
          on early 2023, and evaluated on contracts signed from July 2023 to December 2024.
        </p>
      </Section>

      <Section title="How good is it">
        {summary ? <MetricsTable summary={summary} /> : <p className="text-muted">Loading…</p>}
        <p className="text-sm text-muted">
          PR-AUC is the main metric because amendments are a minority. A model that knows
          nothing scores the base rate. Probabilities are calibrated: across contracts scored
          around 15%, about 15% were amended.
        </p>
      </Section>

      <Section title="Reading the map">
        <ul className="list-disc space-y-1 pl-5">
          <li>Regions are placed by where the <b>buying entity</b> is registered, not by where the
            work happens.</li>
          <li>Rates are hidden when a region or buyer has fewer than {summary?.min_n ?? 30} contracts.
            Many small municipalities still publish in SECOP I, which is not included.</li>
          <li>Buyer lists always show the number of contracts behind each rate.</li>
        </ul>
      </Section>

      <Section title="Privacy">
        <p>
          Suppliers who are natural persons are replaced by an anonymous code before any
          processing. This site shows no supplier names or free text from contracts, and it
          does not rank suppliers.
        </p>
      </Section>

      <Section title="Learn more">
        <ul className="list-disc space-y-1 pl-5">
          <li><a className="text-accent underline" href={doc("docs/data-audit.md")}>Data audit</a></li>
          <li><a className="text-accent underline" href={doc("docs/model-card.md")}>Model card</a></li>
          <li><a className="text-accent underline" href={doc("docs/api.md")}>Prediction API</a></li>
          <li><a className="text-accent underline" href={REPO}>Source code</a></li>
          <li><Link className="text-accent underline" to="/try">Score a contract yourself</Link></li>
        </ul>
      </Section>
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function MetricsTable({ summary }: { summary: Summary }) {
  const rows = [
    ["Value addition", summary.model_metrics.has_value_addition],
    ["Time extension", summary.model_metrics.has_time_extension],
  ] as const;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-muted">
          <tr>
            <th className="py-1 pr-3 font-medium">Target</th>
            <th className="py-1 pr-3 font-medium">PR-AUC (base rate)</th>
            <th className="py-1 pr-3 font-medium">ROC-AUC</th>
            <th className="py-1 font-medium">Amended among top 5% riskiest</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line tabular-nums">
          {rows.map(([name, m]) => (
            <tr key={name}>
              <td className="py-1.5 pr-3">{name}</td>
              <td className="py-1.5 pr-3">
                <span>{m?.lightgbm?.pr_auc?.toFixed(3)}</span>
                <span className="text-muted"> ({m?.base_rate?.pr_auc?.toFixed(3)})</span>
              </td>
              <td className="py-1.5 pr-3">{m?.lightgbm?.roc_auc?.toFixed(3)}</td>
              <td className="py-1.5">{pct(m?.lightgbm?.precision_at_top ?? null)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
