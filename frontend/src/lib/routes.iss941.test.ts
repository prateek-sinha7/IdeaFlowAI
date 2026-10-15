import { describe, it, expect } from 'vitest';
import { parseViewPath } from './routes';

// ISS-941 / QA-KB-084. `it.fails` is vitest's strict xfail: green while the bug
// exists, red (XPASS) the moment the fix lands -> remove `.fails` then.
describe('ISS-941: /runs/{id}/versions edge arities parse to unknown', () => {
  it('ISS-941: bare /runs/r1/versions is unknown', () => {
    expect(parseViewPath(['runs', 'r1', 'versions'])).toEqual({ screen: 'unknown' });
  });
  it('ISS-941: pinned /runs/r1/versions/2/stream is unknown', () => {
    expect(parseViewPath(['runs', 'r1', 'versions', '2', 'stream'])).toEqual({ screen: 'unknown' });
  });
  it('ISS-941: pinned /runs/r1/versions/2/preview/full is unknown', () => {
    expect(parseViewPath(['runs', 'r1', 'versions', '2', 'preview', 'full'])).toEqual({
      screen: 'unknown',
    });
  });
  it('guard: valid pinned and un-pinned forms keep their screens', () => {
    expect(parseViewPath(['runs', 'r1', 'versions', '2'])).toEqual({
      screen: 'run-version', runId: 'r1', version: '2',
    });
    expect(parseViewPath(['runs', 'r1', 'stream'])).toEqual({ screen: 'run-stream', runId: 'r1' });
  });
});
