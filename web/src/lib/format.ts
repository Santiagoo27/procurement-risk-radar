export function pct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "not enough data";
  return `${(x * 100).toFixed(digits)}%`;
}

export function cop(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const units: [number, string][] = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
  for (const [size, suffix] of units) {
    if (Math.abs(x) >= size) {
      const value = x / size;
      const text = Number.isInteger(value) ? value.toFixed(0) : String(Number(value.toFixed(2)));
      return `$${text}${suffix} COP`;
    }
  }
  return `$${x.toFixed(0)} COP`;
}

export function days(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const n = Math.round(x);
  return `${n} ${n === 1 ? "day" : "days"}`;
}

export function isoDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric",
    timeZone: "UTC" });
}

export function count(n: number): string {
  return n.toLocaleString("en-US");
}
