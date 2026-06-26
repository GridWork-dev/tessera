/** The Pigment tessera mark — a jade tile split on the diagonal (one facet).
 *  Fill is currentColor (= accent) so the mark re-themes; the facet line is
 *  translucent black so it reads on any theme's accent. Shared across the nav
 *  wordmark and the first-run setup header. */
export function BrandFacet({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5" fill="currentColor" />
      <path d="M3 8.5 21 15.5" stroke="rgba(0,0,0,0.45)" strokeWidth="1.3" />
    </svg>
  );
}
