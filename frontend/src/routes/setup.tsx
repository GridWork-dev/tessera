import { createFileRoute } from '@tanstack/react-router';
import { SetupWizard } from '../components/SetupWizard';

/**
 * First-run setup wizard route (Spec F). A standalone full-viewport surface (no
 * app chrome) — the SetupWizard owns the whole screen and navigates home on
 * finish. Reachable directly at /setup; the first-run gate (FirstRunGate) sends
 * new users here when /api/setup/status reports first_run_needed.
 */
export const Route = createFileRoute('/setup')({ component: SetupWizard });
