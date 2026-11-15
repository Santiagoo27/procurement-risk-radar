import type { Layer } from "../lib/scale";

export function LayerPicker({ layers, value, onChange, estimateUnavailable }: {
  layers: Layer[];
  value: string;
  onChange: (id: string) => void;
  /** When set, estimate layers are disabled and this text explains why. */
  estimateUnavailable?: string;
}) {
  return (
    <div role="radiogroup" aria-label="Map layer" className="flex flex-wrap gap-2">
      {layers.map((layer) => {
        const active = layer.id === value;
        const disabled = layer.estimate && Boolean(estimateUnavailable);
        return (
          <button key={layer.id} type="button" role="radio" aria-checked={active}
            disabled={disabled} title={disabled ? estimateUnavailable : undefined}
            onClick={() => onChange(layer.id)}
            className={`rounded-full border px-3 py-1 text-sm ${active
              ? "border-accent bg-blue-50 text-accent"
              : "border-line bg-white text-muted hover:text-ink"} disabled:cursor-not-allowed
              disabled:opacity-50 disabled:hover:text-muted`}>
            {layer.short}
            {layer.estimate && (
              <span className="ml-1.5 rounded bg-amber-100 px-1 text-xs text-amber-900">
                Estimate
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
