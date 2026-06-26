import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pencil, Scissors, ShieldOff, Trash2, UserRound, Users, X } from 'lucide-react';
import { type MouseEvent, useEffect, useState } from 'react';
import { mediaThumb } from '../api/client';
import {
  ApiError,
  deletePerson,
  type Face,
  facesForPerson,
  listPeople,
  mergePeople,
  namePerson,
  type Person,
  purgeAllFaces,
  runClustering,
  splitFace,
} from '../api/faces';
import * as s from '../styles/workspace.css';
import { AppNav } from './AppNav';
import * as c from './PeopleView.css';

/* ---- query keys (local to this lane; queries.ts is owned elsewhere) ---- */
const peopleKey = ['faces', 'people'] as const;
const personFacesKey = (id: number) => ['faces', 'person', id] as const;

function isDisabled(err: unknown): boolean {
  return err instanceof ApiError && err.status === 403;
}

function personLabel(p: Person): string {
  return p.name ?? `Cluster #${p.id}`;
}

/**
 * Render a face's source-image thumbnail from its `file_hash` (now returned on
 * the Face / Person responses). No per-face image-detail fetch — opening a person
 * with N faces used to fire N full /api/images/{id} requests just to read the hash.
 */
function FaceThumb({
  hash,
  alt,
  imgClass = c.faceImg,
  emptyClass = c.faceImgEmpty,
}: {
  hash: string | null;
  alt: string;
  imgClass?: string;
  emptyClass?: string;
}) {
  if (hash) {
    return <img className={imgClass} src={mediaThumb(hash)} alt={alt} loading="lazy" />;
  }
  return (
    <div className={emptyClass}>
      <UserRound size={22} aria-hidden />
    </div>
  );
}

export function PeopleView() {
  const qc = useQueryClient();
  const [openId, setOpenId] = useState<number | null>(null);

  const peopleQ = useQuery({
    queryKey: peopleKey,
    queryFn: ({ signal }) => listPeople(signal),
    retry: false,
    staleTime: 30_000,
  });

  // Rename lifted to the parent so both the card (inline) and the detail modal
  // share one mutation + the same `disabled` (403) gate.
  const rename = useMutation({
    mutationFn: ({ personId, name }: { personId: number; name: string }) =>
      namePerson(personId, name),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['faces'] }),
  });

  const cluster = useMutation({
    mutationFn: runClustering,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['faces'] }),
  });

  const purge = useMutation({
    mutationFn: purgeAllFaces,
    onSuccess: () => {
      setOpenId(null);
      void qc.invalidateQueries({ queryKey: ['faces'] });
    },
  });

  const people = peopleQ.data ?? [];
  const disabled = isDisabled(peopleQ.error);
  const total = people.reduce((n, p) => n + p.face_count, 0);

  return (
    <div className={s.appFrame}>
      <header className={s.commandBar}>
        <AppNav />
        <span className={s.pageTitle}>People</span>
        <span className={s.barSpacer} />
        <span className={s.pageMeta}>
          {disabled
            ? 'faces off'
            : peopleQ.isLoading
              ? 'loading…'
              : `${people.length.toLocaleString()} people · ${total.toLocaleString()} faces`}
        </span>
      </header>

      {disabled ? (
        <DisabledState />
      ) : (
        <div className={`${s.body} ${s.bodyNoInspector}`}>
          <aside className={s.rail} aria-label="Faces actions">
            <div className={s.railHeader}>
              <span className={s.railHeaderTitle}>Actions</span>
            </div>
            <div className={c.railActions}>
              <button
                type="button"
                className={c.buttonAccent}
                onClick={() => cluster.mutate()}
                disabled={cluster.isPending}
              >
                <Users size={14} aria-hidden />
                {cluster.isPending ? 'Clustering…' : 'Run clustering'}
              </button>
              {cluster.isSuccess && cluster.data && (
                <span className={s.stateHint}>
                  {cluster.data.clusters_created} new · {cluster.data.faces_assigned} assigned ·{' '}
                  {cluster.data.noise} noise
                </span>
              )}
              {cluster.isError && <span className={c.errorBanner}>Clustering failed.</span>}

              {people.length > 0 && (
                <button
                  type="button"
                  className={c.buttonDanger}
                  onClick={() => {
                    if (window.confirm('Erase all faces and people? This cannot be undone.'))
                      purge.mutate();
                  }}
                  disabled={purge.isPending}
                >
                  <ShieldOff size={14} aria-hidden />
                  {purge.isPending ? 'Purging…' : 'Purge all faces'}
                </button>
              )}
            </div>
          </aside>

          <div className={s.gridRegion}>
            {peopleQ.isError ? (
              <div className={s.stateWrap}>
                <UserRound size={28} aria-hidden="true" />
                <span className={s.stateTitle}>Couldn't load people</span>
                <span className={s.stateHint}>
                  The backend may be offline. Start it with{' '}
                  <code className={c.codeInline}>make backend</code> on :8000.
                </span>
              </div>
            ) : people.length === 0 ? (
              <div className={s.stateWrap}>
                <UserRound size={28} aria-hidden="true" />
                <span className={s.stateTitle}>
                  {peopleQ.isLoading ? 'Loading…' : 'No people yet'}
                </span>
                <span className={s.stateHint}>
                  Faces are detected as images are processed. Use{' '}
                  <code className={c.codeInline}>Run clustering</code> to group detected faces into
                  people.
                </span>
              </div>
            ) : (
              <div className={c.gridPad}>
                <div className={c.grid}>
                  {people.map((p) => (
                    <PersonCard
                      key={p.id}
                      person={p}
                      active={openId === p.id}
                      onOpen={() => setOpenId(p.id)}
                      rename={rename}
                      disabled={disabled}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {openId !== null && (
        <PersonDetail
          personId={openId}
          people={people}
          rename={rename}
          onClose={() => setOpenId(null)}
          onDeleted={() => setOpenId(null)}
        />
      )}
    </div>
  );
}

/** The rename mutation shape lifted to the PeopleView parent and shared by the
 *  card (inline edit) and the detail modal. */
type RenameMutation = {
  mutate: (vars: { personId: number; name: string }) => void;
  isPending: boolean;
};

function PersonCard({
  person,
  active,
  onOpen,
  rename,
  disabled,
}: {
  person: Person;
  active: boolean;
  onOpen: () => void;
  rename: RenameMutation;
  disabled: boolean;
}) {
  const [inlineEditing, setInlineEditing] = useState(false);
  const [draft, setDraft] = useState(person.name ?? '');

  const startEdit = (e: MouseEvent) => {
    if (disabled) return;
    e.stopPropagation();
    setDraft(person.name ?? '');
    setInlineEditing(true);
  };

  const submit = () => {
    const name = draft.trim();
    if (name) rename.mutate({ personId: person.id, name });
    setInlineEditing(false);
  };

  return (
    <button
      type="button"
      className={`${c.card}${active ? ` ${c.cardActive}` : ''}`}
      onClick={onOpen}
    >
      {person.cover_image_id != null ? (
        <FaceThumb
          hash={person.cover_image_hash}
          alt={personLabel(person)}
          imgClass={c.cover}
          emptyClass={c.coverEmpty}
        />
      ) : (
        <div className={c.coverEmpty}>
          <UserRound size={36} aria-hidden />
        </div>
      )}
      <div className={c.cardMeta}>
        {inlineEditing ? (
          // A nested <form> would be invalid HTML inside the card <button>, so
          // this is a plain row: Enter submits, Escape cancels (input keydown),
          // and the controls stopPropagation so the card's open-modal click and
          // global Escape handlers don't fire mid-edit.
          <span className={c.inlineRow}>
            <input
              className={c.input}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Person name"
              // biome-ignore lint/a11y/noAutofocus: focus the editor the moment it opens
              autoFocus
              aria-label="Person name"
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === 'Enter') {
                  e.preventDefault();
                  submit();
                } else if (e.key === 'Escape') {
                  e.preventDefault();
                  setInlineEditing(false);
                }
              }}
            />
            <button
              type="button"
              className={c.buttonAccent}
              disabled={rename.isPending}
              onClick={(e) => {
                e.stopPropagation();
                submit();
              }}
            >
              <Check size={14} aria-hidden />
            </button>
            <button
              type="button"
              className={c.button}
              onClick={(e) => {
                e.stopPropagation();
                setInlineEditing(false);
              }}
            >
              <X size={14} aria-hidden />
            </button>
          </span>
        ) : (
          <>
            {/* biome-ignore lint/a11y/noStaticElementInteractions: double-click to inline-rename; the card's own click still opens the modal */}
            <span
              className={`${person.name ? c.cardName : c.cardNameUnnamed}${disabled ? '' : ` ${c.cardNameEditable}`}`}
              onDoubleClick={startEdit}
              title={disabled ? undefined : 'Double-click to rename'}
            >
              {personLabel(person)}
              {!disabled && <Pencil size={12} aria-hidden className={c.cardEditIcon} />}
            </span>
            <span className={c.cardCount}>{person.face_count}</span>
          </>
        )}
      </div>
    </button>
  );
}

function PersonDetail({
  personId,
  people,
  rename,
  onClose,
  onDeleted,
}: {
  personId: number;
  people: Person[];
  rename: RenameMutation;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const qc = useQueryClient();
  const person = people.find((p) => p.id === personId);

  const [editing, setEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState(person?.name ?? '');
  const [actionError, setActionError] = useState<string | null>(null);

  const facesQ = useQuery({
    queryKey: personFacesKey(personId),
    queryFn: ({ signal }) => facesForPerson(personId, signal),
    retry: false,
    staleTime: 30_000,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['faces'] });
  const fail = (msg: string) => () => setActionError(msg);

  const merge = useMutation({
    mutationFn: (targetId: number) => mergePeople(personId, targetId),
    onSuccess: () => {
      setActionError(null);
      invalidate();
      onClose();
    },
    onError: fail('Merge failed.'),
  });

  const split = useMutation({
    mutationFn: (faceId: number) => splitFace(faceId),
    onSuccess: () => {
      setActionError(null);
      invalidate();
    },
    onError: fail('Split failed.'),
  });

  const erase = useMutation({
    mutationFn: () => deletePerson(personId),
    onSuccess: () => {
      setActionError(null);
      invalidate();
      onDeleted();
    },
    onError: fail('Erase failed.'),
  });

  const faces = facesQ.data ?? [];
  const mergeOptions = people.filter((p) => p.id !== personId);
  const title = person ? personLabel(person) : `Cluster #${personId}`;

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: Escape (global handler) closes; scrim click is a pointer-only convenience
    // biome-ignore lint/a11y/noStaticElementInteractions: scrim click-to-close is a standard modal affordance
    <div className={c.overlay} onClick={onClose}>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: inner guard only stops scrim-close propagation */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: stops propagation so clicks inside the dialog don't close it */}
      <div className={c.dialog} onClick={(e) => e.stopPropagation()}>
        <div className={c.dialogHeader}>
          {editing ? (
            <form
              className={c.inlineRow}
              onSubmit={(e) => {
                e.preventDefault();
                const name = nameDraft.trim();
                if (name) {
                  rename.mutate({ personId, name });
                  setEditing(false);
                  setActionError(null);
                }
              }}
            >
              <input
                className={c.input}
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                placeholder="Person name"
                // biome-ignore lint/a11y/noAutofocus: focus the editor the moment it opens
                autoFocus
                aria-label="Person name"
              />
              <button type="submit" className={c.buttonAccent} disabled={rename.isPending}>
                <Check size={14} aria-hidden /> Save
              </button>
              <button type="button" className={c.button} onClick={() => setEditing(false)}>
                Cancel
              </button>
            </form>
          ) : (
            <>
              <span className={c.dialogTitle}>{title}</span>
              <button
                type="button"
                className={c.button}
                onClick={() => {
                  setNameDraft(person?.name ?? '');
                  setEditing(true);
                }}
              >
                <Pencil size={14} aria-hidden /> {person?.name ? 'Rename' : 'Name'}
              </button>
            </>
          )}
          <button type="button" className={c.button} onClick={onClose} aria-label="Close (Esc)">
            <X size={14} aria-hidden />
          </button>
        </div>

        <div className={c.dialogBody}>
          {actionError && <div className={c.errorBanner}>{actionError}</div>}

          <div className={c.dialogActions}>
            <span className={s.barSpacer} />
            <button
              type="button"
              className={c.buttonDanger}
              disabled={erase.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    `Erase "${title}" and all ${person?.face_count ?? 0} face embeddings? This cannot be undone.`,
                  )
                )
                  erase.mutate();
              }}
            >
              <Trash2 size={14} aria-hidden /> {erase.isPending ? 'Erasing…' : 'Erase person'}
            </button>
          </div>

          {mergeOptions.length > 0 && (
            <div className={c.mergeSection}>
              <span className={c.sectionLabel}>Merge into</span>
              <div className={c.mergeOptions}>
                {mergeOptions.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className={c.mergeOption}
                    disabled={merge.isPending}
                    onClick={() => merge.mutate(p.id)}
                  >
                    <Users size={14} aria-hidden />
                    <span className={c.mergeOptionName}>{personLabel(p)}</span>
                    <span className={c.mergeCount}>{p.face_count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <span className={c.sectionLabel}>Faces{faces.length ? ` (${faces.length})` : ''}</span>
          {facesQ.isError ? (
            <span className={s.stateHint}>Couldn't load faces for this person.</span>
          ) : faces.length === 0 ? (
            <span className={s.stateHint}>
              {facesQ.isLoading ? 'Loading…' : 'No faces assigned.'}
            </span>
          ) : (
            <div className={c.faceGrid}>
              {faces.map((f: Face) => (
                <div key={f.id} className={c.faceTile}>
                  <FaceThumb hash={f.file_hash} alt={`Face ${f.id}`} />
                  <button
                    type="button"
                    className={c.faceSplitBtn}
                    title="Split into a new person"
                    aria-label="Split face into a new person"
                    disabled={split.isPending}
                    onClick={() => split.mutate(f.id)}
                  >
                    <Scissors size={12} aria-hidden />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DisabledState() {
  // Faces-off is the DEFAULT state, so this is what most users see. Render it as
  // a full-width gridRegion (mirrors PlacesView) — NOT inside the 2-column `body`
  // grid, which would strand the explanation in the narrow 280px rail column.
  return (
    <div className={s.gridRegion}>
      <div className={c.optIn}>
        <ShieldOff size={40} aria-hidden className={c.optInIcon} />
        <span className={c.optInTitle}>Faces are off by default</span>
        <span className={c.optInBody}>
          Face detection and clustering process biometric data. For privacy (GDPR Art. 9 / BIPA),
          this feature is disabled until you explicitly opt in. No faces are detected or stored
          while it is off.
        </span>
        <span className={s.stateHint}>Enable it in config, then restart the backend:</span>
        <code className={c.codeBlock}>faces.enabled: true</code>
        <span className={s.stateHint}>or set the environment variable:</span>
        <code className={c.codeBlock}>MP_FACES_ENABLED=1</code>
      </div>
    </div>
  );
}
