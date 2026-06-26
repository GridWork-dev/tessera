import { createFileRoute } from '@tanstack/react-router';
import { TrainingMode } from '../components/TrainingMode';

export const Route = createFileRoute('/training')({
  component: TrainingMode,
});
