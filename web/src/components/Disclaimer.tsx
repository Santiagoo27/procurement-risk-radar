export const DISCLAIMER =
  "Scores are statistical estimates for analysis, not allegations of wrongdoing.";

export function Disclaimer() {
  return (
    <footer className="border-t border-line bg-white px-4 py-6 text-sm text-muted">
      <div className="mx-auto max-w-6xl space-y-2">
        <p className="font-medium text-ink">{DISCLAIMER}</p>
        <p>
          Data: SECOP II open data, Colombia Compra Eficiente (datos.gov.co). Boundaries:
          geoBoundaries (CC BY 4.0) and DANE DIVIPOLA (CC BY-SA 4.0).
        </p>
        <p>
          <a className="underline" href="https://github.com/Santiagoo27/procurement-risk-radar">
            Source code, data audit and model card
          </a>
        </p>
      </div>
    </footer>
  );
}
