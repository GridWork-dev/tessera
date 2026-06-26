import { Link } from '@tanstack/react-router';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ImageOff,
  LoaderCircle,
  LogOut,
  PartyPopper,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { mediaFull, mediaThumb } from '../api/client';
import { addLabel, deleteLabel, getLabels } from '../api/endpoints';
import type { ImageItem } from '../api/types';
import { useFlagImage, useImages } from '../hooks/queries';
import { ratingColor, ratingLabel } from '../lib/rating';
import { useWorkspace } from '../store/useWorkspace';
import * as s from './TrainingMode.css';

const PAGE_SIZE = 100;

type FlagAction = 'keep' | 'reject';
type QueueSource = 'untagged' | 'unrated';

// Binary training signal: keep (advance) / reject (stay → tag reasons). "maybe"
// and the rating action were removed — triage is now pure keep/reject training
// that feeds the preference recommender + exclude/hide suggestions.
const FLAG_VERBS: {
  action: FlagAction;
  label: string;
  hint: string;
  icon: typeof Check;
  color: string;
}[] = [
  { action: 'keep', label: 'Keep', hint: 'k', icon: Check, color: ratingColor('sfw') },
  { action: 'reject', label: 'Reject', hint: 'r', icon: X, color: ratingColor('nsfw') },
];

// Structured rejection reasons (number keys 1..N while a reject is active). These
// persist as user_labels(category='reject_reason') and feed the exclude/hide
// suggestions — the structured "what I didn't like" signal.
const REJECT_REASONS = ['blurry', 'wrong person', 'duplicate', 'off-vibe', 'bad crop', 'other'];

interface Flash {
  /** Monotonic token so identical consecutive actions still retrigger the flash. */
  token: number;
  label: string;
  color: string;
  icon: typeof Check;
}

export function TrainingMode() {
  const flag = useFlagImage();
  const setTrainingMode = useWorkspace((st) => st.setTrainingMode);

  const [source, setSource] = useState<QueueSource>('untagged');
  const [cursor, setCursor] = useState(0);
  const [flash, setFlash] = useState<Flash | null>(null);
  const flashTokenRef = useRef(0);
  // Hashes whose full-res failed -> fall back to the thumbnail.
  const [fallbacks, setFallbacks] = useState<ReadonlySet<string>>(() => new Set());
  // Per-image chosen reject reasons: image_id -> { reasonValue: labelId }.
  // Presence of a key = selected; labelId is the user_labels row id (-1 while the
  // optimistic create is in flight).
  const [reasonMap, setReasonMap] = useState<Record<number, Record<string, number>>>({});

  // Mark training mode active for the route lifetime so other surfaces can
  // reflect it; reset on unmount.
  useEffect(() => {
    setTrainingMode(true);
    return () => setTrainingMode(false);
  }, [setTrainingMode]);

  const filter = useMemo(
    () =>
      source === 'untagged'
        ? { processed: false, sort: 'recent' as const, page: 1, limit: PAGE_SIZE }
        : { rating: 'unrated', sort: 'recent' as const, page: 1, limit: PAGE_SIZE },
    [source],
  );

  const { data, isLoading, isError } = useImages(filter);
  const queue = useMemo<ImageItem[]>(() => data?.images ?? [], [data]);
  const total = data?.total ?? 0;

  // Clamp the cursor whenever the queue length changes (refetch / page churn).
  useEffect(() => {
    setCursor((c) => (queue.length === 0 ? 0 : Math.min(c, queue.length - 1)));
  }, [queue.length]);

  // Reset to the head of the queue when switching source.
  // biome-ignore lint/correctness/useExhaustiveDependencies: source change is the deliberate reset trigger
  useEffect(() => {
    setCursor(0);
  }, [source]);

  const current: ImageItem | undefined = queue[cursor];
  const atFirst = cursor <= 0;
  const atLast = cursor >= queue.length - 1;
  const rejected = current?.flag_action === 'reject';

  const showFlash = useCallback((label: string, color: string, icon: typeof Check) => {
    flashTokenRef.current += 1;
    setFlash({ token: flashTokenRef.current, label, color, icon });
  }, []);

  const advance = useCallback(() => {
    setCursor((c) => Math.min(c + 1, Math.max(queue.length - 1, 0)));
  }, [queue.length]);

  const back = useCallback(() => {
    setCursor((c) => Math.max(c - 1, 0));
  }, []);

  const doFlag = useCallback(
    (action: FlagAction, thenAdvance: boolean) => {
      if (!current) return;
      flag.mutate({ id: current.id, action });
      const verb = FLAG_VERBS.find((v) => v.action === action);
      if (verb) showFlash(verb.label, verb.color, verb.icon);
      if (thenAdvance) advance();
    },
    [current, flag, showFlash, advance],
  );

  // Hydrate chosen reasons from the server the first time a rejected item is shown.
  useEffect(() => {
    const c = current;
    if (!c) return;
    if (c.flag_action !== 'reject' || reasonMap[c.id]) return;
    let alive = true;
    getLabels(c.id)
      .then((res) => {
        if (!alive) return;
        const entries = (res.labels ?? [])
          .filter((l) => l.category === 'reject_reason')
          .map((l) => [l.value, l.id] as const);
        setReasonMap((prev) =>
          prev[c.id] ? prev : { ...prev, [c.id]: Object.fromEntries(entries) },
        );
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [current, reasonMap]);

  const toggleReason = useCallback(
    (value: string) => {
      const c = current;
      if (!c) return;
      setReasonMap((prev) => {
        const cur = { ...(prev[c.id] ?? {}) };
        if (value in cur) {
          const labelId = cur[value];
          delete cur[value];
          if (labelId !== undefined && labelId > 0) void deleteLabel(c.id, labelId).catch(() => {});
        } else {
          cur[value] = -1; // optimistic; real id filled in on resolve
          void addLabel(c.id, value, 'reject_reason')
            .then((l) =>
              setReasonMap((p) => {
                const m = { ...(p[c.id] ?? {}) };
                if (value in m) m[value] = l.id;
                return { ...p, [c.id]: m };
              }),
            )
            .catch(() =>
              setReasonMap((p) => {
                const m = { ...(p[c.id] ?? {}) };
                delete m[value];
                return { ...p, [c.id]: m };
              }),
            );
        }
        return { ...prev, [c.id]: cur };
      });
    },
    [current],
  );

  // ---- Keyboard: the point of this mode. Ignore when typing in a field. ----
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el?.tagName === 'INPUT' || el?.tagName === 'TEXTAREA' || el?.isContentEditable) {
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      switch (e.key) {
        case 'k':
        case 'K':
        case 'Enter':
          e.preventDefault();
          doFlag('keep', true);
          break;
        case 'r':
        case 'R':
        case 'x':
        case 'X':
          e.preventDefault();
          doFlag('reject', false); // stay so the operator can tag reasons
          break;
        case 'ArrowRight':
        case ' ':
        case 'Spacebar':
          e.preventDefault();
          advance();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          back();
          break;
        default: {
          // Number keys 1..N toggle reject reasons — only while a reject is active.
          if (rejected && /^[1-9]$/.test(e.key)) {
            const reason = REJECT_REASONS[Number(e.key) - 1];
            if (reason) {
              e.preventDefault();
              toggleReason(reason);
            }
          }
          break;
        }
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [doFlag, advance, back, rejected, toggleReason]);

  const pct = queue.length === 0 ? 0 : (cursor + 1) / queue.length;
  const queueLabel = source === 'untagged' ? 'untagged backlog' : 'unrated backlog';
  const useFallback = current ? fallbacks.has(current.file_hash) : false;
  const chosen = current ? (reasonMap[current.id] ?? {}) : {};

  return (
    <div className={s.root}>
      {/* ---- Top bar ---- */}
      <header className={s.topBar}>
        <Link to="/" className={s.exitLink}>
          <LogOut size={15} aria-hidden="true" />
          Exit
        </Link>
        <div>
          <div className={s.title}>Training &amp; triage</div>
          <div className={s.subtitle}>Keep or reject the {queueLabel}</div>
        </div>

        <span className={s.spacer} />

        {/* biome-ignore lint/a11y/useSemanticElements: a toolbar button group; role=group is the correct ARIA, not a fieldset */}
        <div className={s.segGroup} role="group" aria-label="Queue source">
          <button
            type="button"
            className={`${s.segBtn}${source === 'untagged' ? ` ${s.segBtnActive}` : ''}`}
            aria-pressed={source === 'untagged'}
            onClick={() => setSource('untagged')}
          >
            Untagged
          </button>
          <button
            type="button"
            className={`${s.segBtn}${source === 'unrated' ? ` ${s.segBtnActive}` : ''}`}
            aria-pressed={source === 'unrated'}
            onClick={() => setSource('unrated')}
          >
            Unrated
          </button>
        </div>

        <span className={s.progress} aria-live="polite">
          <span className={s.progressNum}>{queue.length === 0 ? 0 : cursor + 1}</span>
          <span>/</span>
          <span>{queue.length}</span>
          {total > queue.length && (
            <span className={s.progressTotal}>({total.toLocaleString()} total)</span>
          )}
        </span>
      </header>

      {/* ---- Stage ---- */}
      <main className={s.stage}>
        <div className={s.railTrack} aria-hidden="true">
          <div className={s.railFill} style={{ transform: `scaleX(${pct})` }} />
        </div>

        {isError ? (
          <div className={s.stateWrap}>
            <ImageOff size={30} aria-hidden="true" />
            <span className={s.stateTitle}>Couldn't load the queue</span>
            <span className={s.stateHint}>
              The backend may be offline. Start it with <code>make backend</code> on :8000, then
              reopen this view.
            </span>
          </div>
        ) : isLoading && queue.length === 0 ? (
          <div className={s.stateWrap}>
            <LoaderCircle size={30} aria-hidden="true" />
            <span className={s.stateTitle}>Loading queue…</span>
          </div>
        ) : queue.length === 0 ? (
          <div className={s.stateWrap}>
            <PartyPopper size={30} aria-hidden="true" />
            <span className={s.stateTitle}>Queue clear</span>
            <span className={s.stateHint}>
              Nothing left in the {queueLabel}. Switch the source above, or return to Browse.
            </span>
          </div>
        ) : current ? (
          <div className={s.imageWrap}>
            <img
              key={current.file_hash}
              className={s.image}
              src={useFallback ? mediaThumb(current.file_hash) : mediaFull(current.file_hash)}
              alt={current.filename}
              draggable={false}
              decoding="async"
              onError={() => {
                setFallbacks((prev) => {
                  if (prev.has(current.file_hash)) return prev;
                  const next = new Set(prev);
                  next.add(current.file_hash);
                  return next;
                });
              }}
            />
            {flash && (
              <div
                key={flash.token}
                className={s.actionFlash}
                style={{ borderColor: flash.color, color: flash.color }}
              >
                <flash.icon size={16} aria-hidden="true" />
                {flash.label}
              </div>
            )}

            {/* Reason chips — only after a reject; optional, advance any time. */}
            {rejected && (
              // biome-ignore lint/a11y/useSemanticElements: a chip toolbar group; role=group is the correct ARIA, not a fieldset
              <div className={s.reasonRow} role="group" aria-label="Reject reasons">
                <span className={s.reasonLabel}>Why?</span>
                {REJECT_REASONS.map((reason, i) => {
                  const on = reason in chosen;
                  return (
                    <button
                      key={reason}
                      type="button"
                      className={`${s.reasonChip}${on ? ` ${s.reasonChipActive}` : ''}`}
                      onClick={() => toggleReason(reason)}
                      aria-pressed={on}
                    >
                      {reason}
                      <span className={s.kbd}>{i + 1}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}

        {/* Quiet metadata sidecar */}
        {current && (
          <aside className={s.sidecar} aria-label="Current asset details">
            <div className={s.sidecarRow}>
              <span className={s.groupLabel}>Rating</span>
              <span className={s.metaVal} style={{ color: ratingColor(current.rating) }}>
                {ratingLabel(current.rating)}
              </span>
            </div>

            <div className={s.sidecarRow}>
              <span className={s.groupLabel}>Details</span>
              <div className={s.metaGrid}>
                <span className={s.metaKey}>Person</span>
                <span className={s.metaVal}>{current.person?.replace(/_/g, ' ') ?? '—'}</span>
                <span className={s.metaKey}>Size</span>
                <span className={s.metaNum}>
                  {current.width && current.height ? `${current.width}×${current.height}` : '—'}
                </span>
                <span className={s.metaKey}>State</span>
                <span className={s.metaVal}>{current.processed ? 'tagged' : 'untagged'}</span>
                <span className={s.metaKey}>Flag</span>
                <span className={s.metaVal}>{current.flag_action ?? '—'}</span>
              </div>
            </div>

            <div className={s.sidecarRow}>
              <span className={s.groupLabel}>
                Tags{current.tags.length > 0 ? ` (${current.tags.length})` : ''}
              </span>
              {current.tags.length > 0 ? (
                <div className={s.tagWrap}>
                  {current.tags
                    .filter((tg) => tg.category !== 'rating')
                    .slice(0, 18)
                    .map((tg) => (
                      <span key={`${tg.category}:${tg.value}`} className={s.tag}>
                        {tg.value}
                      </span>
                    ))}
                </div>
              ) : (
                <span className={s.muted}>No tags yet — runs after the Tier 0 tag pass.</span>
              )}
            </div>

            {flag.isError && (
              <span className={s.errorText}>
                Couldn't save the last action — it was rolled back. Retry the key.
              </span>
            )}
          </aside>
        )}
      </main>

      {/* ---- Action bar / hotkey legend ---- */}
      <footer className={s.actionBar}>
        <button
          type="button"
          className={s.navBtn}
          onClick={back}
          disabled={atFirst}
          aria-label="Previous (Left arrow)"
        >
          <ArrowLeft size={15} aria-hidden="true" />
          <span className={s.kbd}>←</span>
        </button>

        <div className={s.verbGroup}>
          {FLAG_VERBS.map(({ action, label, hint, icon: Icon }) => (
            <button
              key={action}
              type="button"
              className={`${s.verbBtn}${current?.flag_action === action ? ` ${s.verbBtnActive}` : ''}`}
              onClick={() => doFlag(action, action === 'keep')}
              disabled={!current}
            >
              <Icon size={16} aria-hidden="true" />
              {label}
              <span className={s.kbd}>{hint}</span>
            </button>
          ))}
        </div>

        <span className={s.divider} aria-hidden="true" />

        <button
          type="button"
          className={s.navBtn}
          onClick={advance}
          disabled={!current || atLast}
          aria-label="Next (Right arrow or Space)"
        >
          <span className={s.kbd}>→</span>
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      </footer>
    </div>
  );
}
