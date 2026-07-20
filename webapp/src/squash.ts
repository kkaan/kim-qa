// Multi-gap dead-time compression (display only). Generalises the deck
// widget's single-largest-gap squash: EVERY gap > minGap collapses to `keep`
// seconds. Metrics and residuals must always use true, uncompressed times.
export type CompressBand = { x0: number; x1: number; removed: number };

export function multiGapSquash(times: number[], minGap = 20, keep = 7): {
  map: (x: number) => number;
  invert: (d: number) => number;
  bands: CompressBand[];
} {
  type Gap = { lo: number; hi: number; span: number; keep: number };
  const gaps: Gap[] = [];
  for (let i = 1; i < times.length; i++) {
    const span = times[i] - times[i - 1];
    if (span > minGap) {
      gaps.push({ lo: times[i - 1], hi: times[i], span, keep: Math.min(keep, span) });
    }
  }
  if (!gaps.length) return { map: (x) => x, invert: (d) => d, bands: [] };

  // Cumulative seconds removed before each gap's start.
  const removedBefore: number[] = [];
  let acc = 0;
  for (const g of gaps) {
    removedBefore.push(acc);
    acc += g.span - g.keep;
  }

  const map = (x: number): number => {
    for (let i = gaps.length - 1; i >= 0; i--) {
      const g = gaps[i];
      if (x >= g.hi) return x - (removedBefore[i] + (g.span - g.keep));
      if (x > g.lo) {
        return g.lo - removedBefore[i] + ((x - g.lo) / g.span) * g.keep;
      }
    }
    return x;
  };

  // Inverse of `map`: display (compressed) coordinate -> true time. Lets callers
  // that only see display coordinates (e.g. a Plotly drag-select range) recover
  // the true time before persisting it, so metrics always run on real samples.
  const invert = (d: number): number => {
    for (let i = gaps.length - 1; i >= 0; i--) {
      const g = gaps[i];
      const b0 = g.lo - removedBefore[i];
      const b1 = b0 + g.keep;
      if (d >= b1) return d + removedBefore[i] + (g.span - g.keep);
      if (d > b0) return g.lo + ((d - b0) / g.keep) * g.span;
    }
    return d;
  };

  const bands: CompressBand[] = gaps.map((g, i) => ({
    x0: g.lo - removedBefore[i],
    x1: g.lo - removedBefore[i] + g.keep,
    removed: g.span,
  }));
  return { map, invert, bands };
}
