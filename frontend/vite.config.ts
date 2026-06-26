// NOTE: @rolldown/plugin-babel@0.2.3 exports the plugin as a DEFAULT export
// (the recipe's `import { babel } from ...` named form is wrong for this version).
import babel from '@rolldown/plugin-babel';
import { tanstackRouter } from '@tanstack/router-plugin/vite';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';
import react, { reactCompilerPreset } from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    // 1. TanStack Router MUST come before plugin-react's react(),
    //    or the build throws "plugin-react was passed before @tanstack/router-plugin".
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    // 2. React (Oxc).
    react(),
    // 3. React Compiler via Babel — OFFICIAL plugin-react v6 form:
    //    react() FIRST, then babel({ presets: [reactCompilerPreset()] }).
    babel({ presets: [reactCompilerPreset()] }),
    // 4. vanilla-extract.
    vanillaExtractPlugin(),
    // 5. Visualizer LAST, env-gated: ANALYZE=1 npm run build
    process.env.ANALYZE
      ? visualizer({
          filename: 'dist/stats.html',
          template: 'treemap',
          gzipSize: true,
          brotliSize: true,
          open: false,
        })
      : undefined,
  ].filter(Boolean),
  server: {
    // Dev: proxy backend routes to FastAPI on :8000 so the client uses relative
    // paths (which also work in prod, where the backend serves the built SPA).
    proxy: {
      '/api': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
      '/image-content': 'http://localhost:8000',
    },
  },
  build: {
    rollupOptions: {
      output: {
        // FUNCTION form. NEVER bucket your own app modules (breaks Router's
        // route code-splitting + risks circular-chunk init errors, vitejs/vite#12209).
        manualChunks(id) {
          if (!id.includes('node_modules')) return; // let Vite/Router decide
          if (id.includes('react') || id.includes('scheduler')) return 'react';
          if (id.includes('@tanstack')) return 'tanstack';
          if (id.includes('radix-ui')) return 'radix';
          if (id.includes('zustand')) return 'state';
          return 'vendor';
        },
      },
    },
  },
});
