import { Check } from 'lucide-react';
import { type CSSProperties, useState } from 'react';
import { ACCENTS, accentInk } from '../styles/accents';
import { getStoredAccent, getStoredTheme, setAccent, setTheme } from '../styles/themeStore';
import { isLightTheme, THEME_IDS, type ThemeId } from '../styles/themes';
import * as s from '../styles/workspace.css';
import { AppNav } from './AppNav';
import { LabelSetsManager } from './LabelSetsManager';
import { LicensePanel } from './LicensePanel';
import { NavCustomizer } from './NavCustomizer';
import * as css from './SettingsView.css';

/** Human-readable preset names for the Appearance switcher. */
const THEME_LABELS: Record<ThemeId, string> = {
  pigment: 'Pigment',
  'slate-warm': 'Slate',
  'obsidian-cool': 'Obsidian',
  light: 'Light',
};

/**
 * Settings page — standard app chrome (command bar + shared nav) over a centered
 * content well with stacked sections: License (Spec J), a keyboard-shortcut
 * reference (the real, in-app bindings), and a truthful About card. The well
 * takes further sections without re-chroming.
 */

interface Shortcut {
  keys: string[];
  label: string;
}

/** Mirrors the live bindings in Browse.tsx / CommandBar.tsx / Lightbox.tsx /
 *  VideosView.tsx — kept in sync by hand (small, rarely-changing surface). */
const BROWSE_KEYS: Shortcut[] = [
  { keys: ['⌘', 'K'], label: 'Open command palette' },
  { keys: ['/'], label: 'Focus search' },
  { keys: ['[', ']'], label: 'Previous / next page' },
  { keys: ['K'], label: 'Keep selected asset' },
  { keys: ['M'], label: 'Maybe selected asset' },
  { keys: ['R'], label: 'Reject selected asset' },
  { keys: ['Esc'], label: 'Clear selection / search' },
];

const MEDIA_KEYS: Shortcut[] = [
  { keys: ['←', '→'], label: 'Previous / next image (lightbox)' },
  { keys: ['Space'], label: 'Play / pause (video)' },
  { keys: ['←', '→'], label: 'Seek ∓5s (video)' },
  { keys: ['Esc'], label: 'Close lightbox / player' },
];

function ShortcutRows({ rows }: { rows: Shortcut[] }) {
  return (
    <>
      {rows.map((sc) => (
        <div key={sc.label} className={css.shortcutRow}>
          <span className={css.shortcutLabel}>{sc.label}</span>
          <span className={css.keys}>
            {sc.keys.map((k) => (
              <kbd key={k} className={s.kbd}>
                {k}
              </kbd>
            ))}
          </span>
        </div>
      ))}
    </>
  );
}

export function SettingsView() {
  // Seed from the persisted theme; setTheme (Wave 1 store) persists to
  // localStorage + /api/ui-prefs and applies the class on <html>.
  const [theme, setThemeState] = useState<ThemeId>(() => getStoredTheme());
  const [accent, setAccentState] = useState<string>(() => getStoredAccent());
  const selectTheme = (id: ThemeId) => {
    setTheme(id);
    setThemeState(id);
  };
  const selectAccent = (id: string) => {
    setAccent(id);
    setAccentState(id);
  };

  return (
    <div className={s.appFrame}>
      <header className={s.commandBar}>
        <AppNav />
        <span className={s.pageTitle}>Settings</span>
        <span className={s.barSpacer} />
      </header>

      <div className={css.scroll}>
        <div className={css.inner}>
          {/* License (Spec J) */}
          <section className={css.section} aria-label="License">
            <div className={css.sectionHead}>
              <h2 className={css.sectionTitle}>License</h2>
              <p className={css.sectionLead}>
                Activate a key to unlock Pro features. The app is fully usable without one.
              </p>
            </div>
            <LicensePanel />
          </section>

          {/* Appearance — theme switcher + accent picker (Wave 2a / Wave 4) */}
          <section className={css.section} aria-label="Appearance">
            <div className={css.sectionHead}>
              <h2 className={css.sectionTitle}>Appearance</h2>
              <p className={css.sectionLead}>Choose a theme and a signal accent.</p>
            </div>
            <div className={css.panel}>
              <div className={css.appearanceGroup}>
                <span className={css.groupLabel}>Theme</span>
                <div className={css.themeSwitch}>
                  {THEME_IDS.map((id) => {
                    const active = theme === id;
                    return (
                      <button
                        key={id}
                        type="button"
                        className={`${css.themeOption}${active ? ` ${css.themeOptionActive}` : ''}`}
                        aria-pressed={active}
                        onClick={() => selectTheme(id)}
                      >
                        {active && <Check size={14} aria-hidden />}
                        {THEME_LABELS[id]}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className={css.appearanceGroup}>
                <span className={css.groupLabel}>Accent</span>
                <div className={css.accentSwitch} role="radiogroup" aria-label="Accent color">
                  {ACCENTS.map((a) => {
                    const active = accent === a.id;
                    const swatch = isLightTheme(theme) ? a.light : a.dark;
                    return (
                      // biome-ignore lint/a11y/useSemanticElements: styled swatch picker intentionally uses the ARIA radiogroup/radio pattern (native inputs can't carry the swatch styling)
                      <button
                        key={a.id}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        aria-label={a.label}
                        title={a.label}
                        className={`${css.accentSwatch}${active ? ` ${css.accentSwatchActive}` : ''}`}
                        style={{ '--swatch': swatch, '--tick': accentInk(swatch) } as CSSProperties}
                        onClick={() => selectAccent(a.id)}
                      >
                        {active && <Check size={14} aria-hidden className={css.accentCheck} />}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </section>

          {/* Navigation — reorder + hide nav modules (Wave 2b) */}
          <section className={css.section} aria-label="Navigation">
            <div className={css.sectionHead}>
              <h2 className={css.sectionTitle}>Navigation</h2>
              <p className={css.sectionLead}>
                Reorder or hide nav modules. Drag the handle to reorder; toggle to hide. Features
                your server doesn't provide show as unavailable.
              </p>
            </div>
            <div className={css.panel}>
              <NavCustomizer surface="nav" />
            </div>
          </section>

          {/* Dashboard — reorder + hide dashboard cards (Wave 2b) */}
          <section className={css.section} aria-label="Dashboard cards">
            <div className={css.sectionHead}>
              <h2 className={css.sectionTitle}>Dashboard cards</h2>
              <p className={css.sectionLead}>Reorder or hide the cards on the Dashboard.</p>
            </div>
            <div className={css.panel}>
              <NavCustomizer surface="dashboard" />
            </div>
          </section>

          {/* Label sets — custom faceted labels (Wave 2b) */}
          <section className={css.section} aria-label="Label sets">
            <div className={css.sectionHead}>
              <h2 className={css.sectionTitle}>Label sets</h2>
              <p className={css.sectionLead}>
                Define your own facets — single-select (like Rating) or multi-select. Drag to
                reorder; values carry a color used in the inspector and filters.
              </p>
            </div>
            <div className={css.panel}>
              <LabelSetsManager />
            </div>
          </section>

          {/* Keyboard shortcuts — the real in-app bindings */}
          <section className={css.section} aria-label="Keyboard shortcuts">
            <div className={css.sectionHead}>
              <h2 className={css.sectionTitle}>Keyboard shortcuts</h2>
              <p className={css.sectionLead}>
                Tessera is keyboard-first. These work anywhere outside a text field.
              </p>
            </div>
            <div className={css.panel}>
              <div className={css.shortcutGroup}>
                <span className={css.groupLabel}>Browse &amp; triage</span>
                <ShortcutRows rows={BROWSE_KEYS} />
                <span className={css.groupLabel}>Lightbox &amp; video</span>
                <ShortcutRows rows={MEDIA_KEYS} />
              </div>
            </div>
          </section>

          {/* About — truthful identity + privacy posture (no fabricated version) */}
          <section className={css.section} aria-label="About">
            <div className={css.sectionHead}>
              <h2 className={css.sectionTitle}>About</h2>
            </div>
            <div className={css.panel}>
              <dl className={css.aboutGrid}>
                <dt className={css.aboutKey}>Application</dt>
                <dd className={css.aboutVal}>Tessera</dd>

                <dt className={css.aboutKey}>License</dt>
                <dd className={css.aboutVal}>AGPL-3.0-only · open source</dd>

                <dt className={css.aboutKey}>Privacy</dt>
                <dd className={css.aboutVal}>
                  Your images, faces, and embeddings stay on this machine. Tagging, search, and
                  similarity run against local models — nothing about your library is uploaded.
                </dd>
              </dl>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
