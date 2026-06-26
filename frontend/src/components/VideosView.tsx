import { ChevronDown, Film, Play, Volume2, VolumeX, X } from 'lucide-react';
import { type KeyboardEvent as ReactKeyboardEvent, useEffect, useRef, useState } from 'react';
import { type VideoSort, videoPoster, videoStream } from '../api/endpoints';
import type { VideoItem } from '../api/types';
import { useVideoDetail, useVideoFacets, useVideos } from '../hooks/queries';
import { labelsToParams } from '../lib/labelFilter';
import { RATINGS } from '../lib/rating';
import { selectHasFilters, useWorkspace } from '../store/useWorkspace';
import * as s from '../styles/workspace.css';
import { AppNav } from './AppNav';
import { RatingChip } from './RatingChip';
import { SceneDetail } from './SceneDetail';
import * as c from './VideosView.css';

const DURATION_ORDER = ['<30s', '30s-2m', '2m-10m', '10m+'];
const ORIENTATIONS = ['portrait', 'landscape', 'square'];

const VIDEO_SORTS: ReadonlyArray<{ value: VideoSort; label: string }> = [
  { value: 'recent', label: 'Recent' },
  { value: 'filename', label: 'Filename' },
  { value: 'size', label: 'File size' },
  { value: 'duration', label: 'Duration' },
  { value: 'random', label: 'Random' },
];

function fmtDuration(sec: number | null): string {
  if (sec == null) return '—';
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

export function VideosView() {
  // Shared filter model (Task F): person/rating/labels are SHARED with Browse,
  // so a filter set there persists when switching to Videos. Video-specific
  // facets (orientation/duration/audio/sort) live alongside in the same store.
  const person = useWorkspace((st) => st.person);
  const rating = useWorkspace((st) => st.rating);
  const labels = useWorkspace((st) => st.labels);
  const orientation = useWorkspace((st) => st.videoOrientation);
  const duration = useWorkspace((st) => st.videoDuration);
  const hasAudio = useWorkspace((st) => st.videoHasAudio);
  const sort = useWorkspace((st) => st.videoSort);
  const setPerson = useWorkspace((st) => st.setPerson);
  const setRating = useWorkspace((st) => st.setRating);
  const setOrientation = useWorkspace((st) => st.setVideoOrientation);
  const setDuration = useWorkspace((st) => st.setVideoDuration);
  const setHasAudio = useWorkspace((st) => st.setVideoHasAudio);
  const setSort = useWorkspace((st) => st.setVideoSort);
  const clearVideoFilters = useWorkspace((st) => st.clearVideoFilters);
  const hasActiveFilter = useWorkspace(selectHasFilters);

  const [playing, setPlaying] = useState<number | null>(null);

  const { data, isLoading, isError } = useVideos({
    orientation,
    duration,
    has_audio: hasAudio,
    person,
    rating,
    labels: labelsToParams(labels),
    sort,
  });
  const { data: facets } = useVideoFacets();
  const videos = data?.videos ?? [];

  const people = facets ? Object.entries(facets.people).sort((a, b) => b[1] - a[1]) : [];
  const ratings = facets ? RATINGS.filter((r) => (facets.ratings[r] ?? 0) > 0) : [];

  const clearFilters = clearVideoFilters;

  return (
    <div className={s.appFrame}>
      {/* Shared command bar — identical brand + nav as every other page. */}
      <header className={s.commandBar}>
        <AppNav />
        <span className={s.pageTitle}>Videos</span>
        <span className={s.barSpacer} />
        <div className={c.sortWrap}>
          <select
            className={c.sortSelect}
            value={sort}
            onChange={(e) => setSort(e.target.value as VideoSort)}
            aria-label="Sort order"
          >
            {VIDEO_SORTS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className={c.sortCaret} aria-hidden="true" />
        </div>
        <span className={s.pageMeta}>
          {isLoading ? 'loading…' : `${(data?.total ?? 0).toLocaleString()} videos`}
        </span>
      </header>

      {/* Same 2-zone layout + facet-rail vocabulary as Browse (no inspector). */}
      <div className={`${s.body} ${s.bodyNoInspector}`}>
        <aside className={s.rail} aria-label="Video filters">
          <div className={s.railHeader}>
            <span className={s.railHeaderTitle}>Filters</span>
            {hasActiveFilter && (
              <button type="button" className={s.clearBtn} onClick={clearFilters}>
                Clear
              </button>
            )}
          </div>

          {people.length > 0 && (
            <div className={s.section}>
              <span className={s.sectionLabel}>People</span>
              {people.map(([name, n]) => {
                const active = person === name;
                return (
                  <button
                    key={name}
                    type="button"
                    className={`${s.facetRow}${active ? ` ${s.facetRowActive}` : ''}`}
                    onClick={() => setPerson(name)}
                    aria-pressed={active}
                  >
                    <span className={s.facetName}>{name}</span>
                    <span className={s.facetCount}>{n}</span>
                  </button>
                );
              })}
            </div>
          )}

          {ratings.length > 0 && (
            <div className={s.section}>
              <span className={s.sectionLabel}>Rating</span>
              {ratings.map((r) => {
                const active = rating === r;
                return (
                  <button
                    key={r}
                    type="button"
                    className={`${s.facetRow}${active ? ` ${s.facetRowActive}` : ''}`}
                    onClick={() => setRating(r)}
                    aria-pressed={active}
                  >
                    <span className={s.facetName}>
                      <RatingChip rating={r} />
                    </span>
                    <span className={s.facetCount}>{facets?.ratings[r]}</span>
                  </button>
                );
              })}
            </div>
          )}

          <div className={s.section}>
            <span className={s.sectionLabel}>Duration</span>
            {DURATION_ORDER.map((d) => {
              const n = facets?.duration[d];
              if (n === undefined && data) return null;
              const active = duration === d;
              return (
                <button
                  key={d}
                  type="button"
                  className={`${s.facetRow}${active ? ` ${s.facetRowActive}` : ''}`}
                  onClick={() => setDuration(d)}
                  aria-pressed={active}
                >
                  <span className={s.facetName}>{d}</span>
                  {n !== undefined && <span className={s.facetCount}>{n}</span>}
                </button>
              );
            })}
          </div>

          <div className={s.section}>
            <span className={s.sectionLabel}>Orientation</span>
            {ORIENTATIONS.map((o) => {
              const n = facets?.orientation[o];
              if (n === undefined && data) return null;
              const active = orientation === o;
              return (
                <button
                  key={o}
                  type="button"
                  className={`${s.facetRow}${active ? ` ${s.facetRowActive}` : ''}`}
                  onClick={() => setOrientation(o)}
                  aria-pressed={active}
                >
                  <span className={s.facetName}>{o}</span>
                  {n !== undefined && <span className={s.facetCount}>{n}</span>}
                </button>
              );
            })}
          </div>

          <div className={s.section}>
            <span className={s.sectionLabel}>Audio</span>
            <button
              type="button"
              className={`${s.facetRow}${hasAudio === true ? ` ${s.facetRowActive}` : ''}`}
              onClick={() => setHasAudio(hasAudio === true ? null : true)}
              aria-pressed={hasAudio === true}
            >
              <span className={s.facetName}>Has audio</span>
              {facets && <span className={s.facetCount}>{facets.has_audio.yes}</span>}
            </button>
            <button
              type="button"
              className={`${s.facetRow}${hasAudio === false ? ` ${s.facetRowActive}` : ''}`}
              onClick={() => setHasAudio(hasAudio === false ? null : false)}
              aria-pressed={hasAudio === false}
            >
              <span className={s.facetName}>Silent</span>
              {facets && <span className={s.facetCount}>{facets.has_audio.no}</span>}
            </button>
          </div>
        </aside>

        <div className={s.gridRegion}>
          {isError ? (
            <div className={s.stateWrap}>
              <Film size={28} aria-hidden="true" />
              <span className={s.stateTitle}>Couldn't load videos</span>
              <span className={s.stateHint}>
                The backend may be offline. Start it with{' '}
                <code className={c.codeInline}>make backend</code> on :8000.
              </span>
            </div>
          ) : videos.length === 0 ? (
            <div className={s.stateWrap}>
              <Film size={28} aria-hidden="true" />
              <span className={s.stateTitle}>{isLoading ? 'Loading…' : 'No videos yet'}</span>
              <span className={s.stateHint}>
                Run the video ingest to import them — see{' '}
                <code className={c.codeInline}>scripts/ingest_videos.py</code>.
              </span>
            </div>
          ) : (
            <div className={c.gridPad}>
              <div className={c.grid}>
                {videos.map((v) => (
                  <VideoCard key={v.id} video={v} onPlay={() => setPlaying(v.id)} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {playing !== null && <VideoPlayerModal videoId={playing} onClose={() => setPlaying(null)} />}
    </div>
  );
}

function VideoCard({ video, onPlay }: { video: VideoItem; onPlay: () => void }) {
  return (
    <button type="button" className={c.card} onClick={onPlay}>
      {video.has_poster && video.file_hash ? (
        <img className={c.poster} src={videoPoster(video.file_hash)} alt="" loading="lazy" />
      ) : (
        <div className={c.posterEmpty}>
          <Play size={28} aria-hidden />
        </div>
      )}
      <span className={c.durationBadge}>{fmtDuration(video.duration)}</span>
      <span className={c.cardMeta}>
        <span className={c.cardName}>{video.filename ?? `#${video.id}`}</span>
        <span
          className={c.audioIcon}
          role="img"
          aria-label={video.has_audio ? 'Has audio' : 'Silent'}
        >
          {video.has_audio ? <Volume2 size={13} aria-hidden /> : <VolumeX size={13} aria-hidden />}
        </span>
      </span>
    </button>
  );
}

function VideoPlayerModal({ videoId, onClose }: { videoId: number; onClose: () => void }) {
  const { data: detail } = useVideoDetail(videoId);
  const ref = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const [deepOpen, setDeepOpen] = useState(false);

  // Keyboard: Esc closes; space toggles play; arrows seek 5s.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = ref.current;
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (!el) return;
      if (e.key === ' ') {
        e.preventDefault();
        if (el.paused) void el.play();
        else el.pause();
      } else if (e.key === 'ArrowRight') {
        el.currentTime = Math.min(el.duration || Infinity, el.currentTime + 5);
      } else if (e.key === 'ArrowLeft') {
        el.currentTime = Math.max(0, el.currentTime - 5);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Real modal semantics: move focus into the dialog on open, restore it to the
  // triggering card on close, and inert the rest of the app (the player overlay
  // is the last child of the app frame, so inert its siblings).
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    closeBtnRef.current?.focus();
    const overlay = overlayRef.current;
    const parent = overlay?.parentElement;
    const siblings = parent
      ? Array.from(parent.children).filter(
          (el): el is HTMLElement => el instanceof HTMLElement && el !== overlay,
        )
      : [];
    for (const el of siblings) el.setAttribute('inert', '');
    return () => {
      for (const el of siblings) el.removeAttribute('inert');
      trigger?.focus?.();
    };
  }, []);

  // Trap Tab inside the dialog so focus can't wander to the (inert) background.
  const onTrapKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab') return;
    const root = dialogRef.current;
    if (!root) return;
    const f = root.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input, video, [tabindex]:not([tabindex="-1"])',
    );
    if (f.length === 0) return;
    const first = f[0];
    const last = f[f.length - 1];
    if (!first || !last) return;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const seek = (t: number | null) => {
    if (ref.current && t != null) {
      ref.current.currentTime = t;
      void ref.current.play();
    }
  };

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: Escape (global handler) closes the modal; scrim click is a pointer-only convenience
    // biome-ignore lint/a11y/noStaticElementInteractions: scrim click-to-close is a standard modal affordance
    <div ref={overlayRef} className={c.overlay} onClick={onClose}>
      <div
        ref={dialogRef}
        className={c.playerDialog}
        role="dialog"
        aria-modal="true"
        aria-label={detail?.filename ?? 'Video player'}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onTrapKeyDown}
      >
        {detail?.file_hash && (
          // biome-ignore lint/a11y/useMediaCaption: local private library; no caption track exists
          <video
            ref={ref}
            className={c.video}
            src={videoStream(detail.file_hash)}
            controls
            autoPlay
          ></video>
        )}
        <div className={c.playerBar}>
          <div className={c.sceneChips}>
            {(detail?.scenes ?? []).map((sc) => (
              <button
                key={sc.scene_index ?? sc.start_time ?? 0}
                type="button"
                className={c.sceneChip}
                onClick={() => seek(sc.start_time)}
                title={`Scene ${(sc.scene_index ?? 0) + 1}`}
              >
                {fmtDuration(sc.start_time)}
              </button>
            ))}
          </div>
          <button type="button" className={c.closeBtn} onClick={() => setDeepOpen(true)}>
            Scenes
          </button>
          <button ref={closeBtnRef} type="button" className={c.closeBtn} onClick={onClose}>
            <X size={14} aria-hidden /> Close
          </button>
        </div>
        {deepOpen && <SceneDetail videoId={videoId} onClose={() => setDeepOpen(false)} />}
      </div>
    </div>
  );
}
