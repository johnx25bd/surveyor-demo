// The Ordnance Survey GeoDataViz palettes — the only colours used for data. Verbatim from the
// design system's GDV-colour-palettes.json. Never invent ad-hoc chart/map colours; reach for these.

export const GDV = {
  // 8-hue qualitative — categorical series, point layers.
  qualitative: [
    "#FF1F5B",
    "#00CD6C",
    "#009ADE",
    "#AF58BA",
    "#FFC61E",
    "#F28522",
    "#A0B1BA",
    "#A6761D",
  ],
  // Sequential 7-stop ramps. `m2` is the warm magenta-red ramp the Surveyor mockup uses for its
  // headline choropleth; `s1` is a calm blue for neutral magnitudes.
  sequential: {
    s1: ["#E4F1F7", "#C5E1EF", "#9EC9E2", "#6CB0D6", "#3C93C2", "#226E9C", "#0D4A70"],
    s2: ["#E1F2E3", "#CDE5D2", "#9CCEA7", "#6CBA7D", "#40AD5A", "#228B3B", "#06592A"],
    m1: ["#B7E6A5", "#7CCBA2", "#46AEA0", "#089099", "#00718B", "#045275", "#003147"],
    m2: ["#FCE1A4", "#FABF7B", "#F08F6E", "#E05C5C", "#D12959", "#AB1866", "#6E005F"],
  },
} as const;

export type SequentialName = keyof typeof GDV.sequential;

export const DEFAULT_RAMP: SequentialName = "m2";

// Number of choropleth/chart classes, and the colour for areas with no value. One definition so the
// map and the ranked chart classify identically (rather than each re-deriving breaks and a no-data hex).
export const CLASSES = 7;
export const NODATA = "#c9c2b4";

/**
 * Quantile class breaks for a set of values. Returns the inner break points (length = classes - 1),
 * so a 7-colour ramp gets 6 breaks. Honest about ties: duplicate breaks are de-duplicated, which
 * just collapses empty classes rather than inventing precision the data doesn't have.
 */
export function quantileBreaks(values: number[], classes: number): number[] {
  const sorted = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (sorted.length === 0) return [];
  const breaks: number[] = [];
  for (let i = 1; i < classes; i++) {
    const q = (sorted.length - 1) * (i / classes);
    const lo = Math.floor(q);
    const hi = Math.ceil(q);
    const value = sorted[lo] + (sorted[hi] - sorted[lo]) * (q - lo);
    breaks.push(value);
  }
  return Array.from(new Set(breaks));
}

/** Pick the ramp colour for a value given inner break points. */
export function colourFor(value: number, breaks: number[], ramp: readonly string[]): string {
  let cls = 0;
  while (cls < breaks.length && value > breaks[cls]) cls++;
  // Spread the (possibly fewer) classes across the full ramp so endpoints stay vivid.
  const idx = breaks.length === 0 ? 0 : Math.round((cls / breaks.length) * (ramp.length - 1));
  return ramp[Math.min(idx, ramp.length - 1)];
}

/**
 * Build a value→colour function for a set of records: quantile-classify the finite values onto the
 * ramp, returning NODATA for missing/non-finite. Shared by the map and the chart so a value gets the
 * same colour in both.
 */
export function classify<T>(
  records: T[],
  value: (r: T) => number,
  ramp: readonly string[] = GDV.sequential[DEFAULT_RAMP],
): (r: T) => string {
  const breaks = quantileBreaks(records.map(value).filter(Number.isFinite), CLASSES);
  return (record) => {
    const v = value(record);
    return Number.isFinite(v) ? colourFor(v, breaks, ramp) : NODATA;
  };
}
