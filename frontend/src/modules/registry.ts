import {
  Activity,
  CalendarRange,
  Cpu,
  Crosshair,
  Database,
  EyeOff,
  Film,
  Images,
  Layers,
  LayoutDashboard,
  MapPin,
  Settings,
  Sparkles,
  UserRound,
} from 'lucide-react';
import type { ComponentType } from 'react';

export type NavPath =
  | '/'
  | '/dashboard'
  | '/training'
  | '/videos'
  | '/people'
  | '/places'
  | '/events'
  | '/learn'
  | '/settings';

export type ModuleSurface = 'nav' | 'dashboard' | 'both';
export type CapabilityGate = 'faces' | 'geo' | 'video' | 'license';

export interface ModuleDef {
  id: string;
  label: string;
  icon: ComponentType<{ size?: number }>;
  route?: NavPath;
  surface: ModuleSurface;
  defaultEnabled: boolean;
  defaultOrder: number;
  gate?: CapabilityGate;
}

/** Single source for nav + dashboard. `gate` is the SERVER capability key
 * (enforced only when capabilities are passed to navModules), distinct from
 * user visibility (prefs.hidden). Order/labels reproduce today's AppNav. */
export const MODULES: readonly ModuleDef[] = [
  {
    id: 'grid',
    label: 'Grid',
    icon: Images,
    route: '/',
    surface: 'nav',
    defaultEnabled: true,
    defaultOrder: 0,
  },
  {
    id: 'videos',
    label: 'Videos',
    icon: Film,
    route: '/videos',
    surface: 'nav',
    defaultEnabled: true,
    defaultOrder: 1,
    gate: 'video',
  },
  {
    id: 'people',
    label: 'People',
    icon: UserRound,
    route: '/people',
    surface: 'nav',
    defaultEnabled: true,
    defaultOrder: 2,
    gate: 'faces',
  },
  {
    id: 'places',
    label: 'Places',
    icon: MapPin,
    route: '/places',
    surface: 'nav',
    defaultEnabled: true,
    defaultOrder: 3,
    gate: 'geo',
  },
  {
    id: 'events',
    label: 'Events',
    icon: CalendarRange,
    route: '/events',
    surface: 'nav',
    defaultEnabled: true,
    defaultOrder: 4,
    gate: 'geo',
  },
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: LayoutDashboard,
    route: '/dashboard',
    surface: 'both',
    defaultEnabled: true,
    defaultOrder: 5,
  },
  {
    id: 'training',
    label: 'Training',
    icon: Crosshair,
    route: '/training',
    surface: 'nav',
    defaultEnabled: true,
    defaultOrder: 6,
  },
  {
    id: 'personalize',
    label: 'Personalize',
    icon: Sparkles,
    route: '/learn',
    surface: 'nav',
    defaultEnabled: true,
    defaultOrder: 7,
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: Settings,
    route: '/settings',
    surface: 'nav',
    defaultEnabled: true,
    defaultOrder: 8,
  },

  // Dashboard cards (surface 'dashboard' — never in nav). Reorder/hide via
  // ui.dashboard prefs; the Dashboard renders these from dashboardModules().
  {
    id: 'dash-pipeline',
    label: 'Pipeline',
    icon: Activity,
    surface: 'dashboard',
    defaultEnabled: true,
    defaultOrder: 10,
  },
  {
    id: 'dash-system',
    label: 'System',
    icon: Cpu,
    surface: 'dashboard',
    defaultEnabled: true,
    defaultOrder: 11,
  },
  {
    id: 'dash-corpus',
    label: 'Corpus',
    icon: Database,
    surface: 'dashboard',
    defaultEnabled: true,
    defaultOrder: 12,
  },
  {
    id: 'dash-suggestions',
    label: 'Suggestions',
    icon: EyeOff,
    surface: 'dashboard',
    defaultEnabled: true,
    defaultOrder: 13,
  },
  {
    id: 'dash-breakdown',
    label: 'Breakdown',
    icon: Layers,
    surface: 'dashboard',
    defaultEnabled: true,
    defaultOrder: 14,
  },
];

export interface NavPrefs {
  order?: string[];
  hidden?: string[];
}

/** Ordered, visible nav modules given optional user prefs + server caps.
 * No args => all nav modules in defaultOrder (today's behavior, unchanged). */
export function navModules(
  prefs?: NavPrefs,
  caps?: Partial<Record<CapabilityGate, boolean>>,
): ModuleDef[] {
  const hidden = new Set(prefs?.hidden ?? []);
  const order = prefs?.order ?? [];
  const rank = (id: string) => {
    const i = order.indexOf(id);
    return i === -1 ? Number.POSITIVE_INFINITY : i;
  };
  return MODULES.filter((m) => m.surface === 'nav' || m.surface === 'both')
    .filter((m) => !m.gate || caps?.[m.gate] !== false)
    .filter((m) => !hidden.has(m.id))
    .sort((a, b) => rank(a.id) - rank(b.id) || a.defaultOrder - b.defaultOrder);
}

/** Ordered, visible DASHBOARD cards given optional user prefs + server caps.
 *  Same two-axis model as navModules: server gates first, then user order/hidden.
 *  surface 'dashboard' | 'both'. No args => all dashboard modules in defaultOrder. */
export function dashboardModules(
  prefs?: NavPrefs,
  caps?: Partial<Record<CapabilityGate, boolean>>,
): ModuleDef[] {
  const hidden = new Set(prefs?.hidden ?? []);
  const order = prefs?.order ?? [];
  const rank = (id: string) => {
    const i = order.indexOf(id);
    return i === -1 ? Number.POSITIVE_INFINITY : i;
  };
  return MODULES.filter((m) => m.surface === 'dashboard' || m.surface === 'both')
    .filter((m) => !m.gate || caps?.[m.gate] !== false)
    .filter((m) => !hidden.has(m.id))
    .sort((a, b) => rank(a.id) - rank(b.id) || a.defaultOrder - b.defaultOrder);
}
