import { createFileRoute } from '@tanstack/react-router';
import { PeopleView } from '../components/PeopleView';

export const Route = createFileRoute('/people')({
  component: PeopleView,
});
