import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { computeResiduals, metricsTable } from './lib';

const golden = JSON.parse(readFileSync(
  resolve(__dirname, '../../tests/golden/overlay_metrics.json'), 'utf-8'));

describe('lib.ts matches Python overlay metrics', () => {
  it('reproduces the golden metric rows', () => {
    const res = computeResiduals(
      golden.kim,
      { t: golden.hex.t, lr: golden.hex.lr, si: golden.hex.si, ap: golden.hex.ap },
      golden.offset, [],
    );
    const rows = metricsTable(res);
    for (let i = 0; i < rows.length; i++) {
      const exp = golden.expected_rows[i];
      expect(rows[i].name).toBe(exp.name);
      expect(rows[i].mean).toBeCloseTo(exp.mean, 9);
      expect(rows[i].std).toBeCloseTo(exp.std, 9);
      expect(rows[i].p5).toBeCloseTo(exp.p5, 9);
      expect(rows[i].p95).toBeCloseTo(exp.p95, 9);
    }
  });
});
