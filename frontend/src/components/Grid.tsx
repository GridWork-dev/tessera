import justifiedLayout from 'justified-layout';
import { Check, Flag, ImageOff } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { mediaThumb } from '../api/client';
import type { ImageItem } from '../api/types';
import { ratingColor, ratingLabel } from '../lib/rating';
import * as ws from '../styles/workspace.css';
import * as g from './Grid.css';

interface GridProps {
  images: ImageItem[];
  /** Single inspector target (accent ring). */
  selectedId: number | null;
  /** Bulk-triage selection set (accent ring + check badge). */
  selectedIds: Set<number>;
  density: 'comfortable' | 'compact';
  /** Plain click — sets the single inspector target. */
  onSelect: (id: number) => void;
  /** Enter / activation — open the lightbox for this id. */
  onActivate: (id: number) => void;
  /** cmd/ctrl/shift-click — toggle bulk selection (additive=true). */
  onToggleSelect: (id: number, additive: boolean) => void;
}

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const PADDING = 12;

// Density tunes target row height + spacing: compact packs more per row with a
// tighter gap; comfortable gives larger targets. justified-layout reflows to fit.
const DENSITY = {
  comfortable: { targetRowHeight: 208, boxSpacing: 8 },
  compact: { targetRowHeight: 150, boxSpacing: 6 },
} as const;

/** Direction unit for geometry-based arrow navigation. */
type Dir = 'left' | 'right' | 'up' | 'down';

/**
 * Pick the nearest box in `dir` from `fromIdx` using box centers. Primary axis
 * must move the right way; we minimize a weighted distance that favors staying
 * in the same row/column (so Up/Down don't drift sideways across a ragged grid).
 */
function nextIndexByGeometry(boxes: Box[], fromIdx: number, dir: Dir): number {
  const cur = boxes[fromIdx];
  if (!cur) return fromIdx;
  const cx = cur.left + cur.width / 2;
  const cy = cur.top + cur.height / 2;

  let best = -1;
  let bestScore = Number.POSITIVE_INFINITY;
  for (let i = 0; i < boxes.length; i++) {
    if (i === fromIdx) continue;
    const b = boxes[i];
    if (!b) continue;
    const bx = b.left + b.width / 2;
    const by = b.top + b.height / 2;
    const dx = bx - cx;
    const dy = by - cy;

    let primary: number;
    let cross: number;
    if (dir === 'left') {
      if (dx >= -1) continue;
      primary = -dx;
      cross = Math.abs(dy);
    } else if (dir === 'right') {
      if (dx <= 1) continue;
      primary = dx;
      cross = Math.abs(dy);
    } else if (dir === 'up') {
      if (dy >= -1) continue;
      primary = -dy;
      cross = Math.abs(dx);
    } else {
      if (dy <= 1) continue;
      primary = dy;
      cross = Math.abs(dx);
    }
    // Weight the cross-axis heavily so we prefer the visually-aligned neighbor.
    const score = primary + cross * 2.5;
    if (score < bestScore) {
      bestScore = score;
      best = i;
    }
  }
  return best === -1 ? fromIdx : best;
}

/**
 * Justified/masonry asset grid. Controlled — Browse owns selection + density and
 * passes them down. Roving tabindex: exactly one tile is tabbable, arrows move
 * focus by grid geometry. Plain click selects (inspector target); modifier-click
 * toggles bulk selection; Enter activates (lightbox).
 */
export function Grid({
  images,
  selectedId,
  selectedIds,
  density,
  onSelect,
  onActivate,
  onToggleSelect,
}: GridProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [focusIdx, setFocusIdx] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setWidth(entry.contentRect.width);
    });
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const sizes = useMemo(
    () => images.map((img) => ({ width: img.width ?? 3, height: img.height ?? 4 })),
    [images],
  );

  const layout = useMemo(() => {
    if (width <= 0) return null;
    const d = DENSITY[density];
    return justifiedLayout(sizes, {
      containerWidth: width,
      containerPadding: PADDING,
      boxSpacing: d.boxSpacing,
      targetRowHeight: d.targetRowHeight,
    });
  }, [sizes, width, density]);

  const boxes: Box[] = layout?.boxes ?? [];

  // Keep the roving-focus index valid as the result set changes (filter/page).
  useEffect(() => {
    setFocusIdx((i) => (images.length === 0 ? 0 : Math.min(i, images.length - 1)));
  }, [images.length]);

  // Mirror the selected (inspector) image into the roving index so keyboard nav
  // continues from wherever the user last clicked.
  useEffect(() => {
    if (selectedId === null) return;
    const idx = images.findIndex((im) => im.id === selectedId);
    if (idx >= 0) setFocusIdx(idx);
  }, [selectedId, images]);

  // Move focus to a tile by index and pull DOM focus to it (roving tabindex).
  const focusTile = useCallback((idx: number) => {
    setFocusIdx(idx);
    const el = ref.current?.querySelector<HTMLButtonElement>(`[data-tile-idx="${idx}"]`);
    el?.focus();
  }, []);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const count = images.length;
      if (count === 0) return;
      let next = focusIdx;
      switch (e.key) {
        case 'ArrowLeft':
          next = nextIndexByGeometry(boxes, focusIdx, 'left');
          break;
        case 'ArrowRight':
          next = nextIndexByGeometry(boxes, focusIdx, 'right');
          break;
        case 'ArrowUp':
          next = nextIndexByGeometry(boxes, focusIdx, 'up');
          break;
        case 'ArrowDown':
          next = nextIndexByGeometry(boxes, focusIdx, 'down');
          break;
        case 'Home':
          next = 0;
          break;
        case 'End':
          next = count - 1;
          break;
        case 'Enter':
        case ' ': {
          const img = images[focusIdx];
          if (img) {
            e.preventDefault();
            onActivate(img.id);
          }
          return;
        }
        default:
          return;
      }
      e.preventDefault();
      if (next !== focusIdx) focusTile(next);
    },
    [boxes, focusIdx, images, onActivate, focusTile],
  );

  const handleTileClick = useCallback(
    (e: React.MouseEvent, id: number, idx: number) => {
      setFocusIdx(idx);
      // cmd/ctrl-click or shift-click → bulk toggle; plain click → single select.
      if (e.metaKey || e.ctrlKey || e.shiftKey) {
        onToggleSelect(id, true);
      } else {
        onSelect(id);
      }
    },
    [onSelect, onToggleSelect],
  );

  return (
    <div
      ref={ref}
      className={`${ws.gridInner} ${g.listbox}`}
      style={{ height: layout ? `${layout.containerHeight}px` : undefined }}
      role="listbox"
      aria-label="Asset grid"
      aria-multiselectable="true"
      onKeyDown={onKeyDown}
    >
      {boxes.map((box, i) => {
        const img = images[i];
        if (!img) return null;
        const active = img.id === selectedId;
        const checked = selectedIds.has(img.id);
        return (
          <Tile
            key={img.id}
            img={img}
            box={box}
            index={i}
            active={active}
            checked={checked}
            roving={i === focusIdx}
            onClick={handleTileClick}
          />
        );
      })}
    </div>
  );
}

interface TileProps {
  img: ImageItem;
  box: Box;
  index: number;
  active: boolean;
  checked: boolean;
  /** True for the single tile that currently holds tabindex=0 (roving). */
  roving: boolean;
  onClick: (e: React.MouseEvent, id: number, idx: number) => void;
}

function Tile({ img, box, index, active, checked, roving, onClick }: TileProps) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);

  // Cached thumbs can finish loading before React binds onLoad — reconcile from
  // img.complete so the fade-in (and skeleton teardown) never gets stuck.
  useEffect(() => {
    const el = imgRef.current;
    if (!el) return;
    if (el.complete) {
      if (el.naturalWidth === 0) setErrored(true);
      else setLoaded(true);
    }
  }, []);

  const showRating = img.rating && img.rating !== 'unrated';
  const cls = [g.tile, active ? g.tileActive : '', checked ? g.tileChecked : '']
    .filter(Boolean)
    .join(' ');

  return (
    <button
      type="button"
      data-tile-idx={index}
      className={cls}
      style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
      // Roving tabindex: exactly one tile is tabbable; arrows move focus.
      tabIndex={roving ? 0 : -1}
      role="option"
      aria-selected={checked || active}
      aria-label={`${img.filename}${showRating ? `, ${ratingLabel(img.rating)}` : ''}`}
      onClick={(e) => onClick(e, img.id, index)}
    >
      <span className={g.imgWrap}>
        {!loaded && !errored && <span className={g.skeleton} aria-hidden="true" />}
        {errored ? (
          <span className={g.broken}>
            <ImageOff size={22} aria-hidden="true" />
          </span>
        ) : (
          <img
            ref={imgRef}
            className={`${g.img}${loaded ? ` ${g.imgLoaded}` : ''}`}
            src={mediaThumb(img.file_hash)}
            alt=""
            loading="lazy"
            decoding="async"
            draggable={false}
            onLoad={() => setLoaded(true)}
            onError={() => setErrored(true)}
          />
        )}
      </span>

      {showRating && (
        <span className={g.ratingBadge} style={{ color: ratingColor(img.rating) }}>
          <span className={g.ratingDot} style={{ backgroundColor: ratingColor(img.rating) }} />
          {ratingLabel(img.rating)}
        </span>
      )}

      {img.flagged && (
        <span className={g.flagBadge} role="img" aria-label="Flagged">
          <Flag size={11} aria-hidden="true" />
        </span>
      )}

      {checked && (
        <span className={g.checkBadge} role="img" aria-label="Selected">
          <Check size={12} aria-hidden="true" />
        </span>
      )}
    </button>
  );
}
