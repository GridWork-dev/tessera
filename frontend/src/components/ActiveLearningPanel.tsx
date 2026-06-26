import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, FlaskConical, Tag, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { mediaThumb } from '../api/client';
import { flagImage, listImages } from '../api/endpoints';
import {
  type ActiveLearningProposal,
  activeLearningNext,
  probeApply,
  probePreview,
} from '../api/personalize';
import { ratingColor } from '../lib/rating';
import * as s from './ActiveLearningPanel.css';

const QUEUE_COUNT = 24;
// Pull the human's flag history so we can both show tallies and pass explicit
// pos/neg ids to the probe (the probe API takes id lists, not a server-side
// flag_action partition — only active-learning resolves labels server-side).
const LABEL_PAGE = 500;

const queueKey = ['personalize', 'active-learning', QUEUE_COUNT] as const;
const labelsKey = ['personalize', 'flag-labels'] as const;

interface FlagLabels {
  pos: number[];
  neg: number[];
}

function useFlagLabels() {
  return useQuery<FlagLabels>({
    queryKey: labelsKey,
    queryFn: async ({ signal }) => {
      const res = await listImages(
        { flagged: true, sort: 'recent', page: 1, limit: LABEL_PAGE },
        signal,
      );
      const pos: number[] = [];
      const neg: number[] = [];
      for (const im of res.images) {
        if (im.flag_action === 'keep') pos.push(im.id);
        else if (im.flag_action === 'reject') neg.push(im.id);
      }
      return { pos, neg };
    },
    staleTime: 10_000,
    retry: false,
  });
}

/**
 * Active-learning surface over /api/personalize. Two stacked sections:
 *   1. "Next to label" — the uncertainty-ranked queue; keep/reject each image
 *      (reuses the shared flag action: keep -> positive, reject -> negative).
 *   2. "Few-shot probe" — fit a linear probe on those labels and preview how
 *      many images it would tag, with an explicit (dry-run-first) apply step.
 *
 * Content-only (no app chrome): designed to slot into the existing /training
 * route as a tab/section. Renders cleanly with no signals — cold start shows
 * guidance, never a crash; a backend error surfaces as an inline state.
 */
export function ActiveLearningPanel() {
  const labels = useFlagLabels();
  return (
    <div className={s.wrap}>
      <NextToLabel labels={labels.data} />
      <ProbePanel labels={labels.data} />
    </div>
  );
}

// ---- Section 1: uncertainty queue ----

function NextToLabel({ labels }: { labels: FlagLabels | undefined }) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: queueKey,
    queryFn: ({ signal }) => activeLearningNext(QUEUE_COUNT, signal),
    retry: false,
    staleTime: 10_000,
  });

  const flag = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'keep' | 'reject' }) =>
      flagImage(id, action),
    onSettled: () => {
      // A new label moves the boundary — refetch the queue, tallies, and any grid.
      void qc.invalidateQueries({ queryKey: ['personalize'] });
      void qc.invalidateQueries({ queryKey: ['images'] });
    },
  });

  const data = query.data;
  const proposals = data?.proposals ?? [];

  return (
    <section className={s.section} aria-label="Next to label">
      <header className={s.sectionHead}>
        <span className={s.sectionTitle}>Next to label</span>
        <span className={s.spacer} />
        {data && (
          <span className={s.counts}>
            <span className={s.countChip}>{data.n_pos} keep</span>
            <span className={s.countChip}>{data.n_neg} reject</span>
            <span className={s.countChip}>{data.n_unlabeled} unlabeled</span>
          </span>
        )}
      </header>

      {query.isError ? (
        <div className={s.state}>
          <FlaskConical size={24} aria-hidden />
          <span className={s.stateTitle}>Active learning unavailable</span>
          <span className={s.stateHint}>
            The backend may be offline. Start it with <code className={s.code}>make backend</code>{' '}
            on :8000.
          </span>
        </div>
      ) : query.isLoading ? (
        <div className={s.state}>
          <span className={s.stateTitle}>Loading queue…</span>
        </div>
      ) : proposals.length === 0 ? (
        <div className={s.state}>
          <Tag size={24} aria-hidden />
          <span className={s.stateTitle}>Nothing to label yet</span>
          <span className={s.stateHint}>
            {data?.reason ?? 'No unlabeled assets with embeddings.'}
          </span>
        </div>
      ) : (
        <>
          {!data?.ready && (
            <p className={s.coldNote}>
              {data?.reason ?? 'Cold start — label some assets to begin.'}
            </p>
          )}
          <div className={s.grid}>
            {proposals.map((p) => (
              <ProposalCard
                key={p.image_id}
                proposal={p}
                ready={data?.ready ?? false}
                labeled={
                  labels?.pos.includes(p.image_id)
                    ? 'keep'
                    : labels?.neg.includes(p.image_id)
                      ? 'reject'
                      : null
                }
                onLabel={(action) => flag.mutate({ id: p.image_id, action })}
                pending={flag.isPending && flag.variables?.id === p.image_id}
              />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function ProposalCard({
  proposal,
  ready,
  labeled,
  onLabel,
  pending,
}: {
  proposal: ActiveLearningProposal;
  ready: boolean;
  labeled: 'keep' | 'reject' | null;
  onLabel: (action: 'keep' | 'reject') => void;
  pending: boolean;
}) {
  // The queue ships file_hash with each proposal, so the thumbnail renders
  // without a getImageDetail fetch per card (previously up to QUEUE_COUNT at once).
  const hash = proposal.file_hash;
  // Ready queues rank by uncertainty (prob near 0.5); cold start by similarity.
  const pct = Math.round(proposal.probability * 100);

  return (
    <div className={`${s.card}${pending ? ` ${s.cardPending}` : ''}`}>
      <div className={s.thumbWrap}>
        {hash ? (
          <img className={s.thumb} src={mediaThumb(hash)} alt="" loading="lazy" />
        ) : (
          <div className={s.thumbEmpty} aria-hidden />
        )}
        <span className={s.scoreBadge} title={ready ? 'Probe probability' : 'Similarity to kept'}>
          {pct}%
        </span>
      </div>
      <div className={s.cardActions}>
        <button
          type="button"
          className={`${s.labelBtn}${labeled === 'keep' ? ` ${s.labelBtnOn}` : ''}`}
          onClick={() => onLabel('keep')}
          disabled={pending}
          aria-pressed={labeled === 'keep'}
          style={{ color: ratingColor('sfw') }}
        >
          <Check size={14} aria-hidden /> Keep
        </button>
        <button
          type="button"
          className={`${s.labelBtn}${labeled === 'reject' ? ` ${s.labelBtnOn}` : ''}`}
          onClick={() => onLabel('reject')}
          disabled={pending}
          aria-pressed={labeled === 'reject'}
          style={{ color: ratingColor('nsfw') }}
        >
          <X size={14} aria-hidden /> Reject
        </button>
      </div>
    </div>
  );
}

// ---- Section 2: probe preview / apply ----

function ProbePanel({ labels }: { labels: FlagLabels | undefined }) {
  const qc = useQueryClient();
  const [category, setCategory] = useState('tags');
  const [value, setValue] = useState('');
  const [threshold, setThreshold] = useState(0.5);

  const posIds = useMemo(() => labels?.pos ?? [], [labels]);
  const negIds = useMemo(() => labels?.neg ?? [], [labels]);
  const haveBoth = posIds.length > 0 && negIds.length > 0;

  const preview = useMutation({
    mutationFn: () => probePreview({ pos_ids: posIds, neg_ids: negIds, threshold, sample: 12 }),
  });

  const apply = useMutation({
    mutationFn: () =>
      probeApply({
        pos_ids: posIds,
        neg_ids: negIds,
        category: category.trim(),
        value: value.trim(),
        threshold,
        dry_run: false,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['images'] });
      void qc.invalidateQueries({ queryKey: ['facets'] });
    },
  });

  const previewData = preview.data;
  const applyData = apply.data;
  const canApply = haveBoth && category.trim().length > 0 && value.trim().length > 0;

  return (
    <section className={s.section} aria-label="Few-shot probe">
      <header className={s.sectionHead}>
        <FlaskConical size={15} aria-hidden />
        <span className={s.sectionTitle}>Few-shot probe</span>
        <span className={s.spacer} />
        {labels && (
          <span className={s.counts}>
            <span className={s.countChip}>{posIds.length} keep</span>
            <span className={s.countChip}>{negIds.length} reject</span>
          </span>
        )}
      </header>

      {!haveBoth ? (
        <div className={s.state}>
          <FlaskConical size={24} aria-hidden />
          <span className={s.stateTitle}>Probe needs both classes</span>
          <span className={s.stateHint}>
            Label at least one Keep and one Reject above. The probe then estimates how many images
            share that preference and can tag them in one pass.
          </span>
        </div>
      ) : (
        <div className={s.probeForm}>
          <div className={s.field}>
            <label className={s.fieldLabel} htmlFor="probe-threshold">
              Threshold
              <span className={s.thresholdValue}>{threshold.toFixed(2)}</span>
            </label>
            <input
              id="probe-threshold"
              className={s.range}
              type="range"
              min={0.05}
              max={0.95}
              step={0.05}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
          </div>

          <button
            type="button"
            className={s.previewBtn}
            onClick={() => preview.mutate()}
            disabled={preview.isPending}
          >
            {preview.isPending ? 'Estimating…' : 'Preview match count'}
          </button>

          {preview.isError && (
            <p className={s.errLine}>Preview failed — check the backend and try again.</p>
          )}

          {previewData && (
            <div className={s.previewResult}>
              <span className={s.bigCount}>{previewData.count.toLocaleString()}</span>
              <span className={s.bigCountLabel}>
                of {previewData.total.toLocaleString()} images would be tagged at ≥{' '}
                {previewData.threshold.toFixed(2)}
              </span>

              <div className={s.applyRow}>
                <Tag size={14} aria-hidden className={s.applyIcon} />
                <input
                  className={s.input}
                  placeholder="category (e.g. tags)"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  aria-label="tag category"
                />
                <input
                  className={s.input}
                  placeholder="value (e.g. my-vibe)"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  aria-label="tag value"
                />
                <button
                  type="button"
                  className={s.applyBtn}
                  onClick={() => apply.mutate()}
                  disabled={!canApply || apply.isPending}
                >
                  {apply.isPending ? 'Applying…' : 'Apply tag'}
                </button>
              </div>
              <p className={s.applyHint}>
                Writes{' '}
                <code className={s.code}>
                  {category.trim() || 'tags'}:{value.trim() || '…'}
                </code>{' '}
                to every matching image (tag_source <code className={s.code}>probe</code>). Back up
                the library first.
              </p>

              {apply.isError && <p className={s.errLine}>Apply failed — no tags were written.</p>}
              {applyData && !apply.isError && (
                <p className={s.okLine}>
                  Tagged {applyData.written.toLocaleString()} images with{' '}
                  <code className={s.code}>
                    {category.trim()}:{value.trim()}
                  </code>
                  .
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
