import { vars } from '../styles/contract.css';

/**
 * Opens the hosted documentation. Docs live online (Cloudflare Pages); there is
 * no bundled offline renderer, so when the network is unavailable we surface a
 * quiet notice instead of opening a dead tab.
 *
 * In a Tauri build the system browser is driven via the opener plugin
 * (`openUrl`); on the web we fall back to `window.open`.
 */
export const DOCS_URL = 'https://gettessera.xyz/docs';

const OFFLINE_MESSAGE = 'Documentation is hosted online. Reconnect to open it.';

function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

export async function openDocs(): Promise<void> {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    showOfflineNotice();
    return;
  }
  try {
    if (isTauri()) {
      const { openUrl } = await import('@tauri-apps/plugin-opener');
      await openUrl(DOCS_URL);
    } else {
      window.open(DOCS_URL, '_blank', 'noopener');
    }
  } catch {
    showOfflineNotice();
  }
}

// Minimal, self-contained notice — no toast system exists yet. A single
// non-blocking, auto-dismissing element styled from design tokens; repeated
// calls reuse the same node rather than stacking.
let noticeTimer: number | undefined;

function showOfflineNotice(): void {
  if (typeof document === 'undefined') return;
  const id = 'tessera-docs-notice';
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement('div');
    el.id = id;
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    Object.assign(el.style, {
      position: 'fixed',
      left: '50%',
      bottom: vars.space[6],
      transform: 'translateX(-50%)',
      maxWidth: 'min(420px, 90vw)',
      padding: `${vars.space[3]} ${vars.space[4]}`,
      backgroundColor: vars.color.panel2,
      color: vars.color.fore,
      border: `1px solid ${vars.color.line}`,
      borderRadius: vars.radius.button,
      boxShadow: vars.shadow.pop,
      fontFamily: vars.font.sans,
      fontSize: vars.fontSize.meta,
      lineHeight: vars.lineHeight.snug,
      zIndex: '200',
      pointerEvents: 'none',
    } satisfies Partial<CSSStyleDeclaration>);
    document.body.appendChild(el);
  }
  el.textContent = OFFLINE_MESSAGE;
  window.clearTimeout(noticeTimer);
  noticeTimer = window.setTimeout(() => el?.remove(), 4000);
}
