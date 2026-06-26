// @fontsource-variable/* packages are CSS-only side-effect imports (they inject
// @font-face rules). They ship no type declarations, so under strict TS
// (verbatimModuleSyntax + bundler resolution) the bare import errors with TS2882.
// Declare them as ambient modules; Vite handles the actual CSS at build time.
declare module '@fontsource-variable/schibsted-grotesk';
