// @ts-check
import { defineConfig } from "astro/config";
import icon from "astro-icon";
import sitemap from "@astrojs/sitemap";

// https://astro.build/config
export default defineConfig({
  // Production origin — anchors absolute canonical + OG/Twitter image URLs.
  site: "https://gettessera.xyz",
  output: "static",
  integrations: [icon({ iconDir: "src/icons" }), sitemap()],
  // The site ships no astro:assets-processed images (downloads/OG are static
  // files + inline SVG), so use the no-op passthrough image service. This avoids
  // pulling in the optional `sharp` native dependency, which the content
  // collection's render pipeline would otherwise require at build time.
  image: { service: { entrypoint: "astro/assets/services/noop" } },
});
