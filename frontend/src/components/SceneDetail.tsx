import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Captions, Film, Hash, RefreshCw, Tags, Users, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ApiError } from '../api/client';
import {
  getSceneDetail,
  getVideoScenes,
  type SceneListItem,
  triggerVideoBackfill,
} from '../api/videoDeep';
import * as ws from '../styles/workspace.css';
import * as c from './SceneDetail.css';

/** Local, lane-scoped query keys (kept out of the shared hooks/queries.ts). */
const sceneKeys = {
  videoScenes: (videoId: number) => ['videoDeep', 'scenes', videoId] as const,
  sceneDetail: (sceneId: number) => ['videoDeep', 'scene', sceneId] as const,
};

function fmtTime(sec: number | null): string {
  if (sec == null) return '—';
  const s = Math.round(sec);
  const m = Math.floor(s / 60);
  const ss = String(s % 60).padStart(2, '0');
  return `${m}:${ss}`;
}

export interface SceneDetailProps {
  videoId: number;
  /** Optional scene to pre-select (e.g. the chip the user clicked). */
  initialSceneId?: number | null;
  onClose: () => void;
}

/**
 * Deep-scene drawer for one video. Lists its scenes with enrichment-status flags
 * (tagged / captioned / transcribed / faces); selecting one reveals tags,
 * caption, ordered transcript segments and the detected-face count. The footer
 * triggers a per-video Re-enrich (background backfill).
 *
 * Renders cleanly empty: a video with no scenes yet shows an "unenriched" state,
 * and the Re-enrich action is the path to populate it.
 */
export function SceneDetail({ videoId, initialSceneId = null, onClose }: SceneDetailProps) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number | null>(initialSceneId);

  // Esc closes the drawer (matches the player modal's keyboard convention).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const scenesQuery = useQuery({
    queryKey: sceneKeys.videoScenes(videoId),
    queryFn: ({ signal }) => getVideoScenes(videoId, signal),
    staleTime: 30_000,
    retry: false,
  });

  const detailQuery = useQuery({
    queryKey: sceneKeys.sceneDetail(selected ?? -1),
    queryFn: ({ signal }) => getSceneDetail(selected as number, signal),
    enabled: selected !== null,
    staleTime: 30_000,
    retry: false,
  });

  const backfill = useMutation({
    mutationFn: () => triggerVideoBackfill(videoId),
    onSuccess: () => {
      // Scenes will enrich in the background; refresh the list + open detail.
      void qc.invalidateQueries({ queryKey: sceneKeys.videoScenes(videoId) });
      if (selected !== null) {
        void qc.invalidateQueries({ queryKey: sceneKeys.sceneDetail(selected) });
      }
    },
  });

  const scenes = scenesQuery.data?.scenes ?? [];
  const detail = detailQuery.data;

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: Escape (global handler) closes; scrim click is a pointer-only convenience
    // biome-ignore lint/a11y/noStaticElementInteractions: scrim click-to-close is a standard drawer affordance
    <div className={c.overlay} onClick={onClose}>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: inner onClick only stops scrim-close propagation; Esc (global) closes */}
      <div
        className={c.drawer}
        role="dialog"
        aria-label={`Scenes for video #${videoId}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className={c.header}>
          <Film size={16} aria-hidden />
          <span className={c.headerTitle}>Scenes</span>
          <span className={c.headerMeta}>
            {scenesQuery.isLoading ? 'loading…' : `${scenes.length} scenes`}
          </span>
          <button type="button" className={c.closeBtn} onClick={onClose} aria-label="Close">
            <X size={14} aria-hidden />
          </button>
        </header>

        <div className={c.body}>
          {scenesQuery.isError ? (
            <div className={ws.stateWrap}>
              <Film size={28} aria-hidden />
              <span className={ws.stateTitle}>Couldn't load scenes</span>
              <span className={ws.stateHint}>
                {scenesQuery.error instanceof ApiError && scenesQuery.error.status === 404
                  ? 'This video has no scene index. Run the deep-video backfill to create scenes.'
                  : 'The deep-video API may be offline. Start the backend on :8000.'}
              </span>
            </div>
          ) : scenes.length === 0 ? (
            <div className={ws.stateWrap}>
              <Film size={28} aria-hidden />
              <span className={ws.stateTitle}>
                {scenesQuery.isLoading ? 'Loading…' : 'No scenes yet'}
              </span>
              <span className={ws.stateHint}>
                Deep enrichment hasn't run for this video. Use Re-enrich below to detect scenes and
                extract tags, captions, transcript and faces.
              </span>
            </div>
          ) : (
            <>
              <div className={c.sceneList}>
                {scenes.map((sc) => (
                  <SceneRow
                    key={sc.id}
                    scene={sc}
                    active={selected === sc.id}
                    onSelect={() => setSelected(sc.id)}
                  />
                ))}
              </div>

              {selected !== null && (
                <div className={c.detail}>
                  {detailQuery.isLoading ? (
                    <span className={c.emptyNote}>Loading scene…</span>
                  ) : detail ? (
                    <>
                      <section className={c.section}>
                        <span className={c.sectionLabel}>
                          <Captions size={11} aria-hidden /> Caption
                        </span>
                        {detail.caption ? (
                          <p className={c.caption}>{detail.caption}</p>
                        ) : (
                          <span className={c.emptyNote}>
                            No caption yet — runs after the Tier 2 caption pass.
                          </span>
                        )}
                      </section>

                      <section className={c.section}>
                        <span className={c.sectionLabel}>
                          <Tags size={11} aria-hidden /> Tags
                        </span>
                        {detail.tags.length > 0 ? (
                          <div className={c.tagWrap}>
                            {detail.tags.map((t) => (
                              <span key={`${t.category}:${t.value}`} className={c.tag}>
                                {t.value}
                                {t.confidence != null && (
                                  <span className={c.tagConf}>{t.confidence.toFixed(2)}</span>
                                )}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className={c.emptyNote}>
                            No tags yet — runs after the Tier 0 tag pass.
                          </span>
                        )}
                      </section>

                      <section className={c.section}>
                        <span className={c.sectionLabel}>
                          <Hash size={11} aria-hidden /> Transcript
                        </span>
                        {detail.transcript.length > 0 ? (
                          <div className={c.transcript}>
                            {detail.transcript.map((seg) => (
                              <div
                                // No stable id; timing + text is a segment's natural identity.
                                key={`${seg.start_time ?? 'na'}-${seg.end_time ?? 'na'}-${seg.text}`}
                                className={c.segment}
                              >
                                <span className={c.segmentTime}>
                                  {fmtTime(seg.start_time)}–{fmtTime(seg.end_time)}
                                </span>
                                <span className={c.segmentText}>{seg.text}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span className={c.emptyNote}>
                            No transcript (silent or unprocessed).
                          </span>
                        )}
                      </section>

                      <section className={c.section}>
                        <span className={c.sectionLabel}>
                          <Users size={11} aria-hidden /> Faces
                        </span>
                        <span className={c.faceCount}>
                          <span className={c.faceCountNum}>{detail.face_count}</span>
                          {detail.face_count === 1 ? 'face detected' : 'faces detected'}
                        </span>
                      </section>
                    </>
                  ) : (
                    <span className={c.emptyNote}>Couldn't load this scene.</span>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <footer className={c.footer}>
          <span className={c.footerHint}>
            {backfill.isSuccess ? (
              <span className={c.started}>Re-enrichment started — scenes update shortly.</span>
            ) : backfill.isError ? (
              'Re-enrich failed. Check the backend.'
            ) : (
              'Re-run deep enrichment for this video.'
            )}
          </span>
          <button
            type="button"
            className={c.action}
            onClick={() => backfill.mutate()}
            disabled={backfill.isPending}
          >
            <RefreshCw size={13} aria-hidden /> {backfill.isPending ? 'Starting…' : 'Re-enrich'}
          </button>
        </footer>
      </div>
    </div>
  );
}

function SceneRow({
  scene,
  active,
  onSelect,
}: {
  scene: SceneListItem;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`${c.sceneRow}${active ? ` ${c.sceneRowActive}` : ''}`}
      onClick={onSelect}
      aria-pressed={active}
    >
      <span className={c.sceneRowIndex}>{(scene.scene_index ?? 0) + 1}</span>
      <span className={c.sceneRowTime}>
        {fmtTime(scene.start_time)}–{fmtTime(scene.end_time)}
      </span>
      <span className={c.statusFlags}>
        <span
          className={`${c.flag}${scene.tagged ? ` ${c.flagOn}` : ''}`}
          title={scene.tagged ? 'Tagged' : 'Not tagged'}
        >
          <Tags size={12} aria-hidden />
        </span>
        <span
          className={`${c.flag}${scene.captioned ? ` ${c.flagOn}` : ''}`}
          title={scene.captioned ? 'Captioned' : 'Not captioned'}
        >
          <Captions size={12} aria-hidden />
        </span>
        <span
          className={`${c.flag}${scene.transcribed ? ` ${c.flagOn}` : ''}`}
          title={scene.transcribed ? 'Transcribed' : 'Not transcribed'}
        >
          <Hash size={12} aria-hidden />
        </span>
        <span
          className={`${c.flag}${scene.face_count > 0 ? ` ${c.flagOn}` : ''}`}
          title={`${scene.face_count} face(s)`}
        >
          <Users size={12} aria-hidden />
        </span>
      </span>
    </button>
  );
}
