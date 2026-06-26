import { Check, HelpCircle, ImageOff, Plus, TriangleAlert, X } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { mediaFull, mediaThumb } from '../api/client';
import type { Caption, DetailTag, ImageDetail, NudeRegion } from '../api/types';
import {
  useAddLabel,
  useDeleteLabel,
  useFlagImage,
  useImageDetail,
  useLabels,
  useSimilar,
} from '../hooks/queries';
import type { ViewDepth } from '../store/useWorkspace';
import { tagKey, useWorkspace } from '../store/useWorkspace';
import * as ws from '../styles/workspace.css';
import * as c from './Inspector.css';
import { LabelAssign } from './LabelAssign';
import { RatingChip } from './RatingChip';

interface InspectorProps {
  imageId: number | null;
  onOpenSimilar: (id: number) => void;
}

type FlagAction = 'reject' | 'maybe' | 'keep';

const FLAG_ACTIONS: { action: FlagAction; label: string; icon: typeof Check }[] = [
  { action: 'keep', label: 'Keep', icon: Check },
  { action: 'maybe', label: 'Maybe', icon: HelpCircle },
  { action: 'reject', label: 'Reject', icon: X },
];

const DEPTHS: { value: ViewDepth; label: string }[] = [
  { value: 'basic', label: 'Basic' },
  { value: 'detailed', label: 'Detailed' },
];

const BASIC_TAG_LIMIT = 8;

/** Human-readable byte size (binary). */
function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes <= 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB'] as const;
  let v = bytes;
  let idx = 0;
  while (v >= 1024 && idx < units.length - 1) {
    v /= 1024;
    idx += 1;
  }
  const unit = units[idx] ?? 'B';
  return `${v >= 100 || idx === 0 ? Math.round(v) : v.toFixed(1)} ${unit}`;
}

/** ISO/SQL timestamp → short local date. Falls back to the raw string. */
function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

const humanize = (v: string | null): string => (v ? v.replace(/_/g, ' ') : '—');

/** Group detail tags by category, dropping the rating (shown as the chip). */
function groupTags(tags: DetailTag[]): [string, DetailTag[]][] {
  const map = new Map<string, DetailTag[]>();
  for (const t of tags) {
    const cat = t.category ?? 'other';
    if (cat === 'rating') continue;
    const list = map.get(cat) ?? [];
    list.push(t);
    map.set(cat, list);
  }
  return [...map.entries()];
}

/* ============================================================
   Inspector — fetches detail by id and renders the in-depth
   metadata / triage / tags / captions / labels / similar panel.
   ============================================================ */

export function Inspector({ imageId, onOpenSimilar }: InspectorProps) {
  const viewDepth = useWorkspace((st) => st.viewDepth);
  const setViewDepth = useWorkspace((st) => st.setViewDepth);
  const setInspectorOpen = useWorkspace((st) => st.setInspectorOpen);

  const detail = useImageDetail(imageId);

  const head = (showToggle: boolean) => (
    <Header
      viewDepth={viewDepth}
      onDepth={setViewDepth}
      onClose={() => setInspectorOpen(false)}
      showToggle={showToggle}
    />
  );

  if (imageId === null) {
    return (
      <aside className={ws.inspector} aria-label="Inspector">
        {head(false)}
        <div className={ws.stateWrap}>
          <span className={ws.stateTitle}>No selection</span>
          <span className={ws.stateHint}>
            Select an asset to see its metadata, tags, and similar items.
          </span>
        </div>
      </aside>
    );
  }

  if (detail.isLoading) {
    return (
      <aside className={ws.inspector} aria-label="Inspector">
        {head(false)}
        <div className={ws.stateWrap}>
          <span className={ws.stateHint}>Loading detail…</span>
        </div>
      </aside>
    );
  }

  if (detail.isError || !detail.data) {
    const notFound = detail.error instanceof Error && /404/.test(detail.error.message);
    return (
      <aside className={ws.inspector} aria-label="Inspector">
        {head(false)}
        <div className={ws.stateWrap} role="alert">
          <TriangleAlert size={24} aria-hidden="true" />
          <span className={ws.stateTitle}>{notFound ? 'Not found' : "Couldn't load asset"}</span>
          <span className={ws.stateHint}>
            {notFound
              ? 'This asset is no longer in the library.'
              : "The asset's detail didn't load. Try again."}
          </span>
        </div>
      </aside>
    );
  }

  return (
    <DetailView
      key={detail.data.id}
      detail={detail.data}
      viewDepth={viewDepth}
      onDepth={setViewDepth}
      onClose={() => setInspectorOpen(false)}
      onOpenSimilar={onOpenSimilar}
    />
  );
}

/* ---- Header: zone title + segmented depth toggle + close ---- */

function Header({
  viewDepth,
  onDepth,
  onClose,
  showToggle,
}: {
  viewDepth: ViewDepth;
  onDepth: (d: ViewDepth) => void;
  onClose: () => void;
  showToggle: boolean;
}) {
  return (
    <div className={ws.inspectorHeader}>
      <span className={ws.inspectorTitle}>Inspector</span>
      <div className={c.headerControls}>
        {showToggle && (
          // biome-ignore lint/a11y/useSemanticElements: a toolbar button group; role=group is the correct ARIA, not a fieldset
          <div className={c.depthToggle} role="group" aria-label="Detail level">
            {DEPTHS.map((d) => (
              <button
                key={d.value}
                type="button"
                className={`${c.depthSeg}${viewDepth === d.value ? ` ${c.depthSegActive}` : ''}`}
                aria-pressed={viewDepth === d.value}
                onClick={() => onDepth(d.value)}
              >
                {d.label}
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          className={ws.iconButton}
          onClick={onClose}
          aria-label="Close inspector"
          title="Close inspector"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

interface DetailViewProps {
  detail: ImageDetail;
  viewDepth: ViewDepth;
  onDepth: (d: ViewDepth) => void;
  onClose: () => void;
  onOpenSimilar: (id: number) => void;
}

function DetailView({ detail, viewDepth, onDepth, onClose, onOpenSimilar }: DetailViewProps) {
  const detailed = viewDepth === 'detailed';

  return (
    <aside className={ws.inspector} aria-label="Inspector">
      <Header viewDepth={viewDepth} onDepth={onDepth} onClose={onClose} showToggle={true} />
      <Preview hash={detail.file_hash} filename={detail.filename} />

      <div className={ws.inspectorBody}>
        <TriageSection id={detail.id} current={detail.flag_action} />
        <MetadataSection detail={detail} detailed={detailed} />
        <LabelSetsSection imageId={detail.id} />
        <TagsSection tags={detail.tags} detailed={detailed} />
        <CaptionsSection captions={detail.captions} />
        {detailed && <RegionsSection regions={detail.nudenet_regions} />}
        <NotesSection notes={detail.notes} />
        {detailed && <LabelsSection imageId={detail.id} />}
        <SimilarSection imageId={detail.id} onOpenSimilar={onOpenSimilar} />
      </div>
    </aside>
  );
}

/* ---- Preview (full-res → thumb fallback → placeholder) ---- */

function Preview({ hash, filename }: { hash: string | null; filename: string | null }) {
  const [previewFailed, setPreviewFailed] = useState(false);
  const [thumbFailed, setThumbFailed] = useState(false);

  const src = !hash
    ? null
    : previewFailed
      ? thumbFailed
        ? null
        : mediaThumb(hash)
      : mediaFull(hash);

  return (
    <div className={c.preview}>
      {src ? (
        <img
          className={c.previewImg}
          src={src}
          alt={filename ?? 'Asset preview'}
          onError={() => {
            if (!previewFailed) setPreviewFailed(true);
            else setThumbFailed(true);
          }}
        />
      ) : (
        <div className={c.previewPlaceholder}>
          <ImageOff size={28} aria-hidden="true" />
          <span className={c.previewPlaceholderText}>Preview unavailable</span>
        </div>
      )}
    </div>
  );
}

/* ---- Triage (Keep / Maybe / Reject) + inline error strip ---- */

function TriageSection({ id, current }: { id: number; current: FlagAction | null }) {
  const flag = useFlagImage();
  return (
    <div className={c.section}>
      <div className={c.sectionHead}>
        <span className={ws.groupLabel} style={{ marginBottom: 0 }}>
          Triage
        </span>
      </div>
      <div className={c.triageRow}>
        {FLAG_ACTIONS.map(({ action, label, icon: Icon }) => {
          const active = current === action;
          return (
            <button
              key={action}
              type="button"
              className={`${c.triageBtn}${active ? ` ${c.triageBtnActive}` : ''}`}
              aria-pressed={active}
              disabled={flag.isPending}
              onClick={() => flag.mutate({ id, action })}
            >
              <Icon size={14} aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>
      {flag.isError && (
        <div className={c.errorBox} role="alert">
          <TriangleAlert size={14} aria-hidden="true" />
          <span>
            Couldn't save the flag —{' '}
            {flag.error instanceof Error ? flag.error.message : 'try again'}.
          </span>
        </div>
      )}
    </div>
  );
}

/* ---- Metadata grid (sentence-case keys, mono values) ---- */

function MetadataSection({ detail, detailed }: { detail: ImageDetail; detailed: boolean }) {
  return (
    <div className={ws.metaGrid}>
      <span className={ws.metaKey}>Person</span>
      <span className={ws.metaVal}>{humanize(detail.person)}</span>

      <span className={ws.metaKey}>Rating</span>
      <span className={ws.metaVal}>
        <RatingChip rating={detail.rating} />
      </span>

      <span className={ws.metaKey}>Dimensions</span>
      <span className={ws.metaVal}>
        {detail.width && detail.height ? `${detail.width}×${detail.height}` : '—'}
      </span>

      <span className={ws.metaKey}>Filesize</span>
      <span className={ws.metaVal}>{formatBytes(detail.filesize)}</span>

      <span className={ws.metaKey}>Format</span>
      <span className={ws.metaVal}>{detail.format ?? '—'}</span>

      <span className={ws.metaKey}>Imported</span>
      <span className={ws.metaVal}>{formatDate(detail.imported_at)}</span>

      {detailed && (
        <>
          <span className={ws.metaKey}>Path</span>
          <span className={ws.metaVal}>{detail.path}</span>

          <span className={ws.metaKey}>Original filename</span>
          <span className={ws.metaVal}>{detail.original_filename ?? '—'}</span>

          <span className={ws.metaKey}>Media type</span>
          <span className={ws.metaVal}>{detail.media_type}</span>

          <span className={ws.metaKey}>Has metadata</span>
          <span className={ws.metaVal}>{detail.has_metadata ? 'yes' : 'no'}</span>
        </>
      )}
    </div>
  );
}

/* ---- Label sets (Wave 2b): assign user-defined faceted labels. The Rating
   set renders here from the seeded single-select set, not images.rating. ---- */

function LabelSetsSection({ imageId }: { imageId: number }) {
  return (
    <div className={c.section}>
      <div className={c.sectionHead}>
        <span className={ws.groupLabel} style={{ marginBottom: 0 }}>
          Labels
        </span>
      </div>
      <LabelAssign imageId={imageId} />
    </div>
  );
}

/* ---- Tags grouped by category (basic = top ~8; detailed = all) ---- */

function TagsSection({ tags, detailed }: { tags: DetailTag[]; detailed: boolean }) {
  const groups = groupTags(tags);
  return (
    <div className={c.section}>
      <div className={c.sectionHead}>
        <span className={ws.groupLabel} style={{ marginBottom: 0 }}>
          Tags
        </span>
        {tags.length > 0 && <span className={c.sectionCount}>{tags.length}</span>}
      </div>
      {groups.length === 0 ? (
        <span className={ws.stateHint}>No tags yet — runs after the Tier 0 tag pass.</span>
      ) : (
        <div className={c.tagGroups}>
          {groups.map(([cat, group]) => {
            const shown = detailed ? group : group.slice(0, BASIC_TAG_LIMIT);
            const hidden = group.length - shown.length;
            const source = group.find((t) => t.tag_source)?.tag_source;
            return (
              <div key={cat} className={c.tagGroup}>
                <div className={c.tagGroupLabel}>
                  <span>{cat.replace(/_/g, ' ')}</span>
                  {detailed && source && <span className={c.tagSource}>{source}</span>}
                </div>
                <div className={ws.chipWrap}>
                  {shown.map((t, idx) => (
                    <span key={`${cat}:${t.value ?? idx}`} className={ws.chip}>
                      {t.value ?? '—'}
                      {t.confidence !== null && (
                        <span className={ws.chipConf}>{Math.round(t.confidence * 100)}</span>
                      )}
                    </span>
                  ))}
                  {hidden > 0 && <span className={c.sectionCount}>+{hidden} more</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ---- Captions (Tier 2) ---- */

function CaptionsSection({ captions }: { captions: Caption[] }) {
  const present = captions.filter((cap) => cap.caption);
  return (
    <div className={c.section}>
      <div className={c.sectionHead}>
        <span className={ws.groupLabel} style={{ marginBottom: 0 }}>
          Captions
        </span>
      </div>
      {present.length === 0 ? (
        <span className={ws.stateHint}>No caption yet — runs after the Tier 2 caption pass.</span>
      ) : (
        <div className={c.captionList}>
          {present.map((cap, idx) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: captions have no stable id; list order is stable
            <div key={`${cap.model ?? 'm'}-${idx}`} className={c.captionItem}>
              {cap.model && <span className={c.captionModel}>{cap.model}</span>}
              <span className={c.captionText}>{cap.caption}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---- NudeNet regions (detailed only; metadata, never a gate) ---- */

function RegionsSection({ regions }: { regions: NudeRegion[] | null }) {
  if (regions === null || regions.length === 0) return null;
  return (
    <div className={c.section}>
      <div className={c.sectionHead}>
        <span className={ws.groupLabel} style={{ marginBottom: 0 }}>
          Regions
        </span>
        <span className={c.sectionCount}>{regions.length}</span>
      </div>
      <div className={ws.chipWrap}>
        {regions.map((r, idx) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: regions have no stable id; list order is stable
          <span key={`${r.label}-${idx}`} className={c.nudeChip}>
            {r.label.replace(/_/g, ' ').toLowerCase()}
            <span className={c.nudeScore}>{Math.round(r.score * 100)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/* ---- Notes (read-only) ---- */

function NotesSection({ notes }: { notes: string | null }) {
  const text = notes?.trim();
  if (!text) return null;
  return (
    <div className={c.section}>
      <div className={c.sectionHead}>
        <span className={ws.groupLabel} style={{ marginBottom: 0 }}>
          Notes
        </span>
      </div>
      <div className={c.notesBox}>{text}</div>
    </div>
  );
}

/* ---- User labels (detailed only): removable chips + add input ---- */

function LabelsSection({ imageId }: { imageId: number }) {
  const labels = useLabels(imageId);
  const addLabel = useAddLabel(imageId);
  const deleteLabel = useDeleteLabel(imageId);
  const [value, setValue] = useState('');

  function submit(e: FormEvent) {
    e.preventDefault();
    const v = value.trim();
    if (!v || addLabel.isPending) return;
    addLabel.mutate({ value: v }, { onSuccess: () => setValue('') });
  }

  const items = labels.data?.labels ?? [];

  return (
    <div className={c.section}>
      <div className={c.sectionHead}>
        <span className={ws.groupLabel} style={{ marginBottom: 0 }}>
          Your labels
        </span>
        {items.length > 0 && <span className={c.sectionCount}>{items.length}</span>}
      </div>
      {items.length > 0 && (
        <div className={ws.chipWrap}>
          {items.map((label) => (
            <span key={label.id} className={c.labelChip}>
              <span className={c.labelChipText}>{label.value}</span>
              <button
                type="button"
                className={c.labelRemove}
                aria-label={`Remove label ${label.value}`}
                disabled={deleteLabel.isPending}
                onClick={() => deleteLabel.mutate(label.id)}
              >
                <X size={11} aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      )}
      <form className={c.labelForm} onSubmit={submit}>
        <input
          className={c.labelInput}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Add a label…"
          aria-label="Add a label"
          maxLength={80}
        />
        <button
          type="submit"
          className={c.labelAddBtn}
          disabled={value.trim() === '' || addLabel.isPending}
        >
          <Plus size={14} aria-hidden="true" />
          Add
        </button>
      </form>
    </div>
  );
}

/* ---- Similar (4-up clickable strip; graceful when vectors pending) ---- */

function SimilarSection({
  imageId,
  onOpenSimilar,
}: {
  imageId: number;
  onOpenSimilar: (id: number) => void;
}) {
  // Thread the active FacetRail multi-tag filter so "Similar" stays within the
  // current filter (allowlist pre-filter on the backend). No tags ⇒ unfiltered.
  const activeTags = useWorkspace((st) => st.activeTags);
  const filterTags = activeTags.map(tagKey);
  const sim = useSimilar(imageId, filterTags);
  const unavailable = sim.data?.vectors_unavailable === true || sim.isError;
  const results = sim.data?.results ?? [];

  return (
    <div className={c.section}>
      <div className={c.sectionHead}>
        <span className={ws.groupLabel} style={{ marginBottom: 0 }}>
          Similar
        </span>
        {filterTags.length > 0 && <span className={c.sectionCount}>within filter</span>}
      </div>
      {unavailable ? (
        <span className={ws.stateHint}>
          Embeddings pending — similarity activates after the Tier 1 SigLIP pass.
        </span>
      ) : sim.isLoading ? (
        <span className={ws.stateHint}>Finding similar…</span>
      ) : results.length === 0 ? (
        <span className={ws.stateHint}>No similar items.</span>
      ) : (
        <div className={c.similarGrid}>
          {results.slice(0, 4).map((r) => (
            <button
              key={r.id}
              type="button"
              className={c.similarTile}
              aria-label={`Open similar asset ${r.id}`}
              onClick={() => onOpenSimilar(r.id)}
            >
              <img className={c.similarImg} src={mediaThumb(r.file_hash)} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
