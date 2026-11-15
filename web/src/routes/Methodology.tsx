import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { DISCLAIMER } from "../components/Disclaimer";
import {
  loadAmendmentSize, loadMonitoring, loadSummary,
  type AmendmentSize, type Monitoring, type Summary,
} from "../lib/data";
import { count, pct } from "../lib/format";

const REPO = "https://github.com/Santiagoo27/procurement-risk-radar";
const doc = (path: string) => `${REPO}/blob/main/${path}`;

export default function Methodology() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [monitoring, setMonitoring] = useState<Monitoring | null>(null);
  const [size, setSize] = useState<AmendmentSize | null>(null);
  useEffect(() => {
    loadSummary().then(setSummary).catch(() => setSummary(null));
    loadMonitoring().then(setMonitoring);
    loadAmendmentSize().then(setSize);
  }, []);

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

      {size && (
        <Section title="How big are additions?">
          {size.median_increase_pct === null ? (
            <p className="text-sm text-muted">
              Not enough data yet: {size.reason}. The archive started on {size.since}.
            </p>
          ) : (
            <p>
              SECOP does not publish the amount of each addition, so a nightly archive records
              every contract's value since {size.since}. So far {count(size.n_increased)}{" "}
              contracts have increased in value. The median increase is{" "}
              <b>{pct(size.median_increase_pct)}</b>; one in four rose by more than{" "}
              {pct(size.p75_increase_pct)}, and {pct(size.share_over_30pct)} rose by more than
              30%. These are early figures and will stabilise as the archive grows.
            </p>
          )}
        </Section>
      )}

      {monitoring && (
        <Section title="Model health">
          <ModelHealth monitoring={monitoring} />
        </Section>
      )}

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
          does not rank suppliers. Contracts with a natural-person supplier are listed without
          their identifier or SECOP link, because the SECOP page names the person. Contracts
          with no recorded value are scored but not listed.
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

const STATUS: Record<Monitoring["status"], string> = {
  ok: "OK: recent contracts look like the training data",
  watch: "Watch: some inputs or results have shifted",
  insufficient_data: "Not enough recent data to check yet",
};

function ModelHealth({ monitoring: m }: { monitoring: Monitoring }) {
  const top = m.feature_drift.filter((d) => d.psi !== null && !d.expected).slice(0, 5);
  return (
    <div className="space-y-3 text-sm">
      <p>
        <b>{STATUS[m.status]}</b> (checked {m.as_of}, {m.n_current.toLocaleString("en-US")}{" "}
        contracts signed {m.windows.current[0]} to {m.windows.current[1]}).
      </p>
      {top.length > 0 && (
        <table className="text-sm">
          <thead className="text-left text-muted">
            <tr><th className="pr-4 font-medium">Input</th>
              <th className="pr-4 font-medium">Shift (PSI)</th><th /></tr>
          </thead>
          <tbody className="tabular-nums">
            {top.map((d) => (
              <tr key={d.feature}>
                <td className="pr-4">{d.label}</td>
                <td className="pr-4">{d.psi?.toFixed(2)}</td>
                <td>{d.shifted && <span className="rounded bg-amber-100 px-1 text-xs text-amber-900">shifted</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="text-muted">
        {m.realized.pr_auc !== null
          ? `On contracts that closed after the model was trained, PR-AUC is ${m.realized.pr_auc.toFixed(3)} with a base rate of ${((m.realized.positive_rate ?? 0) * 100).toFixed(1)}% (n = ${m.realized.n.toLocaleString("en-US")}; test PR-AUC ${m.realized.test_pr_auc?.toFixed(3)}). PR-AUC rises with the base rate, so compare it with care.`
          : `Out-of-time performance: ${m.realized.reason}.`}{" "}
        PSI above 0.2 means an input's distribution has shifted noticeably since training.
        Calendar inputs and history counts are left out: they change with the season and
        as the archive grows.
      </p>
    </div>
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
