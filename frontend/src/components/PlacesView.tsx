import { useQuery } from '@tanstack/react-query';
import { MapPin } from 'lucide-react';
import { listPlaces, type Place } from '../api/geo';
import * as s from '../styles/workspace.css';
import { AppNav } from './AppNav';
import * as c from './PlacesView.css';

/** Country-code → label is intentionally not localized — show the cc as data. */
function placeRegion(p: Place): string {
  const parts = [p.admin1, p.cc].filter((x): x is string => Boolean(x));
  return parts.length ? parts.join(' · ') : 'Unknown region';
}

export function PlacesView() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['geo', 'places'],
    queryFn: ({ signal }) => listPlaces(signal),
    staleTime: 60_000,
    retry: false,
  });

  const places = data ?? [];
  const total = places.reduce((n, p) => n + p.image_count, 0);

  return (
    <div className={s.appFrame}>
      <header className={s.commandBar}>
        <AppNav />
        <span className={s.pageTitle}>Places</span>
        <span className={s.barSpacer} />
        <span className={s.pageMeta}>
          {isLoading ? 'loading…' : `${places.length.toLocaleString()} places`}
        </span>
      </header>

      <div className={s.gridRegion}>
        {isError ? (
          <div className={s.stateWrap}>
            <MapPin size={28} aria-hidden="true" />
            <span className={s.stateTitle}>Couldn't load places</span>
            <span className={s.stateHint}>
              The backend may be offline. Start it with{' '}
              <code className={c.codeInline}>make backend</code> on :8000.
            </span>
          </div>
        ) : places.length === 0 ? (
          <div className={s.stateWrap}>
            <MapPin size={28} aria-hidden="true" />
            <span className={s.stateTitle}>{isLoading ? 'Loading…' : 'No places yet'}</span>
            <span className={s.stateHint}>
              Places appear once the geo backfill reverse-geocodes images with GPS — run{' '}
              <code className={c.codeInline}>POST /api/geo/backfill</code> (stage{' '}
              <code className={c.codeInline}>places</code>).
            </span>
          </div>
        ) : (
          <div className={c.pad}>
            <div className={c.countNote}>
              {total.toLocaleString()} located image{total === 1 ? '' : 's'} across{' '}
              {places.length.toLocaleString()} place{places.length === 1 ? '' : 's'}
            </div>
            <div className={c.grid}>
              {places.map((p) => (
                <div key={p.id} className={c.card}>
                  <span className={c.cardIcon} aria-hidden="true">
                    <MapPin size={16} />
                  </span>
                  <span className={c.cardText}>
                    <span className={c.cardName} title={p.name}>
                      {p.name || `Place #${p.id}`}
                    </span>
                    <span className={c.cardRegion}>{placeRegion(p)}</span>
                  </span>
                  <span className={c.cardCount}>{p.image_count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
