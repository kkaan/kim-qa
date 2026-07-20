import { describe, expect, it } from 'vitest';
import { multiGapSquash } from './squash';

describe('multiGapSquash', () => {
  it('is identity when no gaps exceed the threshold', () => {
    const { map, bands } = multiGapSquash([0, 1, 2, 3], 20, 7);
    expect(bands).toEqual([]);
    expect(map(2.5)).toBe(2.5);
  });

  it('collapses each qualifying gap to keep seconds', () => {
    // gaps: 51 s (10->61) and 30 s (70->100); both collapse to 7 s
    const t = [0, 5, 10, 61, 65, 70, 100, 105];
    const { map, bands } = multiGapSquash(t, 20, 7);
    expect(bands.length).toBe(2);
    expect(map(10)).toBe(10);                    // before first gap: identity
    expect(map(61)).toBeCloseTo(17);             // 10 + 7
    expect(map(70)).toBeCloseTo(26);             // 17 + (70-61)
    expect(map(100)).toBeCloseTo(33);            // 26 + 7
    expect(map(105)).toBeCloseTo(38);
    expect(bands[0]).toEqual({ x0: 10, x1: 17, removed: 51 });
    expect(bands[1].removed).toBe(30);
  });

  it('maps interior gap points proportionally and stays monotonic', () => {
    const t = [0, 10, 61];
    const { map } = multiGapSquash(t, 20, 7);
    expect(map(35.5)).toBeCloseTo(13.5);         // halfway through the band
    for (let x = 0; x < 60; x += 0.5) {
      expect(map(x + 0.5)).toBeGreaterThan(map(x));
    }
  });

  it('invert is identity when no gaps exceed the threshold', () => {
    const { invert } = multiGapSquash([0, 1, 2, 3], 20, 7);
    expect(invert(2.5)).toBe(2.5);
  });

  it('invert recovers true time from display coordinates (round-trip)', () => {
    const t = [0, 5, 10, 61, 65, 70, 100, 105];
    const { map, invert } = multiGapSquash(t, 20, 7);
    // Sampled points that fall outside the collapsed gaps round-trip exactly.
    for (const x of [0, 5, 10, 61, 65, 70, 100, 105, 8, 63, 102]) {
      expect(invert(map(x))).toBeCloseTo(x);
    }
    // A range selected after the compressed gap must map back to real time, not
    // to the display coordinate ~ (removed) seconds earlier.
    expect(invert(map(80))).toBeCloseTo(80);
    expect(invert(30)).toBeGreaterThan(map(30)); // display 30 -> a later true time
  });
});
