// One number formatter so the map popup, legend, and chart agree: thousands get grouped and dropped
// to whole units; small magnitudes keep one decimal so rates like "14.3 per 10k" stay legible.
export function formatNum(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return Math.abs(n) >= 100 ? n.toLocaleString("en-GB", { maximumFractionDigits: 0 }) : n.toFixed(1);
}
