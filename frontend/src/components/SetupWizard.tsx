import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { Cpu, FolderOpen, Lock, PackageOpen } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import {
  type ComputeBackend,
  getComputeDetect,
  getWeightsPlan,
  pullWeights,
  setBindAuth,
  setCompute,
  setLibrary,
} from '../api/setup';
import { BrandFacet } from './BrandFacet';
import * as css from './SetupWizard.css';

/**
 * First-run setup wizard (Spec F / §7 P0.4). Walks a NEW user through four
 * steps, each backed by a /api/setup endpoint:
 *
 *   1. Library  — choose the library/content dir (settings layer write).
 *   2. Weights  — size preview (plan) + pull, with the NudeNet AGPL opt-in.
 *   3. Compute  — show the auto-detected backend; allow an override.
 *   4. Bind+Auth — bind host/port + optionally create the first admin.
 *
 * Mounted by the /setup route. On finish, navigates home. The backend's
 * apply-gate means a pull/seed is inert until the operator sets
 * MEDIA_PIPELINE_SETUP_APPLY (so this surface is safe to click through in dev).
 */

const STEPS = [
  { key: 'library', label: 'Library', icon: FolderOpen },
  { key: 'weights', label: 'Models', icon: PackageOpen },
  { key: 'compute', label: 'Compute', icon: Cpu },
  { key: 'auth', label: 'Access', icon: Lock },
] as const;

const BACKEND_LABEL: Record<ComputeBackend, string> = {
  local_mps: 'Apple Silicon (CoreML / MLX)',
  local_cuda: 'NVIDIA (CUDA / TensorRT)',
  local_directml: 'Windows GPU (DirectML)',
  local_cpu: 'CPU only (slow)',
};

function fmtSize(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}

export function SetupWizard() {
  const navigate = useNavigate();
  const [stepIdx, setStepIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Step state
  const [libraryRoot, setLibraryRoot] = useState('');
  const [includeNudenet, setIncludeNudenet] = useState(false);
  const [pullStatus, setPullStatus] = useState<string | null>(null);
  const [backend, setBackend] = useState<ComputeBackend | null>(null);
  const [bindHost, setBindHost] = useState('127.0.0.1');
  const [bindPort, setBindPort] = useState(8000);
  const [enableAuth, setEnableAuth] = useState(false);
  const [adminUser, setAdminUser] = useState('admin');
  const [adminPw, setAdminPw] = useState('');

  const stepKey = (STEPS[stepIdx] ?? STEPS[0]).key;

  // a11y: move focus to the active step heading on advance so AT users are
  // landed on the new step's title rather than left on the (now-changed) button.
  const headingRef = useRef<HTMLHeadingElement>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: focus only on step change.
  useEffect(() => {
    headingRef.current?.focus();
  }, [stepIdx]);

  const planQuery = useQuery({
    queryKey: ['setup-weights-plan', includeNudenet],
    queryFn: ({ signal }) => getWeightsPlan({ includeNudenet }, signal),
    enabled: stepKey === 'weights',
  });

  const computeQuery = useQuery({
    queryKey: ['setup-compute-detect'],
    queryFn: ({ signal }) => getComputeDetect(signal),
    enabled: stepKey === 'compute',
  });

  const detected = computeQuery.data?.detected_backend ?? null;
  const isLoopback = ['127.0.0.1', '::1', 'localhost'].includes(bindHost.trim());

  async function advance() {
    setErr(null);
    setBusy(true);
    try {
      if (stepKey === 'library') {
        await setLibrary({ library_root: libraryRoot.trim() });
      } else if (stepKey === 'weights') {
        const res = await pullWeights({ include_nudenet: includeNudenet });
        setPullStatus(
          res.applied
            ? 'Download started.'
            : 'Preview only — set MEDIA_PIPELINE_SETUP_APPLY to download.',
        );
      } else if (stepKey === 'compute') {
        await setCompute({ backend: backend ?? detected });
      } else if (stepKey === 'auth') {
        await setBindAuth({
          bind_host: bindHost.trim(),
          bind_port: bindPort,
          enable_auth: enableAuth,
          admin_username: adminUser.trim() || 'admin',
          // Omit the password entirely (not `undefined`) when auth is off, to
          // satisfy exactOptionalPropertyTypes.
          ...(enableAuth ? { admin_password: adminPw } : {}),
        });
        navigate({ to: '/' });
        return;
      }
      setStepIdx((i) => Math.min(i + 1, STEPS.length - 1));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Setup step failed.');
    } finally {
      setBusy(false);
    }
  }

  const canAdvance = (() => {
    if (busy) return false;
    if (stepKey === 'library') return libraryRoot.trim().length > 0;
    if (stepKey === 'auth') {
      if (!isLoopback && !enableAuth) return false; // §6: open bind needs auth
      if (enableAuth && adminPw.trim().length === 0) return false;
      return true;
    }
    return true;
  })();

  return (
    <div className={css.screen}>
      <div className={css.card}>
        <div className={css.header}>
          <div className={css.brand}>
            <span className={css.brandGlyph} aria-hidden="true">
              <BrandFacet size={16} />
            </span>
            Tessera — Setup
          </div>
          <p className={css.subtitle}>
            Tessera is a local-first manager for your library — tagging, search, and curation. A few
            one-time choices to set it up; your files never leave this machine.
          </p>
        </div>

        <ol
          className={css.rail}
          aria-label={`Setup progress — step ${stepIdx + 1} of ${STEPS.length}`}
        >
          {STEPS.map((s, i) => (
            <li
              className={css.railStep}
              key={s.key}
              aria-current={i === stepIdx ? 'step' : undefined}
            >
              <div
                className={`${css.railBar} ${
                  i === stepIdx ? css.railBarActive : i < stepIdx ? css.railBarDone : ''
                }`}
              />
              <span className={`${css.railLabel} ${i === stepIdx ? css.railLabelActive : ''}`}>
                {s.label}
              </span>
            </li>
          ))}
        </ol>

        <div className={css.step}>
          <p className={css.stepCount}>
            Step {stepIdx + 1} of {STEPS.length}
          </p>

          {stepKey === 'library' && (
            <>
              <h2 className={css.stepTitle} ref={headingRef} tabIndex={-1}>
                Where is your library?
              </h2>
              <p className={css.stepHint}>
                The folder that holds your library. Image paths are stored relative to it, so you
                can move it later.
              </p>
              <div className={css.field}>
                <label className={css.label} htmlFor="library-root">
                  Library folder
                </label>
                <input
                  id="library-root"
                  className={css.input}
                  value={libraryRoot}
                  onChange={(e) => setLibraryRoot(e.target.value)}
                  placeholder="/path/to/your/library"
                  spellCheck={false}
                  autoComplete="off"
                />
              </div>
            </>
          )}

          {stepKey === 'weights' && (
            <>
              <h2 className={css.stepTitle} ref={headingRef} tabIndex={-1}>
                Model weights
              </h2>
              <p className={css.stepHint}>
                These power tagging, search, and captions. They're pulled from Hugging Face on first
                run, not bundled — here's what would download:
              </p>
              {planQuery.isLoading && <p className={css.note}>Estimating sizes…</p>}
              {planQuery.isError && (
                <p className={css.error}>
                  Couldn't estimate model sizes.{' '}
                  {planQuery.error instanceof Error ? planQuery.error.message : ''}
                </p>
              )}
              {planQuery.data && (
                <>
                  <div className={css.previewList}>
                    {planQuery.data.to_pull.map((row) => (
                      <div className={css.previewRow} key={row.key}>
                        <span>{row.title}</span>
                        <span className={css.previewSize}>{fmtSize(row.approx_size_mb)}</span>
                      </div>
                    ))}
                  </div>
                  <div className={css.totalRow}>
                    <span>Total to download</span>
                    <span className={css.totalValue}>
                      {fmtSize(planQuery.data.approx_total_mb)}
                    </span>
                    <span>· {planQuery.data.count} models</span>
                  </div>
                </>
              )}
              <label className={css.checkRow}>
                <input
                  type="checkbox"
                  className={css.checkBox}
                  checked={includeNudenet}
                  onChange={(e) => {
                    setIncludeNudenet(e.target.checked);
                    // The plan re-fetches for the new selection; drop the now-stale
                    // "Preview only…" / "Download started." note from the prior plan.
                    setPullStatus(null);
                  }}
                />
                <span>
                  Include NudeNet region detection
                  <span className={css.checkNote}>
                    AGPL-3.0 · optional · region metadata only, never a content gate.
                  </span>
                </span>
              </label>
              {pullStatus && <p className={css.note}>{pullStatus}</p>}
            </>
          )}

          {stepKey === 'compute' && (
            <>
              <h2 className={css.stepTitle} ref={headingRef} tabIndex={-1}>
                Compute backend
              </h2>
              <p className={css.stepHint}>
                This decides how tagging and search run. We picked the best option for this machine
                — change it if you prefer.
              </p>
              {computeQuery.isLoading && <p className={css.note}>Detecting hardware…</p>}
              {computeQuery.isError && (
                <p className={css.error}>
                  Couldn't detect compute hardware.{' '}
                  {computeQuery.error instanceof Error ? computeQuery.error.message : ''}
                </p>
              )}
              {computeQuery.data && (
                <div className={css.options}>
                  {computeQuery.data.choices.map((b) => {
                    const selected = (backend ?? detected) === b;
                    return (
                      <button
                        type="button"
                        key={b}
                        className={`${css.option} ${selected ? css.optionActive : ''}`}
                        onClick={() => setBackend(b)}
                        aria-pressed={selected}
                      >
                        {BACKEND_LABEL[b]}
                        {b === detected && <span className={css.badge}>Detected</span>}
                        <span className={css.optionMeta}>{b}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {stepKey === 'auth' && (
            <>
              <h2 className={css.stepTitle} ref={headingRef} tabIndex={-1}>
                Access &amp; binding
              </h2>
              <p className={css.stepHint}>
                Loopback is private to this machine. Exposing it on your network requires a login.
                Bind host and port changes take effect after the server restarts.
              </p>
              <div className={css.field}>
                <label className={css.label} htmlFor="bind-host">
                  Bind host
                </label>
                <input
                  id="bind-host"
                  className={css.input}
                  value={bindHost}
                  onChange={(e) => setBindHost(e.target.value)}
                  spellCheck={false}
                  autoComplete="off"
                />
              </div>
              <div className={css.field}>
                <label className={css.label} htmlFor="bind-port">
                  Port
                </label>
                <input
                  id="bind-port"
                  className={css.input}
                  type="number"
                  value={bindPort}
                  min={1}
                  max={65535}
                  onChange={(e) => setBindPort(Number(e.target.value) || 8000)}
                />
              </div>
              <label className={css.checkRow}>
                <input
                  type="checkbox"
                  className={css.checkBox}
                  checked={enableAuth}
                  onChange={(e) => setEnableAuth(e.target.checked)}
                />
                <span>
                  Require a login (create the first admin)
                  {!isLoopback && (
                    <span className={css.checkNote}>Required for a non-loopback bind.</span>
                  )}
                </span>
              </label>
              {enableAuth && (
                <>
                  <div className={css.field}>
                    <label className={css.label} htmlFor="admin-user">
                      Admin username
                    </label>
                    <input
                      id="admin-user"
                      className={css.input}
                      value={adminUser}
                      onChange={(e) => setAdminUser(e.target.value)}
                      spellCheck={false}
                      autoComplete="username"
                    />
                  </div>
                  <div className={css.field}>
                    <label className={css.label} htmlFor="admin-pw">
                      Admin password
                    </label>
                    <input
                      id="admin-pw"
                      className={css.input}
                      type="password"
                      value={adminPw}
                      onChange={(e) => setAdminPw(e.target.value)}
                      autoComplete="new-password"
                    />
                  </div>
                </>
              )}
            </>
          )}

          {err && <p className={css.error}>{err}</p>}
        </div>

        <div className={css.footer}>
          <button
            type="button"
            className={css.button}
            disabled={stepIdx === 0 || busy}
            onClick={() => {
              setErr(null);
              setStepIdx((i) => Math.max(i - 1, 0));
            }}
          >
            Back
          </button>
          <span className={css.footerSpacer} />
          <button
            type="button"
            className={`${css.button} ${css.buttonPrimary}`}
            disabled={!canAdvance}
            onClick={advance}
          >
            {stepKey === 'auth' ? 'Finish' : 'Continue'}
          </button>
        </div>
      </div>
    </div>
  );
}
