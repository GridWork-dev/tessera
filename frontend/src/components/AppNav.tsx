import { Link, useRouterState } from '@tanstack/react-router';
import { useCapabilities, useUiPrefs } from '../hooks/queries';
import { navModules } from '../modules/registry';
import * as ws from '../styles/workspace.css';
import * as css from './AppNav.css';
import { BrandFacet } from './BrandFacet';

/**
 * Brand wordmark + primary nav — the shared left cluster of every command bar.
 * Nav items come from the module registry (navModules()); with no prefs/caps it
 * yields today's 9 items in order, so output is unchanged this wave.
 */
export function AppNav() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  // Two axes, both applied: server capability gates (faces/geo/video) AND user
  // order/hidden prefs. Until either query resolves, navModules falls back to the
  // registry defaults so the nav renders immediately (no flash of empty chrome).
  const caps = useCapabilities();
  const prefs = useUiPrefs();
  const items = navModules(prefs.data?.ui.nav, caps.data);
  return (
    <>
      <Link to="/" className={css.brandMark} aria-label="Tessera — home">
        <span className={css.brandGlyph}>
          <BrandFacet />
        </span>
        <span className={css.brandWord}>Tessera</span>
      </Link>

      <nav className={css.nav} aria-label="Primary">
        {items.map((m) => {
          const Icon = m.icon;
          const active = pathname === m.route;
          return (
            <Link
              key={m.id}
              to={m.route as '/'}
              className={`${ws.iconButton}${active ? ` ${ws.iconButtonActive}` : ''}`}
              aria-current={active ? 'page' : undefined}
              aria-label={m.label}
              title={m.label}
            >
              <Icon size={16} />
            </Link>
          );
        })}
      </nav>
    </>
  );
}
