import { createFileRoute } from '@tanstack/react-router';
import { ActiveLearningPanel } from '../components/ActiveLearningPanel';
import { AppNav } from '../components/AppNav';
import * as s from '../styles/workspace.css';

/**
 * Personalize — active-learning surface (rungs 1-2: linear probe + active
 * learning over keep/reject signals). ActiveLearningPanel is content-only, so
 * this route supplies the shared app frame (command bar + nav), mirroring the
 * other full-page surfaces.
 */
function LearnPage() {
  return (
    <div className={s.appFrame}>
      <header className={s.commandBar}>
        <AppNav />
        <span className={s.pageTitle}>Personalize</span>
        <span className={s.barSpacer} />
      </header>
      {/* Content-only surface: render the scroll region directly under the app
          frame (it is flex:1 1 auto) so it fills the full width. The `body` rail
          grid expects a rail + content pair; with one child the content would
          otherwise be stranded in the fixed 280px first track. */}
      <div className={s.gridRegion}>
        <ActiveLearningPanel />
      </div>
    </div>
  );
}

export const Route = createFileRoute('/learn')({ component: LearnPage });
