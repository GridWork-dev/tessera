import { Check, ChevronLeft, ChevronRight, HelpCircle, ImageOff, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { mediaFull, mediaThumb } from '../api/client';
import type { ImageItem } from '../api/types';
import { useFlagImage } from '../hooks/queries';
import { useWorkspace } from '../store/useWorkspace';
import * as lb from './Lightbox.css';
import { RatingChip } from './RatingChip';

interface LightboxProps {
  /** The current grid page, in display order, for prev/next navigation. */
  images: ImageItem[];
}

const FLAG_ACTIONS: {
  action: 'keep' | 'maybe' | 'reject';
  label: string;
  icon: typeof Check;
}[] = [
  { action: 'keep', label: 'Keep', icon: Check },
  { action: 'maybe', label: 'Maybe', icon: HelpCircle },
  { action: 'reject', label: 'Reject', icon: X },
];

// Per-image load stage for the full → thumb → placeholder fallback chain.
type LoadStage = 'full' | 'thumb' | 'failed';

/**
 * Docked lightbox. Renders only when `store.lightboxId !== null`, as a fixed
 * full-region overlay. Navigates the ordered `images` list passed by Browse;
 * arrows / Left-Right keys move, Escape / close button / scrim click dismiss.
 */
export function Lightbox({ images }: LightboxProps) {
  const lightboxId = useWorkspace((s) => s.lightboxId);
  const openLightbox = useWorkspace((s) => s.openLightbox);
  const closeLightbox = useWorkspace((s) => s.closeLightbox);
  const flag = useFlagImage();

  const overlayRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const filmstripRef = useRef<HTMLDivElement>(null);
  // Reset the load fallback whenever the displayed image changes.
  const [stage, setStage] = useState<LoadStage>('full');

  const index = lightboxId === null ? -1 : images.findIndex((im) => im.id === lightboxId);
  const total = images.length;
  const current = index >= 0 ? images[index] : undefined;

  const goPrev = useCallback(() => {
    if (index > 0) {
      const prev = images[index - 1];
      if (prev) openLightbox(prev.id);
    }
  }, [index, images, openLightbox]);

  const goNext = useCallback(() => {
    if (index >= 0 && index < total - 1) {
      const next = images[index + 1];
      if (next) openLightbox(next.id);
    }
  }, [index, total, images, openLightbox]);

  // Reset the fallback chain on image change.
  // biome-ignore lint/correctness/useExhaustiveDependencies: lightboxId is the deliberate reset trigger
  useEffect(() => {
    setStage('full');
  }, [lightboxId]);

  // Keyboard: arrows navigate, Escape closes. Bound while open.
  useEffect(() => {
    if (lightboxId === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeLightbox();
      } else if (e.key === 'ArrowLeft' || e.key === 'j') {
        e.preventDefault();
        goPrev();
      } else if (e.key === 'ArrowRight' || e.key === 'k') {
        e.preventDefault();
        goNext();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [lightboxId, closeLightbox, goPrev, goNext]);

  // Move initial focus into the overlay so Escape/Tab are captured immediately.
  useEffect(() => {
    if (lightboxId !== null) closeRef.current?.focus();
  }, [lightboxId]);

  // Keep the active filmstrip thumb in view as we navigate.
  useEffect(() => {
    if (lightboxId === null) return;
    const strip = filmstripRef.current;
    if (!strip) return;
    const active = strip.querySelector<HTMLElement>('[data-active="true"]');
    active?.scrollIntoView({ inline: 'center', block: 'nearest' });
  }, [lightboxId]);

  // Make everything behind the overlay `inert` while the lightbox is open —
  // removing the command bar / grid / rail / inspector from the tab order AND
  // the accessibility tree. The manual Tab trap only intercepts Tab at the
  // edges; a screen-reader virtual cursor could otherwise still reach the
  // background. The overlay is a child of the app frame, so inert its siblings.
  useEffect(() => {
    if (lightboxId === null) return;
    const overlay = overlayRef.current;
    const parent = overlay?.parentElement;
    if (!parent) return;
    const siblings = Array.from(parent.children).filter(
      (el): el is HTMLElement => el instanceof HTMLElement && el !== overlay,
    );
    for (const el of siblings) el.setAttribute('inert', '');
    return () => {
      for (const el of siblings) el.removeAttribute('inert');
    };
  }, [lightboxId]);

  if (lightboxId === null || !current) return null;

  const hasPrev = index > 0;
  const hasNext = index < total - 1;

  const onImgError = () => {
    setStage((s) => (s === 'full' ? 'thumb' : 'failed'));
  };

  // Close only when the click originates on the scrim itself, not a child.
  const onOverlayMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) closeLightbox();
  };

  // Minimal focus trap: keep Tab cycling within the overlay.
  const onKeyDownTrap = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab') return;
    const root = overlayRef.current;
    if (!root) return;
    const focusables = root.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input, [tabindex]:not([tabindex="-1"])',
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (!first || !last) return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <div
      ref={overlayRef}
      className={lb.overlay}
      role="dialog"
      aria-modal="true"
      aria-label="Image viewer"
      onMouseDown={onOverlayMouseDown}
      onKeyDown={onKeyDownTrap}
    >
      <button
        ref={closeRef}
        type="button"
        className={lb.closeBtn}
        onClick={closeLightbox}
        aria-label="Close viewer"
        title="Close (Esc)"
      >
        <X size={18} aria-hidden="true" />
      </button>

      {/* Scrim region: clicking empty space dismisses. Keyboard users have Escape + the close button. */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: redundant scrim-dismiss convenience; keyboard paths exist (Esc / close button) */}
      <div className={lb.stage} onMouseDown={onOverlayMouseDown}>
        <button
          type="button"
          className={lb.navPrev}
          onClick={goPrev}
          disabled={!hasPrev}
          aria-label="Previous image"
          title="Previous (←)"
        >
          <ChevronLeft size={22} aria-hidden="true" />
        </button>

        <figure className={lb.figure}>
          {stage === 'failed' ? (
            <div className={lb.placeholder}>
              <ImageOff size={32} aria-hidden="true" />
              <span className={lb.placeholderHint}>Couldn't load preview</span>
            </div>
          ) : (
            <img
              key={`${current.id}-${stage}`}
              className={lb.image}
              src={stage === 'full' ? mediaFull(current.file_hash) : mediaThumb(current.file_hash)}
              alt=""
              draggable={false}
              onError={onImgError}
            />
          )}
        </figure>

        <button
          type="button"
          className={lb.navNext}
          onClick={goNext}
          disabled={!hasNext}
          aria-label="Next image"
          title="Next (→)"
        >
          <ChevronRight size={22} aria-hidden="true" />
        </button>
      </div>

      <div className={lb.strip}>
        <div className={lb.stripRow}>
          <div className={lb.stripMeta}>
            <RatingChip rating={current.rating} />
            {current.filename && (
              <span className={lb.filename} title={current.filename}>
                {current.filename}
              </span>
            )}
            <span className={lb.indexCount}>
              {index + 1} / {total}
            </span>
          </div>

          <div className={lb.stripSpacer} />

          {flag.isError && (
            <span className={lb.flagError} role="alert">
              Flag failed
            </span>
          )}

          <div className={lb.flagGroup}>
            {FLAG_ACTIONS.map(({ action, label, icon: Icon }) => {
              const active = current.flag_action === action;
              return (
                <button
                  key={action}
                  type="button"
                  className={`${lb.flagBtn}${active ? ` ${lb.flagBtnActive}` : ''}`}
                  onClick={() => flag.mutate({ id: current.id, action })}
                  disabled={flag.isPending}
                  aria-pressed={active}
                  title={`Flag: ${label}`}
                >
                  <Icon size={14} aria-hidden="true" />
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {total > 1 && (
          <div ref={filmstripRef} className={lb.filmstrip}>
            {images.map((im, i) => {
              const active = i === index;
              return (
                <button
                  key={im.id}
                  type="button"
                  data-active={active}
                  className={`${lb.thumb}${active ? ` ${lb.thumbActive}` : ''}`}
                  onClick={() => openLightbox(im.id)}
                  aria-label={`View image ${i + 1} of ${total}`}
                  aria-current={active ? 'true' : undefined}
                >
                  <img
                    className={lb.thumbImg}
                    src={mediaThumb(im.file_hash)}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    draggable={false}
                  />
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
