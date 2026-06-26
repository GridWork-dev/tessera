import { createFileRoute } from '@tanstack/react-router';
import { PlacesView } from '../components/PlacesView';

export const Route = createFileRoute('/places')({
  component: PlacesView,
});
