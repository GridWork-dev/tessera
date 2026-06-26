import { BadgeCheck, Check, KeyRound, Lock, Trash2, TriangleAlert, Upload, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import type { LicenseStatus, ProFeatures } from '../api/license';
import { getLicense, removeLicense, saveLicense } from '../api/license';
import * as css from './LicensePanel.css';

/** The three (and only) capabilities Pro unlocks. No content is ever gated. */
const FEATURES: ReadonlyArray<{ key: keyof ProFeatures; label: string }> = [
  { key: 'bulk_export', label: 'Bulk export' },
  { key: 'remote_compute_routing', label: 'Remote compute routing' },
  { key: 'priority_support', label: 'Priority support' },
];

type Msg = { kind: 'ok' | 'error'; text: string };

/**
 * Settings → License (Spec J / PART 5). Shows the current entitlement, what Pro
 * unlocks, a soft dismissible upgrade note, and a local activate/remove flow.
 * Verification is OFFLINE (Ed25519 vs a baked-in public key); pasting a token
 * only writes a local `license.key` — nothing phones home. Removing it reverts
 * to Free and never bricks the app.
 */
export function LicensePanel() {
  const [status, setStatus] = useState<LicenseStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [token, setToken] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState<Msg | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [noteDismissed, setNoteDismissed] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async (signal?: AbortSignal) => {
    try {
      const next = await getLicense(signal);
      setStatus(next);
      setLoadError(null);
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      setLoadError("Couldn't read license status. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    void reload(ac.signal);
    return () => ac.abort();
  }, [reload]);

  async function handleActivate() {
    const value = token.trim();
    if (!value || submitting) return;
    setSubmitting(true);
    setMsg(null);
    try {
      await saveLicense(value);
      await reload();
      setToken('');
      setMsg({ kind: 'ok', text: 'License activated. Pro features available.' });
    } catch (err) {
      const text =
        err instanceof ApiError && err.status === 400
          ? "That token couldn't be verified. Check it and try again."
          : "Couldn't save the license. Try again.";
      setMsg({ kind: 'error', text });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove() {
    if (submitting) return;
    setSubmitting(true);
    setMsg(null);
    try {
      await removeLicense();
      await reload();
      setMsg({ kind: 'ok', text: 'License removed — reverted to Free.' });
    } catch {
      setMsg({ kind: 'error', text: "Couldn't remove the license. Try again." });
    } finally {
      setSubmitting(false);
    }
  }

  async function readFile(file: File) {
    try {
      const text = await file.text();
      setToken(text.trim());
      setMsg(null);
    } catch {
      setMsg({ kind: 'error', text: "Couldn't read that file." });
    }
  }

  const isPro = status?.tier === 'pro';

  return (
    <div className={css.card}>
      <div className={css.header}>
        <span className={css.glyph} aria-hidden="true">
          <KeyRound size={18} />
        </span>
        <div className={css.headerText}>
          <p className={css.subtitle}>
            Verified offline on this machine — your key never leaves the device.
          </p>
        </div>
      </div>

      {loading ? (
        <p className={css.loading}>Checking license…</p>
      ) : loadError ? (
        <p className={css.error} role="status">
          <TriangleAlert size={15} aria-hidden="true" />
          {loadError}
        </p>
      ) : status ? (
        <>
          <div className={css.statusRow}>
            <span className={css.statusLabel}>Status</span>
            <span className={`${css.statusValue}${isPro ? ` ${css.statusValuePro}` : ''}`}>
              {isPro && <BadgeCheck size={16} aria-hidden="true" />}
              {isPro ? status.detail : 'Free'}
            </span>
          </div>

          <ul className={css.featureList}>
            {FEATURES.map(({ key, label }) => {
              const on = status.features[key];
              return (
                <li key={key} className={css.featureRow}>
                  {on ? (
                    <Check size={15} className={css.featureIconOn} aria-hidden="true" />
                  ) : (
                    <Lock size={14} className={css.featureIconOff} aria-hidden="true" />
                  )}
                  <span className={css.featureName}>{label}</span>
                  <span className={css.featureState}>{on ? 'Included' : 'Pro'}</span>
                </li>
              );
            })}
          </ul>
          <p className={css.freeNote}>
            Core features and uncensored local search are always free — no content is ever gated.
          </p>

          {!isPro && !noteDismissed && (
            <div className={css.upgradeNote} role="note">
              <Lock size={14} className={css.upgradeIcon} aria-hidden="true" />
              <span className={css.upgradeText}>
                Pro unlocks bulk export, remote compute routing, and priority support — a one-time{' '}
                <span className={css.upgradePrice}>$29</span> purchase, perpetual for this major
                version.
              </span>
              <button
                type="button"
                className={css.dismiss}
                aria-label="Dismiss Pro note"
                onClick={() => setNoteDismissed(true)}
              >
                <X size={14} />
              </button>
            </div>
          )}

          <div className={css.field}>
            <label className={css.label} htmlFor="license-token">
              {isPro ? 'Replace license token' : 'Activate Pro'}
            </label>
            <textarea
              id="license-token"
              className={`${css.textarea}${dragOver ? ` ${css.dropActive}` : ''}`}
              placeholder="Paste your license token (MPL-…) or drop a license.key file"
              value={token}
              spellCheck={false}
              onChange={(e) => setToken(e.target.value)}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const file = e.dataTransfer.files?.[0];
                if (file) void readFile(file);
              }}
            />
            <p className={css.dropHint}>
              Saved locally to <code>license.key</code>. Nothing is sent anywhere.
            </p>
          </div>

          {msg && (
            <p className={msg.kind === 'ok' ? css.ok : css.error} role="status" aria-live="polite">
              {msg.kind === 'ok' ? (
                <Check size={15} aria-hidden="true" />
              ) : (
                <TriangleAlert size={15} aria-hidden="true" />
              )}
              {msg.text}
            </p>
          )}

          <div className={css.actions}>
            <input
              ref={fileRef}
              type="file"
              accept=".key,text/plain"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void readFile(file);
                e.target.value = '';
              }}
            />
            <button
              type="button"
              className={css.button}
              onClick={() => fileRef.current?.click()}
              disabled={submitting}
            >
              <Upload size={15} aria-hidden="true" />
              Choose file…
            </button>
            <span className={css.spacer} />
            {isPro && (
              <button
                type="button"
                className={`${css.button} ${css.buttonDanger}`}
                onClick={() => void handleRemove()}
                disabled={submitting}
              >
                <Trash2 size={15} aria-hidden="true" />
                Remove
              </button>
            )}
            <button
              type="button"
              className={`${css.button} ${css.buttonPrimary}`}
              onClick={() => void handleActivate()}
              disabled={submitting || !token.trim()}
            >
              {isPro ? 'Replace' : 'Activate'}
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
