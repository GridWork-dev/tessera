# ADR 0005 — Self-retrieval gate authorizes text2image

Status: Proposed (plan-only). Date: 2026-06-23.
Bucket: A. AI search & discovery. Effort: S.

## Context / problem

`text2image` is the flagship search capability. Its body in
`webui/search.py` is already wired: `run_search()` (line 280) gates the mode on
`TEXT2IMAGE_GATE_PASSED and vectors_ok and can_embed_text`, and
`TEXT2IMAGE_GATE_PASSED` is read from an env var (line 53). Today it is `0`, so
text2image always degrades to tag relevance.

The load-bearing risk is the SigLIP checkpoint identity. SigLIP SO400M is a
**dual encoder** — text and image share one 1152-dim space — but only if the
weights are the HF `SiglipModel`. A *timm vision-only* checkpoint produces
1152-dim image vectors that are correct for image-to-image (find-similar) yet
**semantically meaningless for text queries** (`knowledge/vendors/siglip-quirks.md`
lines 7-11; HF docs confirm `get_image_features` delegates to `self.vision_model`
and that the text tower lives only in `SiglipModel`, ref
https://huggingface.co/docs/transformers/en/model_doc/siglip).

`scripts/validate_h100_parity.py::validate_tier1` (lines 167-215) **cannot catch
this**. It recomputes each pilot id locally with the *same*
`Tier1Embedder` (line 183) and asserts cosine > 0.9999 vs the remote vector. If
the H100 ran a vision-only checkpoint, the local re-embed would load the same
wrong checkpoint — both sides equally poisoned, parity PASSES, text2image ships
broken. Parity proves *the box computed what we asked*; it does not prove *what
we asked is the dual-encoder*.

The self-retrieval check (`outputs/research/04-search-ui-scale.md` §2.4;
`docs/roadmap-platform-2026.md:58`) is the missing, **net-new** verification: it
proves the stored vectors form a coherent self-consistent metric space. It is
implemented NOWHERE — it is a new artifact, not the env-flag flip the flag's
presence might suggest. This ADR pins it as the sole authorization for flipping
`TEXT2IMAGE_GATE_PASSED=1`.

A subtlety to record honestly: a pure self-retrieval check (image re-embedded →
nearest neighbor is itself) is satisfied by ANY deterministic embedder,
**including a vision-only one**. Self-retrieval is necessary but, alone, does
*not* prove cross-modal validity. This ADR therefore mandates self-retrieval as
the **GATE 0 / image-space sanity** check, and explicitly defers the
**cross-modal** proof (a text query retrieving the right images) to ADR-0006's
text-tower work as GATE 1. The two gates compose; neither alone authorizes
shipping text2image. find-similar (image→image only) needs GATE 0 only.

## Decision

1. **Add a self-retrieval verifier** (`scripts/verify_self_retrieval.py`, new)
   that, for a fixed set of ~10-20 known image ids:
   - re-embeds each image **locally on MPS** via `Tier1Embedder.embed_image`
     (`pipeline/tier1_embedder.py:228`) — same `get_image_features().pooler_output`,
     L2-normalized;
   - queries `vec_siglip_1152` (the H100-populated store) for that re-embedded
     vector's top neighbor via the existing `_vec_rescore` path;
   - asserts the top neighbor's `image_id == id` AND cosine similarity > 0.99.
   - Emits a JSON report (mirroring `validate_h100_parity.py`'s shape) +
     exit 0/1.
2. **Reuse the existing probe set.** `data/validation/tier1_ids.json` already
   holds 10 known ids `[56,57,58,63,477,479,13791,13792,13793,13794]` from the
   e2e baseline. Use these (optionally widen to ~20). No new fixture, no library
   path exposure.
3. **Gate semantics (GATE 0, image space).** This gate authorizes ONLY:
   that `vec_siglip_1152` is a coherent self-consistent metric space and the
   checkpoint is deterministic/non-degenerate. It is the prerequisite for
   find-similar (`similar_by_id`) AND a precondition for text2image.
4. **find-similar may ship before text2image.** `similar_by_id`
   (`webui/search.py:463`) is image→image and depends only on GATE 0 +
   vectors present. This ADR records that GATE 0 passing authorizes find-similar
   go-live (SPEC-find-similar-golive) but does NOT by itself flip
   `TEXT2IMAGE_GATE_PASSED`.
5. **text2image needs GATE 0 AND GATE 1.** `TEXT2IMAGE_GATE_PASSED=1` is flipped
   only after BOTH (a) this self-retrieval check passes AND (b) the cross-modal
   text-tower verification in ADR-0006 passes (a held-out text query retrieves
   the expected image above its random-pair baseline). Until GATE 1,
   `_text_query_vector` returns None and the mode degrades — correctly.
6. **Threshold rationale.** >0.99 (not parity's 0.9999) because this is
   recompute-vs-stored across two *different* runtimes (local MPS fp16/fp32 vs
   H100). MPS vs CUDA accumulation drift legitimately costs a few thousandths of
   cosine; 0.99 catches a wrong checkpoint (which collapses to ~random, cosine
   well below 0.5 against the true vector) while tolerating runtime drift. Parity
   (same-runtime recompute) keeps its tighter 0.9999.

No schema change. No migration. Read-only against `data/catalog.db` /
`vec_siglip_1152`. No new dependency (torch/transformers already used by
`Tier1Embedder._load`).

## Concrete touchpoints

| Item | File / endpoint / table | Add or change |
|---|---|---|
| New verifier script | `scripts/verify_self_retrieval.py` | ADD — re-embed ids, query `vec_siglip_1152`, assert top1==self & cos>0.99, JSON+exit code |
| Probe id set | `data/validation/tier1_ids.json` | REUSE (read-only) — the 10 baseline ids |
| Local image tower | `pipeline/tier1_embedder.py::Tier1Embedder.embed_image` / `._load` | REUSE (no change) |
| Vector store read | `webui/search.py::_vec_rescore` / `open_vec_db` / `VEC_TABLE` | REUSE the rescore SQL (or inline the same `embedding MATCH ? AND k=?` query) |
| Vector presence | `webui/search.py::vector_count` | REUSE as a pre-check (count>0 before running) |
| The gate flag | `webui/search.py:53` `TEXT2IMAGE_GATE_PASSED` | UNCHANGED mechanism; this ADR defines *when* an operator sets the env var to `1` |
| Test | `tests/test_self_retrieval.py` (new) or extend `tests/test_tier1_embedder.py` | ADD — unit-test the top1/threshold decision logic with synthetic vectors (no torch); the live MPS run stays a manual/operator step |
| Docs cross-ref | `webui/search.py:49-53` docstring; `knowledge/vendors/siglip-quirks.md` | note the gate is two-stage (image-space here, cross-modal in ADR-0006) |

Tables touched: `vec_siglip_1152` (READ only). No writes anywhere.

## Dependencies & gates

- **Blocked by:** H100 full run populating `vec_siglip_1152` (and the parity gate
  passing — parity must pass first; this is the *next* check on top of it).
- **Needs:** local SigLIP image tower (`Tier1Embedder._load`) — requires
  torch + transformers + SigLIP weights present on the Mac (already used by the
  parity validator's tier1 path, so this is a satisfied prerequisite).
- **Blocks:** `TEXT2IMAGE_GATE_PASSED=1` (jointly with ADR-0006 GATE 1).
- **Authorizes (alone):** SPEC-find-similar-golive (image→image).
- **Does NOT authorize:** the text tower / text2image — see ADR-0006.

## Sequencing

1. H100 full run + `validate_h100_parity.py` PASS.
2. This ADR's verifier → GATE 0 PASS → ship find-similar (SPEC-find-similar-golive).
3. ADR-0006 text-tower hosting + GATE 1 cross-modal check.
4. GATE 0 ∧ GATE 1 PASS → operator sets `TEXT2IMAGE_GATE_PASSED=1` → text2image live.

Effort: **S** (one ~80-line read-only script + a small unit test; reuses the
embedder and the rescore SQL; fixture already exists).

## H100 cost note

Zero incremental H100 cost. The gate runs entirely on the Mac (MPS) against
already-downloaded vectors. It re-embeds ~10-20 images locally — seconds of MPS
time, no rented GPU. It does NOT trigger a re-run on the box; a FAIL means the
checkpoint used on the H100 was wrong and the *next* full run must pin the HF
`SiglipModel` (not a timm vision-only checkpoint) — that re-run is the cost, and
it is the whole point of catching this cheaply before trusting 26.5k vectors.

## Risks

- **False sense of security (primary).** Self-retrieval passing does NOT prove
  cross-modal validity — a vision-only checkpoint passes GATE 0 trivially.
  MITIGATION: this ADR explicitly forbids flipping the text2image flag on GATE 0
  alone; cross-modal proof is ADR-0006 GATE 1. Documented in code + this ADR.
- **Threshold too tight / too loose.** 0.99 is a judgment call for cross-runtime
  drift. MITIGATION: report worst-case cosine + which-neighbor-won so a marginal
  pass is visible, not silent; widen probe set to ~20 to reduce single-image
  luck.
- **fp32 vs fp16 / rev-flag mismatch.** The H100 runner has fp32/rev flags
  (commit 742aa6a); if the box embedded in a different precision than the local
  MPS re-embed, cosine drifts. MITIGATION: pin the same precision contract the
  parity gate assumes; if drift pushes legitimate matches below 0.99, the report
  surfaces it for a one-line threshold review (do not auto-loosen).
- **Over-engineering for one user.** A 20-image manual check is the *floor*, not
  a CI harness. Keep it a single operator-run script; resist building a
  scheduled monitor.

## Acceptance / verify checks

- `python3 scripts/verify_self_retrieval.py --ids data/validation/tier1_ids.json`
  exits 0, and the JSON shows every probe id's top neighbor == itself with
  cosine > 0.99 (report includes `worst_cosine` and any `wrong_neighbor`).
- A deliberately wrong vector (e.g. a shuffled/zeroed embedding for one id)
  makes the script exit 1 — proves the check actually discriminates.
- `./venv/bin/pytest tests/ -q` passes (new unit test on the top1/threshold
  decision logic, using synthetic vectors, no torch required).
- After GATE 0 ∧ GATE 1: with `TEXT2IMAGE_GATE_PASSED=1`, a `mode=text2image`
  query returns ranked image results (not `degraded_from: text2image`) — this is
  the ADR-0006 acceptance, recorded here only as the downstream consequence.
