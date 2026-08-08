// Ground-truth curve construction: explicit irregular t (baseline KIM logs)
// vs fixed-dt reconstruction (hexamotion traces).
import { describe, expect, it } from 'vitest';
import { hexCurveFromPayload } from './lib';

describe('hexCurveFromPayload', () => {
  it('uses an explicit t array verbatim (baseline KIM ground truth)', () => {
    const t = [0, 0.15, 0.33, 0.41];
    const c = hexCurveFromPayload({ t, n: 4, lr: [1, 2, 3, 4], si: [5, 6, 7, 8], ap: [9, 10, 11, 12] });
    expect(c.t).toEqual(t);
    expect(c.si).toEqual([5, 6, 7, 8]);
  });

  it('reconstructs i*dt when only dt/n are present (hexamotion trace)', () => {
    const c = hexCurveFromPayload({ dt: 0.02, n: 3, lr: [0, 0, 0], si: [1, 1, 1], ap: [2, 2, 2] });
    expect(c.t).toEqual([0, 0.02, 0.04]);
  });
});
