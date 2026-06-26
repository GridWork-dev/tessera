// Docs content collection (Astro 5 — glob loader, src/content.config.ts).
// Each markdown file under src/content/docs/ is one page rendered at
// /docs/<slug>. `group` buckets the sidebar; `order` sorts within a group
// and across groups (low first).
import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const docs = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/docs" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    group: z.string(),
    order: z.number(),
  }),
});

export const collections = { docs };
