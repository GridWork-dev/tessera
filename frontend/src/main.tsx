// Self-hosted variable font (no external CDN — local-first / privacy).
// Schibsted Grotesk is the single UI typeface; numerics use the same family
// rendered tabular (font-variant-numeric), so there's one font across the app.
import '@fontsource-variable/schibsted-grotesk';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createRouter, RouterProvider } from '@tanstack/react-router';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ErrorBoundary } from './components/ErrorBoundary';
import { routeTree } from './routeTree.gen';
import { applyTheme, getStoredTheme } from './styles/themeStore';

// Apply the persisted (or default Pigment) theme on <html> BEFORE first paint
// so token vars resolve everywhere, including portaled content.
applyTheme(getStoredTheme());

const queryClient = new QueryClient();

const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: 'intent',
  // Let TanStack Query own staleness; Router just triggers the preload.
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found');
}

createRoot(rootElement).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
