import { describe, expect, it } from 'vitest';
import { parseViewPath } from './routes';

// @pytest.mark.issue("ISS-339") / @pytest.mark.issue("ISS-572") equivalent for
// vitest: this suite used `it.fails` (the vitest analogue of
// xfail(strict=True)) as proof until the fix landed. FIX-397 mirrored
// next.config.ts's redirects() in parseViewPath, so `.fails` was removed.
//
// BUG-20260828-042311-settings: next.config.ts's server-only redirects()
// rules have no client-side mirror in parseViewPath, so a client-side
// transition (pushState/popstate, router.push, same-origin <Link>) to one of
// the 4 bare paths it redirects falls through to `unknown` -> the 404 page,
// while a cold/full navigation to the identical path redirects correctly.
//
// ISS-339 (root): /settings -> /settings/profile (next.config.ts:26-30)
// ISS-572 (sibling): /library/agents|skills|hooks -> /library[...]
//   (next.config.ts:11-25)

describe('parseViewPath — client-side mirror of next.config.ts redirects (ISS-339, ISS-572)', () => {
  it(
    'ISS-339 — bare /settings resolves like the cold-load redirect to /settings/profile, not unknown',
    () => {
      const parsed = parseViewPath(['settings']);
      expect(parsed).toEqual({ screen: 'settings-profile' });
    },
  );

  it(
    'ISS-572 — /library/agents resolves like the cold-load redirect to /library, not unknown',
    () => {
      const parsed = parseViewPath(['library', 'agents']);
      expect(parsed).toEqual({ screen: 'library' });
    },
  );

  it(
    'ISS-572 — /library/skills resolves like the cold-load redirect to /library, not unknown',
    () => {
      const parsed = parseViewPath(['library', 'skills']);
      expect(parsed).toEqual({ screen: 'library' });
    },
  );

  it(
    'ISS-572 — /library/hooks resolves like the cold-load redirect to /library, not unknown',
    () => {
      const parsed = parseViewPath(['library', 'hooks']);
      expect(parsed).toEqual({ screen: 'library' });
    },
  );
});
