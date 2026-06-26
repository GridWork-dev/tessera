import { RotateCcw, TriangleAlert } from 'lucide-react';
import { Component, type ErrorInfo, type ReactNode } from 'react';
import * as c from './ErrorBoundary.css';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Top-level error boundary. A single uncaught render error would otherwise
 * unmount the whole SPA to a blank screen — with no dev overlay in the packaged
 * Tauri app to explain it. This catches the throw and renders a calm, recoverable
 * fallback (Reload) plus the error text in a collapsible block for diagnosis.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface to the console so it is captured in the app log / devtools.
    console.error('Unhandled render error:', error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className={c.wrap} role="alert">
        <TriangleAlert size={40} aria-hidden="true" className={c.icon} />
        <h1 className={c.title}>Something went wrong</h1>
        <p className={c.message}>
          Tessera hit an unexpected error and couldn't render this view. Your library is untouched —
          reloading usually clears it.
        </p>
        <div className={c.actions}>
          <button type="button" className={c.reloadBtn} onClick={() => window.location.reload()}>
            <RotateCcw size={16} aria-hidden="true" />
            Reload
          </button>
        </div>
        <details className={c.details}>
          <summary className={c.summary}>Error details</summary>
          <pre className={c.trace}>{error.stack ?? error.message}</pre>
        </details>
      </div>
    );
  }
}
