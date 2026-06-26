import { describe, expect, it } from 'vitest';
import { dashboardModules, MODULES, navModules } from './registry';

describe('navModules', () => {
  it('no args -> all nav modules in default order', () => {
    const ids = navModules().map((m) => m.id);
    expect(ids).toContain('grid');
    expect(ids).toContain('settings');
    // dashboard has surface 'both' so it appears in nav too.
    expect(ids).toContain('dashboard');
    // sorted by defaultOrder.
    expect(ids.indexOf('grid')).toBeLessThan(ids.indexOf('settings'));
  });

  it('a user-hidden module drops from nav', () => {
    const ids = navModules({ hidden: ['videos'] }).map((m) => m.id);
    expect(ids).not.toContain('videos');
    expect(ids).toContain('grid');
  });

  it('user order overrides default order', () => {
    const ids = navModules({ order: ['settings', 'grid'] }).map((m) => m.id);
    expect(ids[0]).toBe('settings');
    expect(ids[1]).toBe('grid');
  });

  it('a gated-off capability hides its module regardless of prefs', () => {
    // people is gated 'faces'; with faces=false it must not appear even if the
    // user did not hide it (the two axes never merge).
    const ids = navModules({}, { faces: false }).map((m) => m.id);
    expect(ids).not.toContain('people');
    // a gated module whose capability is true still shows.
    const withFaces = navModules({}, { faces: true }).map((m) => m.id);
    expect(withFaces).toContain('people');
  });

  it('a gated module is never user-toggleable away from its gate (gate wins)', () => {
    // even if the user "ordered" people, faces=false still hides it.
    const ids = navModules({ order: ['people', 'grid'] }, { faces: false }).map((m) => m.id);
    expect(ids).not.toContain('people');
  });
});

describe('dashboardModules', () => {
  it('returns only surface dashboard|both modules', () => {
    const ids = dashboardModules().map((m) => m.id);
    // dashboard is 'both'; grid is 'nav' only.
    expect(ids).toContain('dashboard');
    expect(ids).not.toContain('grid');
  });

  it('applies hidden + order prefs and server gates', () => {
    const both = MODULES.filter((m) => m.surface === 'dashboard' || m.surface === 'both');
    expect(both.length).toBeGreaterThan(0);
    const ids = dashboardModules({ hidden: ['dashboard'] }).map((m) => m.id);
    expect(ids).not.toContain('dashboard');
  });
});
