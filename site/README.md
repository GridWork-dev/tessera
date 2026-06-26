# Tessera marketing site

Static [Astro](https://astro.build) site for Tessera, the private, local AI media
library. Self-contained — its own `package.json`, independent of the app build.

## Design

Mirrors the app's **Pigment** design system (see repo `DESIGN.md`): dark-only,
near-black surface ramp (void `#0a0b0d`), 4pt spacing, radii 8/9/12/16,
**Schibsted Grotesk** as the only typeface (self-hosted via
`@fontsource-variable/schibsted-grotesk`), one restrained jade accent (`#2fd6a0`).
Icons are **Lucide only** (`astro-icon` + `@iconify-json/lucide`). No emoji anywhere.

## Configure

Every brand/external value lives in [`src/config.ts`](src/config.ts):
`SITE_NAME`, `GITHUB_URL`, `RELEASES_URL`, `DISCUSSIONS_URL`, `POLAR_CHECKOUT_URL`
(placeholder `#`), `PRICE_PRO`, and contact emails (`admin@gettessera.xyz`).
Rebrand by editing `SITE_NAME` once.

## Contact form (Cloudflare Pages Function)

`functions/api/contact.ts` handles the contact-form POST: verifies Cloudflare
Turnstile, then sends a notification + branded auto-reply via Resend. It needs three
environment variables set in the Cloudflare Pages project (never commit secrets):

- `TURNSTILE_SECRET` — Cloudflare Turnstile secret key
- `RESEND_API_KEY` — Resend API key
- `CONTACT_TO` (optional) — override the notification recipient (defaults to `admin@gettessera.xyz`)

The contact page also needs the Turnstile **site** key — replace the
`data-sitekey` placeholder in `src/pages/contact.astro`.

## Develop

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # static output -> dist/
npm run preview  # serve the build locally
```

Deploy target: Cloudflare Pages (build command `npm run build`, output `dist/`).

## Deferred (impeccable build phase)

Final pixel polish, motion / micro-interactions, responsive fine-tuning, real
screenshots, and the Remotion demo video. The `VideoEmbed` and `.shot` placeholders are
swappable in place once those assets exist.
