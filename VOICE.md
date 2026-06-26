# Voice

> Microcopy + register guide for Tessera (app UI + marketing site).
> Source of truth for the copy pass. Codifies the voice already in the code —
> don't invent a new one. Read alongside `PRODUCT.md` (register) + `DESIGN.md`.
> Terse, imperative, example-led. No emoji, no hype.

Register: **precise, quiet, fast.** A pro instrument for one power user. The chrome
recedes; copy is chrome. Say the true thing in the fewest words and stop.

## Voice principles

1. **Terse over polite.** One clause, sentence case, no filler. The user is fast; respect it.
   - Do: `Run clustering` · `Clear all filters` · `Save current view…`
   - Don't: `Click here to run the clustering process now`

2. **Honest, never hype.** State what is, including limits and failures. No celebration, no superlatives.
   - Do: `First run downloads ~3.5 GB of models, then works fully offline.`
   - Don't: `Blazing-fast AI magic — instantly understands your whole library!`

3. **Empty + error states name the cause and the fix.** Never a dead end; never blame the user.
   - Do: `No matching assets` + `Adjust or clear the filters in the left rail.`
   - Don't: `Oops! Nothing here 😕`

4. **Numbers are data, rendered plainly.** Counts, confidences, dimensions are real and tabular — never rounded for flattery, never decorated.
   - Do: `26,590 images` · `Tier 0 · tags`
   - Don't: `Thousands of photos analyzed!`

5. **Privacy stated as architecture, not promise.** Frame local-first as a property of the system.
   - Do: `Private by architecture, not by promise.` · `Three steps. No cloud in any of them.`
   - Don't: `We take your privacy seriously and will never misuse your data.`

6. **Plain words, light contractions.** `Couldn't`, `It's`, `you'll` are fine. No jargon the schema doesn't use; no marketing register inside the app.
   - Do: `Couldn't load faces for this person.`
   - Don't: `Face-retrieval subsystem returned a non-200 response.`

## Microcopy patterns

**Buttons / actions** — imperative verb, sentence case, no trailing period. Trailing `…` only when it opens further input or a dialog.
- `Run clustering` · `Clear all filters` · `Merge into` · `Split into a new person` · `Save current view…`

**Section labels** — short noun, sentence case in chrome; uppercase (label token, `.06em`) only for the tracked facet/category headers. Never a verb.
- `Dashboard cards` · `Accent color` · `Keyboard shortcuts` · `Label sets`

**Empty states** — `<flat statement of nothing>` + one-line next step. State the cause when it's a pipeline stage.
- `No matching assets` → `Adjust or clear the filters in the left rail.`
- `No tags yet — runs after the Tier-0 tag pass.`
- `No people attributed yet.` · `No similar items.` · `No selection`

**Errors / toasts** — `Couldn't <verb> <thing>.` for failures (plain, no error codes, no blame). Past-tense fragment for completed actions. Match the in-app calm; no exclamation.
- `Couldn't load assets` · `Couldn't load videos` · `Clustering failed.`
- `Download started.` · `Queue clear`

**In-progress** — present participle + `…`. Name the specific work, not a generic spinner word.
- `Loading…` · `Finding similar…` · `Mining rejects…` · `Detecting hardware…` · `Checking license…`

**Tooltips / aria-labels** — name the action or element; append the shortcut in parens when one exists. Sentence case, no period.
- `Close (Esc)` · `Next (→)` · `Toggle grid density` · `Split face into a new person`

**Placeholders** — show the shape of the expected input, not an instruction.
- `/path/to/your/library` · `Add a label…` · `Paste your license token (MPL-…) or drop a license.key file`

**Confirmations (destructive)** — state the irreversible effect in the body; the confirm button repeats the verb (never `OK`/`Yes`). Pair with the destructive tokens (`negBg`/`negLine`), never color alone.
- Title: `Reject 12 assets?` · Body: `They move to the reject queue. You can restore them later.` · Confirm: `Reject`

## Glossary

Canonical term on the left; banned synonyms on the right. Two terms are kept where they
mean genuinely different things — those are flagged, not collapsed.

| Use | Not | Why |
|---|---|---|
| **library** | collection, database, catalog (in UI), gallery | The whole local set of assets. `catalog.db` is the file; "library" is the user-facing whole. |
| **asset** | image, photo, media, file (as the generic unit) | Covers images **and** videos. Use the generic "asset" when type doesn't matter. |
| **image** / **video** | — (both valid) | The two concrete `media_type`s. Use the specific word only when type matters; otherwise "asset". |
| **tags** | keywords, attributes | Model-emitted structured tags (Tier 0: JoyTag + WD EVA02). Machine-written. |
| **labels** | tags (when user-defined), categories | User-defined `label_sets` the user assigns by hand. **Distinct from tags** — keep both; never call a label a tag or vice versa. |
| **rating** | label (when meaning the rating), flag, score | The one single-select label set (`sfw` / `suggestive` / `nsfw` / `unrated`). It is a label set, but always call it "rating". |
| **person** | subject, model, individual | A named subject in the library. |
| **face cluster** | group, batch, bucket | Unnamed agglomerated faces before they're attributed to a person. Distinct from "person". |
| **place** | location (in UI), geo, region | Geo-derived grouping (`place`). |
| **event** | session, shoot, batch | Time-derived grouping (`event`). Distinct from "place". |
| **caption** | description, summary | Free-text VLM caption (Tier 2). |
| **embedding** | vector (in UI), feature | SigLIP image vector (Tier 1). Say "embeddings" in chrome; "vector index" is fine for the index itself. |
| **flag** / **reject** / **maybe** / **keep** | delete, trash, archive | Triage actions (`flag_action`). "Reject" routes to the reject queue; nothing is deleted. |
| **Pro** | premium, paid, upgrade, plus | The paid edition. Capitalized. The free edition is **Free** (AGPLv3 open core). |
| **Free** | community, lite, basic, trial | The open-core edition. Not a downgrade — "Free forever. Pro once, if you want more." |
| **Tessera** | the app, the tool, MediaPipeline | Product name. The mark is the **Facet** tessera. |

Tier names are canonical and ordered: `Tier 0 · tags`, `Tier 1 · embeddings`, `Tier 2 · captions`, `Tier 3 · nudenet`. NudeNet output is **metadata**, never a gate — never imply it filters or blocks.
