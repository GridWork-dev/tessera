---
title: Tagging & semantic search
description: How Tessera auto-tags, captions, and indexes your library for natural-language and visual-similarity search.
group: Organizing
order: 40
---

Tessera describes every asset for you and indexes it for search. Nothing here
requires manual tagging to get started — the library is browsable and searchable
on day one.

## Auto-tagging

Each asset is run through structured taggers that assign tags across categories:
person, clothing, content type, pose, composition, setting, location, lighting,
mood, rating, and free-form tags. Each tag carries a confidence value, rendered
honestly in the interface — never faked or rounded into decoration.

Tags are data you can filter on. Combine several at once with AND logic to narrow
a large library quickly: `person` plus `setting` plus `rating`, for example.

## Captions

A local vision-language model writes a natural-language caption for each asset.
Captions are full-text indexed, so a keyword in a caption is a search lane of its
own, alongside structured tags.

## Semantic search

Tessera embeds every image into a high-dimensional embedding and searches by
meaning, not filename. Type a description — "golden hour on the beach," "person
in a red coat" — and the nearest matches are ranked by how close the pixels are
to your query.

This is layered, not exclusive:

- **Natural-language queries** search the embedding space and captions.
- **Visual similarity** — pick any asset and find more like it from the image
  embedding directly.
- **Facet filters** — narrow by person, place, rating, or any tag, and combine
  them with a semantic query.

## Keyboard-first workflow

Tessera is built for long curation sessions. A command bar and keyboard shortcuts
are primary affordances: open the command palette, jump between assets, flag
keep/reject, and move through the filmstrip without leaving the keyboard. The grid
and inspector virtualize, so scrolling a large library stays instant.

## What runs where

Tagging, captions, and embeddings are all computed by local models on the compute
backend you chose during [first-run setup](/docs/first-run). None of it leaves
your machine.
