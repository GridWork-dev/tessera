import { useQuery } from '@tanstack/react-query';
import { CalendarRange, MapPin, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { type GeoEvent, getEventDetail, listEvents, memberThumb } from '../api/geo';
import * as s from '../styles/workspace.css';
import { AppNav } from './AppNav';
import * as c from './EventsView.css';

function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

/** "Mar 3 – Mar 5, 2024" style range; collapses to a single date when equal. */
function timeRange(ev: GeoEvent): string {
  const start = fmtDate(ev.start_time);
  const end = fmtDate(ev.end_time);
  if (!start && !end) return 'Undated';
  if (!end || start === end) return start ?? (end as string);
  if (!start) return end;
  return `${start} – ${end}`;
}

function centroid(ev: GeoEvent): string | null {
  if (ev.centroid_lat == null || ev.centroid_lon == null) return null;
  return `${ev.centroid_lat.toFixed(3)}, ${ev.centroid_lon.toFixed(3)}`;
}

export function EventsView() {
  const [openId, setOpenId] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['geo', 'events'],
    queryFn: ({ signal }) => listEvents(signal),
    staleTime: 60_000,
    retry: false,
  });

  const events = data ?? [];

  return (
    <div className={s.appFrame}>
      <header className={s.commandBar}>
        <AppNav />
        <span className={s.pageTitle}>Events</span>
        <span className={s.barSpacer} />
        <span className={s.pageMeta}>
          {isLoading ? 'loading…' : `${events.length.toLocaleString()} events`}
        </span>
      </header>

      <div className={s.gridRegion}>
        {isError ? (
          <div className={s.stateWrap}>
            <CalendarRange size={28} aria-hidden="true" />
            <span className={s.stateTitle}>Couldn't load events</span>
            <span className={s.stateHint}>
              The backend may be offline. Start it with{' '}
              <code className={c.codeInline}>make backend</code> on :8000.
            </span>
          </div>
        ) : events.length === 0 ? (
          <div className={s.stateWrap}>
            <CalendarRange size={28} aria-hidden="true" />
            <span className={s.stateTitle}>{isLoading ? 'Loading…' : 'No events yet'}</span>
            <span className={s.stateHint}>
              Events appear once the geo backfill clusters assets by time and place — run{' '}
              <code className={c.codeInline}>POST /api/geo/backfill</code> (stage{' '}
              <code className={c.codeInline}>events</code>).
            </span>
          </div>
        ) : (
          <div className={c.pad}>
            <div className={c.grid}>
              {events.map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  className={c.card}
                  onClick={() => setOpenId(ev.id)}
                >
                  <span className={c.cardLabel}>{ev.label || `Event #${ev.id}`}</span>
                  <span className={c.cardRange}>{timeRange(ev)}</span>
                  <span className={c.cardFoot}>
                    <span className={c.cardMembers}>
                      {ev.member_count.toLocaleString()} asset{ev.member_count === 1 ? '' : 's'}
                    </span>
                    {centroid(ev) && (
                      <span className={c.cardCentroid}>
                        <MapPin size={11} aria-hidden="true" />
                        {centroid(ev)}
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {openId !== null && <EventDetailModal eventId={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function EventDetailModal({ eventId, onClose }: { eventId: number; onClose: () => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['geo', 'event', eventId],
    queryFn: ({ signal }) => getEventDetail(eventId, signal),
    staleTime: 30_000,
    retry: false,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const members = data?.members ?? [];
  const images = members.filter((m) => m.owner_type === 'image');

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: Escape (global handler) closes the modal; scrim click is a pointer-only convenience
    // biome-ignore lint/a11y/noStaticElementInteractions: scrim click-to-close is a standard modal affordance
    <div className={c.overlay} onClick={onClose}>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: inner guard only stops scrim-close propagation, not an interactive control */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: stops propagation so clicks inside the dialog don't close it */}
      <div className={c.dialog} onClick={(e) => e.stopPropagation()}>
        <div className={c.dialogHead}>
          <span className={c.dialogText}>
            <span className={c.dialogTitle}>
              {data?.label || (isLoading ? 'Loading…' : `Event #${eventId}`)}
            </span>
            {data && (
              <span className={c.dialogMeta}>
                {timeRange(data)} · {data.member_count.toLocaleString()} asset
                {data.member_count === 1 ? '' : 's'}
                {centroid(data) ? ` · ${centroid(data)}` : ''}
              </span>
            )}
          </span>
          <button type="button" className={c.closeBtn} onClick={onClose}>
            <X size={14} aria-hidden="true" /> Close (Esc)
          </button>
        </div>

        <div className={c.dialogBody}>
          {isError ? (
            <div className={c.modalState}>Couldn't load this event.</div>
          ) : images.length === 0 ? (
            <div className={c.modalState}>{isLoading ? 'Loading members…' : 'No members.'}</div>
          ) : (
            <div className={c.thumbGrid}>
              {images.map((m) => (
                <img
                  key={m.owner_id}
                  className={c.thumb}
                  src={memberThumb(m.owner_id)}
                  alt=""
                  loading="lazy"
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
