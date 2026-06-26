import {
  Activity,
  Cpu,
  Database,
  EyeOff,
  Flag,
  Gauge,
  HardDrive,
  Image as ImageIcon,
  Layers,
  MemoryStick,
  TriangleAlert,
  Users,
} from 'lucide-react';
import type { ReactNode } from 'react';
import type { DirStat, TierProgress } from '../api/types';
import {
  useCapabilities,
  useCreateExclusion,
  useDirectoryStats,
  useExclusionSuggestions,
  usePipeline,
  useStats,
  useSystem,
  useThroughput,
  useUiPrefs,
} from '../hooks/queries';
import { RATINGS } from '../lib/rating';
import { dashboardModules } from '../modules/registry';
import * as s from '../styles/workspace.css';
import { AppNav } from './AppNav';
import * as c from './Dashboard.css';
import { RatingChip } from './RatingChip';

/* ============================================================================
   Formatters — pure + tiny. Numerics render mono/tabular via the CSS classes.
   ============================================================================ */

const nf = new Intl.NumberFormat('en-US');
const num = (n: number | null | undefined): string => (n == null ? '—' : nf.format(n));
const pct = (n: number | null | undefined): string =>
  n == null ? '—' : `${n >= 99.95 ? 100 : Math.round(n * 10) / 10}%`;
/** Clamp a 0..100 percent to a 0..1 fraction for transform-based fills. */
const frac = (p: number | null | undefined): number =>
  p == null ? 0 : Math.max(0, Math.min(1, p / 100));

function bytes(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  const v = n / 1024 ** i;
  return `${v >= 100 || i === 0 ? Math.round(v) : Math.round(v * 10) / 10} ${units[i]}`;
}

/* ============================================================================
   Shared building blocks
   ============================================================================ */

function ErrorState({ label }: { label: string }) {
  return (
    <div className={c.errorInline} role="status">
      <TriangleAlert size={16} aria-hidden="true" />
      <span>
        {label} — the backend may be offline. Start it with <code>make backend</code> on :8000.
      </span>
    </div>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className={c.stateInline} role="status">
      <span>{label}</span>
    </div>
  );
}

/* Horizontal accent meter (CPU / RAM / disk). `value` is a 0..100 percent. */
function Meter({ value, label }: { value: number | null | undefined; label: string }) {
  return (
    <div
      className={c.meterTrack}
      role="progressbar"
      aria-label={label}
      aria-valuenow={value == null ? undefined : Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={c.meterFill} style={{ transform: `scaleX(${frac(value)})` }} />
    </div>
  );
}

function Section({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={c.section} aria-label={title}>
      <div className={c.sectionHead}>
        <span className={c.sectionTitle}>{title}</span>
        {meta != null && <span className={c.sectionMeta}>{meta}</span>}
      </div>
      <div className={c.panel}>{children}</div>
    </section>
  );
}

/* ============================================================================
   1. Pipeline — four honest tier bars
   ============================================================================ */

function tierDone(t: TierProgress): number {
  return t.processed ?? t.count ?? 0;
}

function TierBar({ label, sub, tier }: { label: string; sub: string; tier: TierProgress }) {
  const done = tierDone(tier);
  const running = tier.running === true;
  return (
    <div className={c.tierRow}>
      <div className={c.tierHead}>
        <span className={c.tierName}>
          <span className={`${c.dot} ${running ? c.dotRunning : c.dotIdle}`} aria-hidden="true" />
          {label}
          {running && <span className={c.runningTag}>running</span>}
        </span>
        <span className={c.tierCounts}>
          <span>
            {num(done)} / {num(tier.total)}
          </span>
          <span className={c.tierPct}>{pct(tier.pct)}</span>
        </span>
      </div>
      <div
        className={c.track}
        role="progressbar"
        aria-label={`${label} — ${sub}`}
        aria-valuenow={Math.round(tier.pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={c.fill} style={{ transform: `scaleX(${frac(tier.pct)})` }} />
      </div>
    </div>
  );
}

function PipelineSection() {
  const { data, isLoading, isError } = usePipeline();
  return (
    <Section
      title="Pipeline"
      meta={data ? `${num(data.total)} assets · all tiers` : 'multi-tier processing'}
    >
      {isError ? (
        <ErrorState label="Couldn't load pipeline status" />
      ) : isLoading && !data ? (
        <LoadingState label="Loading pipeline…" />
      ) : data ? (
        <div className={c.tierList}>
          <TierBar
            label="Tier 0 · tags"
            sub="JoyTag + WD EVA02 → structured tags"
            tier={data.tier0_3}
          />
          <TierBar
            label="Tier 1 · embeddings"
            sub="SigLIP SO400M → vector index"
            tier={data.tier1}
          />
          <TierBar
            label="Tier 2 · captions"
            sub="JoyCaption / Qwen-VL → captions"
            tier={data.tier2}
          />
          <TierBar
            label="Tier 3 · nudenet"
            sub="NudeNet regions (metadata only)"
            tier={data.tier3}
          />
        </div>
      ) : null}
    </Section>
  );
}

/* ============================================================================
   2. System — compact instruments
   ============================================================================ */

function SystemSection() {
  const { data, isLoading, isError } = useSystem();

  const mem = data?.virtual_memory;
  const disk = data?.disk_usage;
  const coreList = data?.per_cpu_percent;
  const load = data?.load_average;
  const gpu = data?.gpu;
  const memUsed = mem
    ? (mem.used ?? (mem.available != null ? mem.total - mem.available : undefined))
    : undefined;

  return (
    <Section title="System" meta="live · 3s">
      {isError ? (
        <ErrorState label="Couldn't load system metrics" />
      ) : isLoading && !data ? (
        <LoadingState label="Loading system metrics…" />
      ) : data ? (
        <div className={c.statGrid}>
          {/* CPU */}
          <div className={c.stat}>
            <div className={c.statHead}>
              <span className={c.statLabel}>
                <Cpu size={13} aria-hidden="true" /> CPU
              </span>
              <span className={c.statValue}>{pct(data.cpu_percent)}</span>
            </div>
            <Meter value={data.cpu_percent} label="CPU utilization" />
            <div className={c.statSub}>{num(data.cpu_count)} cores</div>
            {coreList && coreList.length > 0 && (
              <div className={c.cores} aria-hidden="true">
                {coreList.map((cv, i) => (
                  <span
                    // biome-ignore lint/suspicious/noArrayIndexKey: core index is the identity
                    key={i}
                    className={c.core}
                    style={{ transform: `scaleY(${Math.max(0.04, frac(cv))})` }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Memory */}
          <div className={c.stat}>
            <div className={c.statHead}>
              <span className={c.statLabel}>
                <MemoryStick size={13} aria-hidden="true" /> Memory
              </span>
              <span className={c.statValue}>{pct(mem?.percent)}</span>
            </div>
            <Meter value={mem?.percent} label="Memory utilization" />
            <div className={c.statSub}>
              {bytes(memUsed)} / {bytes(mem?.total)}
            </div>
          </div>

          {/* Disk */}
          <div className={c.stat}>
            <div className={c.statHead}>
              <span className={c.statLabel}>
                <HardDrive size={13} aria-hidden="true" /> Disk
              </span>
              <span className={c.statValue}>{pct(disk?.percent)}</span>
            </div>
            <Meter value={disk?.percent} label="Disk utilization" />
            <div className={c.statSub}>
              {bytes(disk?.free)} free / {bytes(disk?.total)}
            </div>
          </div>

          {/* Load · GPU · tagger */}
          <div className={c.stat}>
            <div className={c.statHead}>
              <span className={c.statLabel}>
                <Gauge size={13} aria-hidden="true" /> Load &amp; devices
              </span>
            </div>
            <div className={c.inlineRows}>
              <div className={c.inlineRow}>
                <span className={c.inlineKey}>Load avg (1/5/15m)</span>
                <span className={c.inlineVal}>
                  {load && load.length >= 3
                    ? `${load[0]?.toFixed(2)} / ${load[1]?.toFixed(2)} / ${load[2]?.toFixed(2)}`
                    : '—'}
                </span>
              </div>
              <div className={c.inlineRow}>
                <span className={c.inlineKey}>
                  <Activity size={13} aria-hidden="true" /> GPU backend
                </span>
                <span className={`${c.statusChip} ${gpu?.available ? c.statusChipOk : ''}`}>
                  {gpu?.available ? (gpu.backend ?? 'available') : 'unavailable'}
                </span>
              </div>
              <div className={c.inlineRow}>
                <span className={c.inlineKey}>Tagger</span>
                <span className={`${c.statusChip} ${data.tagger_running ? c.statusChipOk : ''}`}>
                  <span
                    className={`${c.dot} ${data.tagger_running ? c.dotRunning : c.dotIdle}`}
                    aria-hidden="true"
                  />
                  {data.tagger_running ? 'running' : 'idle'}
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </Section>
  );
}

/* ============================================================================
   3. Corpus — totals + recent import rate
   ============================================================================ */

function CorpusSection() {
  const stats = useStats();
  const tput = useThroughput();
  const s = stats.data;

  return (
    <Section title="Corpus" meta="source-of-truth library">
      {stats.isError ? (
        <ErrorState label="Couldn't load corpus stats" />
      ) : stats.isLoading && !s ? (
        <LoadingState label="Loading corpus stats…" />
      ) : s ? (
        <>
          <div className={c.summaryRow}>
            <div className={c.summaryItem}>
              <span className={c.summaryNum}>{num(s.total_images)}</span>
              <span className={c.summaryLabel}>
                <ImageIcon size={11} aria-hidden="true" /> total assets
              </span>
            </div>
            <div className={c.summaryItem}>
              <span className={c.summaryNum}>{pct(s.processing_pct)}</span>
              <span className={c.summaryLabel}>
                <Layers size={11} aria-hidden="true" /> processed ({num(s.processed_images)})
              </span>
            </div>
            <div className={c.summaryItem}>
              <span className={c.summaryNum}>{num(s.flagged_count)}</span>
              <span className={c.summaryLabel}>
                <Flag size={11} aria-hidden="true" /> flagged
              </span>
            </div>
            <div className={c.summaryItem}>
              <span className={c.summaryNum}>{num(s.people_count)}</span>
              <span className={c.summaryLabel}>
                <Users size={11} aria-hidden="true" /> people
              </span>
            </div>
            <div className={c.summaryItem}>
              <span className={c.summaryNum}>{num(s.tag_categories)}</span>
              <span className={c.summaryLabel}>
                <Database size={11} aria-hidden="true" /> tag categories
              </span>
            </div>
          </div>
          <div className={c.throughput}>
            <span className={c.throughputNum}>
              {tput.isError ? '—' : tput.data ? num(Math.round(tput.data.per_minute)) : '…'}
            </span>
            <span className={c.throughputUnit}>recent imports/min</span>
            {tput.data && (
              <span className={c.throughputMeta}>
                {num(tput.data.count)} in last {num(tput.data.window_minutes)}m
              </span>
            )}
          </div>
        </>
      ) : null}
    </Section>
  );
}

/* ============================================================================
   4. Breakdown — by-person table
   ============================================================================ */

function RatingDots({ ratings }: { ratings: Record<string, number> }) {
  const present = RATINGS.filter((r) => (ratings[r] ?? 0) > 0);
  if (present.length === 0) return <span className={c.tdMuted}>—</span>;
  return (
    <span className={c.ratingCell}>
      {present.map((r) => (
        // Rating shown as color + visible label (RatingChip), never color alone,
        // per the accessibility principle. Count sits beside it in mono.
        <span key={r} className={c.ratingPair}>
          <RatingChip rating={r} />
          <span className={c.ratingPairCount}>{num(ratings[r])}</span>
        </span>
      ))}
    </span>
  );
}

function PersonRow({ d }: { d: DirStat }) {
  const procPct = d.image_count > 0 ? (d.processed_count / d.image_count) * 100 : 0;
  return (
    <tr>
      <td className={`${c.td} ${c.tdKey}`}>{d.key || 'unassigned'}</td>
      <td className={`${c.td} ${c.tdNum}`}>{num(d.image_count)}</td>
      <td className={`${c.td} ${c.tdNum}`}>
        {num(d.processed_count)} · {pct(procPct)}
      </td>
      <td className={`${c.td} ${d.flagged_count > 0 ? c.tdNum : c.tdMuted}`}>
        {num(d.flagged_count)}
      </td>
      <td className={c.td}>
        <RatingDots ratings={d.ratings} />
      </td>
    </tr>
  );
}

function BreakdownSection() {
  const { data, isLoading, isError } = useDirectoryStats();
  const people = data?.by_person ?? [];

  return (
    <Section title="By person" meta={data ? `${num(people.length)} people` : 'distribution'}>
      {isError ? (
        <ErrorState label="Couldn't load breakdown" />
      ) : isLoading && !data ? (
        <LoadingState label="Loading breakdown…" />
      ) : people.length === 0 ? (
        <LoadingState label="No people attributed yet." />
      ) : (
        <div className={c.tableScroll}>
          <table className={c.table}>
            <thead>
              <tr>
                <th className={c.th}>Person</th>
                <th className={`${c.th} ${c.thNum}`}>Images</th>
                <th className={`${c.th} ${c.thNum}`}>Processed</th>
                <th className={`${c.th} ${c.thNum}`}>Flagged</th>
                <th className={`${c.th} ${c.thNum}`}>Ratings</th>
              </tr>
            </thead>
            <tbody>
              {people.map((d) => (
                <PersonRow key={d.key} d={d} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

/* ============================================================================
   Dashboard root
   ============================================================================ */

/* ============================================================================
   5. Hide suggestions — mined from the operator's rejects (no H100)
   ============================================================================ */

function SuggestionsSection() {
  const { data, isLoading, isError } = useExclusionSuggestions(3);
  const create = useCreateExclusion();
  const candidates = data?.candidates ?? [];
  const reasons = data?.reasons ?? [];

  return (
    <Section
      title="Hide suggestions"
      meta={data ? `from ${num(data.reject_count)} rejected` : 'mined from rejects'}
    >
      {isError ? (
        <ErrorState label="Couldn't load suggestions" />
      ) : isLoading && !data ? (
        <LoadingState label="Mining rejects…" />
      ) : candidates.length === 0 ? (
        <LoadingState label="No hide suggestions yet — reject items in Training to surface recurring junk." />
      ) : (
        <>
          <div className={c.suggestList}>
            {candidates.map((cand) => (
              <div key={`${cand.category}:${cand.value}`} className={c.suggestRow}>
                <span className={c.suggestTag}>
                  <span className={c.suggestCat}>{cand.category}</span>
                  {cand.value}
                </span>
                <span className={c.suggestCount}>{num(cand.reject_count)} rejects</span>
                <button
                  type="button"
                  className={c.hideBtn}
                  onClick={() => create.mutate({ category: cand.category, value: cand.value })}
                  disabled={create.isPending}
                >
                  <EyeOff size={13} aria-hidden="true" />
                  Hide
                </button>
              </div>
            ))}
          </div>
          {reasons.length > 0 && (
            <div className={c.reasonChips}>
              {reasons.map((r) => (
                <span key={r.value} className={c.reasonChip}>
                  {r.value}
                  <span className={c.suggestCount}>{num(r.count)}</span>
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </Section>
  );
}

/** Dashboard cards keyed by their registry module id (surface 'dashboard'). The
 *  Dashboard renders them in the order/visibility dashboardModules() resolves
 *  from ui.dashboard prefs — one source for the cards + the Settings customizer. */
const DASH_CARDS: Record<string, () => ReactNode> = {
  'dash-pipeline': () => <PipelineSection />,
  'dash-system': () => <SystemSection />,
  'dash-corpus': () => <CorpusSection />,
  'dash-suggestions': () => <SuggestionsSection />,
  'dash-breakdown': () => <BreakdownSection />,
};

export function Dashboard() {
  const caps = useCapabilities();
  const prefs = useUiPrefs();
  // Order/hide from ui.dashboard; unknown/new cards fall back to registry order.
  const cards = dashboardModules(prefs.data?.ui.dashboard, caps.data).filter(
    (m) => m.id in DASH_CARDS,
  );
  return (
    <div className={s.appFrame}>
      <header className={s.commandBar}>
        <AppNav />
        <span className={s.pageTitle}>Dashboard</span>
        <span className={s.barSpacer} />
        <span className={s.pageMeta}>live monitoring</span>
      </header>

      <div className={c.scroll}>
        <div className={c.inner}>
          {cards.map((m) => (
            <div key={m.id}>{DASH_CARDS[m.id]?.()}</div>
          ))}
        </div>
      </div>
    </div>
  );
}
