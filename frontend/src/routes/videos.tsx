import { createFileRoute } from '@tanstack/react-router';
import { VideosView } from '../components/VideosView';

export const Route = createFileRoute('/videos')({
  component: VideosView,
});
