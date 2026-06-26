import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useRouterState } from '@tanstack/react-router';
import { useEffect } from 'react';
import { ApiError } from '../api/client';
import { getSetupStatus } from '../api/setup';
import * as css from './FirstRunGate.css';

/**
 * First-run gate (Spec F). Polls /api/setup/status once on mount; if the backend
 * reports first_run_needed (no library configured / no admin / weights missing)
 * and we are not already on /setup, redirect to the wizard.
 *
 * Renders a thin error banner (with a "Run setup" link) when the status probe
 * fails so a genuine first-run user is never left with a blank, undirected app.
 * A transient network failure is retried once before the banner shows; a 4xx is
 * surfaced immediately (no point retrying an authoritative error).
 */
export function FirstRunGate() {
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const { data, isError } = useQuery({
    queryKey: ['setup-status'],
    queryFn: ({ signal }) => getSetupStatus(signal),
    // First-run state does not change under the user; one check per load is enough.
    staleTime: Number.POSITIVE_INFINITY,
    // Retry a transient network blip once, but never retry an authoritative 4xx.
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
        return false;
      }
      return failureCount < 1;
    },
  });

  useEffect(() => {
    if (data?.first_run_needed && pathname !== '/setup') {
      navigate({ to: '/setup' });
    }
  }, [data?.first_run_needed, pathname, navigate]);

  if (isError && pathname !== '/setup') {
    return (
      <div className={css.banner} role="alert">
        <span>
          Couldn't reach the backend to check setup. If this is a fresh install, run setup —
          otherwise the server may still be starting; this clears once it responds.
        </span>
        <Link to="/setup" className={css.action}>
          Run setup
        </Link>
      </div>
    );
  }

  return null;
}
