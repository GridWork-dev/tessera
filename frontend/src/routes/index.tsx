import { createFileRoute } from '@tanstack/react-router';
import { Browse } from '../components/Browse';

export const Route = createFileRoute('/')({
  component: Browse,
});
