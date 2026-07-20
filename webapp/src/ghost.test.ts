import { describe, expect, it } from 'vitest';
import { asRecorded } from './ghost';

describe('asRecorded', () => {
  // Fixture mirrors tests/fixtures.py make_interrupt_session: corrected SI
  // segment 1 = raw - 1.2, so ghost (as-recorded) = corrected + 1.2.
  const events = [{ t_after: 9, lr: 0.3, si: 1.2, ap: 1.7 }];
  const fileIndex = [0, 0, 1, 1];

  it('is null before any shift, corrected + cum after', () => {
    const g = asRecorded([2.0, 2.1, 2.2, 2.3], fileIndex, events, 'si');
    expect(g[0]).toBeNull();
    expect(g[1]).toBeNull();
    expect(g[2]).toBeCloseTo(3.4);
    expect(g[3]).toBeCloseTo(3.5);
  });

  it('accumulates across multiple shifts', () => {
    const two = [
      { t_after: 9, lr: 0, si: 1.0, ap: 0 },
      { t_after: 20, lr: 0, si: 0.5, ap: 0 },
    ];
    const g = asRecorded([0, 0, 0], [0, 1, 2], two, 'si');
    expect(g[1]).toBeCloseTo(1.0);
    expect(g[2]).toBeCloseTo(1.5);
  });
});
