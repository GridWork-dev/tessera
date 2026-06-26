import { useEffect, useState } from 'react';

/**
 * Subscribe to a CSS media query and re-render on change. SSR/headless-safe
 * (returns false until mounted). Used to branch interaction behaviour that CSS
 * alone can't express — e.g. routing a tile tap to the lightbox on viewports
 * where the docked inspector is hidden.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && 'matchMedia' in window
      ? window.matchMedia(query).matches
      : false,
  );

  useEffect(() => {
    if (typeof window === 'undefined' || !('matchMedia' in window)) return;
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}
