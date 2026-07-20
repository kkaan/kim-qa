// As-recorded ghost reconstruction. Sign convention (kim-reporter):
// recorded_post = recorded_pre + applied_shift. apply_couch_shifts on the
// server SUBTRACTS the cumulative shift, so the payload's main trace is the
// shift-removed (no-correction, hex-comparable) trajectory and the
// as-recorded ghost is corrected + cumulative shift for the point's segment.
import type { ShiftEvent } from './api';

export function asRecorded(
  values: number[],
  fileIndex: number[],
  events: ShiftEvent[],
  axis: 'lr' | 'si' | 'ap',
): (number | null)[] {
  const cum: number[] = [0];
  for (const ev of events) cum.push(cum[cum.length - 1] + ev[axis]);
  return values.map((v, i) => {
    const seg = fileIndex[i] ?? 0;
    if (seg === 0) return null;
    return v + cum[Math.min(seg, cum.length - 1)];
  });
}
