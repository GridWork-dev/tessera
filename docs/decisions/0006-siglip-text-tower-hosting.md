# ADR 0006 — SigLIP text-tower hosting + 64-token preprocessing contract

Status: Proposed (plan-only). Supersedes the `_text_query_vector() -> None` stub in `webui/search.py:391`.
Date: 2026-06-23

## Context / problem

`text2image` / `semantic` / `hybrid` are the flagship search modes. The full code path is built (`webui/search.py::run_search` -> `_vector_search` -> TurboVec allowlist -> sqlite-vec cosine rescore) and degrades to tag relevance today because `_text_query_vector(q)` returns `None` — the SigLIP **text tower** is not wired.

The load-bearing question is NOT the body of `_text_query_vector` (that's a few lines, effort S). It's **where the ~1GB text tower lives** relative to a FastAPI host that is currently inference-free (no model ever loaded in-process; all ML runs in batch jobs / on the rented H100). Two real options:

1. **In-process lazy load** — load the SigLIP text tower inside the API process on first text query.
2. **Sidecar** — a separate local process (subprocess / small FastAPI / ZeroMQ) owns the model; the API does IPC.

Verified facts (read, not assumed):
- `torch 2.12.1` + `transformers 5.12.1` ARE in the API venv (`./venv/bin/python -c "import torch, transformers"` succeeds). In-process loading needs no new dependency.
- `pipeline/tier1_embedder.py::Tier1Embedder._load` (lines 212-226) already establishes the exact lazy-load pattern: import torch lazily, pick `mps`-or-cpu, `AutoProcessor`/`AutoModel.from_pretrained(MODEL_ID)`, `.eval()`. It uses `get_image_features(...).pooler_output`; the text tower is the symmetric `get_text_features(...)`.
- `webui/main.py:554 api_search` is `async def` and calls the **synchronous** `search_svc.run_search`. A torch forward in the request thread blocks the event loop for the duration of the embed.
- Model id is `google/siglip-so400m-patch14-384` (`Tier1Embedder.MODEL_ID`), 1152-dim, shared text+image space (`knowledge/vendors/siglip-quirks.md`). The SO400M text encoder is the smaller half of the checkpoint; resident footprint is on the order of ~1-1.5GB in fp32 on CPU/MPS (the "~3.4GB" figure in the roadmap item is the whole checkpoint, not the text tower alone — the image tower is loaded separately by the batch path, never in the API).

## Decision

### 1. Host **in-process, lazy-loaded** — NOT a sidecar.

For a single-user private tool, a sidecar adds a process to supervise, an IPC contract to version, and a second copy of torch — pure over-engineering. The text tower is small, queries are human-paced (one user typing), and the model loads once then stays resident. Justification:

- **One user, low QPS.** No concurrency pressure that a sidecar would relieve. Worst realistic case is one in-flight text query.
- **Deps already present.** No isolation benefit — torch is already importable in the API venv.
- **Event-loop blocking is cheap to fix correctly.** Wrap the synchronous embed in `await anyio.to_thread.run_sync(...)` (or `run_in_executor`) at the one call site, so the ~10-50ms MPS forward doesn't stall other routes. The model itself is NOT thread-safe across concurrent forwards, so guard with a module-level `threading.Lock` (a single user won't contend, but it makes the in-process choice safe under the default multi-route server).

Mirror `Tier1Embedder._load` exactly: a module-level singleton holder in a new `pipeline/text_embedder.py` (text twin of `tier1_embedder.py`), lazy-imported torch/transformers, `mps`-or-cpu, `.eval()`, loaded on first call and cached for process lifetime. First query pays a one-time ~3-8s load; subsequent queries are warm. Gate loading behind the same readiness as the rest of the path so a cold/un-gated server never loads the model.

### 2. Preprocessing contract (NON-NEGOTIABLE — wrong preprocessing silently poisons every text query)

Confirmed against HF SigLIP docs (https://huggingface.co/docs/transformers/v5.8.1/en/model_doc/siglip): *"When using the standalone SiglipTokenizer or SiglipProcessor, make sure to pass `padding='max_length'` because that is how the model was trained."*

```python
inputs = processor(
    text=[q],
    padding="max_length",   # MANDATORY — model trained this way; default 'longest' degrades silently
    max_length=64,          # SigLIP text context length
    truncation=True,
    return_tensors="pt",
).to(device)
with torch.no_grad():
    feats = model.get_text_features(**inputs)   # (1, 1152)
vec = l2_normalize(feats[0].cpu().numpy().astype(np.float32))  # reuse tier1_embedder.l2_normalize
```

- **Lowercase**: `SiglipTokenizer` canonicalizes/lowercases internally (`do_lower_case`), so do NOT pre-lowercase the raw query in a way that fights the tokenizer; rely on the processor. Record this so a future refactor doesn't bolt on a redundant `.lower()` that the tokenizer already does — but the contract is "the tokenizer owns case normalization."
- **L2-normalize** the output with the SAME `l2_normalize` helper the image path uses (`tier1_embedder.py:54`), so the text query vector lives on the same unit sphere as the stored image vectors that the sqlite-vec `distance_metric=cosine` rescore expects.
- **Single canonical embed function** shared by both the query path and the GATE 1 re-embed, so a contract change can never make the gate and the live path disagree.

### 3. DROP GR-CLIP modality-gap calibration.

GR-CLIP (arxiv 2507.19054 / https://yuhui-zh15.github.io/MixedModalitySearch/) subtracts per-modality mean embeddings to close the CLIP/SigLIP modality gap, improving NDCG@10 by up to 26pp on **mixed-modality** corpora (heterogeneous image+text+multimodal documents). This project's corpus is **homogeneous images** ranked by a single text query — the intra-modal ranking-bias and inter-modal-fusion-failure that GR-CLIP fixes do not arise when every candidate is an image. Computing/storing modality means is research-grade tuning with no payoff for one user searching one modality. Record as explicitly DEFERRED; revisit only if/when video scenes + captions become co-ranked corpus items (the `vec_owner` table in migration 006 hints at a future mixed corpus, but that is not this ADR).

### 4. NEVER surface raw cross-modal cosine as a confidence/percentage.

SigLIP's sigmoid-loss cross-modal cosines are NOT calibrated probabilities and the modality gap makes their absolute magnitude misleading. Use cosine ONLY as a **ranking** signal. `webui/search.py` already does the right thing — it emits `score_parts={"vector": round(...)}` as an opaque rank score (line 349), not a labeled confidence. This ADR pins that: the UI must present text2image hits as ranked, never "87% match." No change required, only a recorded constraint.

## Concrete touchpoints

Add:
- **`pipeline/text_embedder.py`** (NEW) — `TextEmbedder` with the same lazy `_load` shape as `Tier1Embedder._load`, a module-level singleton accessor, a `threading.Lock`, and one `embed_text(q) -> np.ndarray[1152]` implementing the contract above. Reuse `l2_normalize`/`serialize_float32` from `tier1_embedder`. MODEL_ID identical (`google/siglip-so400m-patch14-384`).

Change:
- **`webui/search.py:391 _text_query_vector`** — replace the `return None` stub with: import the text-embedder singleton, embed `q`, return `serialize_float32(vec)` (the blob shape `_vector_search` -> sqlite-vec expects). Return `None` only for empty/whitespace `q`. No other line in `search.py` changes (`run_search`/`_vector_search` already branch on a non-None vector).
- **`webui/main.py:586`** — wrap `search_svc.run_search(...)` in `await anyio.to_thread.run_sync(...)` so the in-process torch forward never blocks the event loop. (Optional but recommended; the only behavioral edit to the route.)

Untouched: no schema change (read-only over existing `vec_siglip_1152` + `turbovec_siglip.idx`), no migration, `data/catalog.db` not written. `TEXT2IMAGE_GATE_PASSED` env flag (`search.py:53`) stays the authorization switch — this ADR does NOT flip it (ADR-0005 owns that).

## Dependencies & gates

- **GATE 1 (self-retrieval, ADR-0005) MUST pass first.** Wiring the text tower is pointless — and actively harmful — if the stored image vectors came from a vision-only timm checkpoint (`siglip-quirks.md` trap). The gate proves the image vectors are real SigLIP before any text query is trusted. Sequencing: GATE 1 -> this ADR -> flip `TEXT2IMAGE_GATE_PASSED=1`.
- **H100 vectors present** — `vec_siglip_1152` + `data/turbovec_siglip.idx` populated by the H100 full run (`vector_count(db) > 0`). The text tower produces queries; without indexed image vectors there is nothing to rank.
- Hard dep on the same `processor`/`get_text_features` API already proven for the image side; no new pip install.

## Effort + sequencing

**M.** The code is S (one new ~40-line module mirroring an existing pattern + one stub replacement + one `to_thread` wrap). The M comes from the decision/validation surface: pinning the hosting model, getting the preprocessing contract provably correct, and the GATE-1 ordering. Sequence: (1) ADR-0005 self-retrieval gate passes; (2) implement `text_embedder.py` + swap the stub; (3) verify; (4) flip the env gate.

## H100 cost note

**Zero incremental H100 cost.** The text tower runs LOCALLY in the API process (MPS/CPU) at query time — it is not a batch job. The image vectors it ranks against were already produced by the H100 full run (sunk cost, accounted under the Tier-1 embed pass). No GPU-hours attributable to this ADR.

## Risks

- **Silent preprocessing drift** — the single highest risk. Default `padding='longest'` instead of `'max_length'`, or skipping `max_length=64`, yields plausible-looking-but-wrong vectors and degrades ranking with no error. Mitigation: the contract is a single shared embed function + a unit assertion on tokenized `input_ids` length == 64.
- **Wrong-checkpoint poisoning** — fully owned by GATE 1; this ADR refuses to flip the env gate until GATE 1 passes.
- **Event-loop stall** if the synchronous forward isn't offloaded — mitigated by the `to_thread` wrap; low real impact at one-user QPS.
- **First-query latency** (~3-8s model load) — acceptable one-time cost; optionally pre-warm on startup behind a flag if it annoys. Not worth a sidecar.
- **Cold model memory** (~1-1.5GB resident) on the M4 alongside the API — fine on this box; flagged so it isn't a surprise.

## Acceptance / verify

1. `./venv/bin/python -c "from pipeline.text_embedder import embed_text; v=embed_text('a photo'); import numpy as np; print(v.shape, round(float(np.linalg.norm(v)),4))"` -> `(1152,) 1.0`.
2. Tokenizer contract: assert the processor call produces `input_ids` of length 64 (`padding='max_length'` honored).
3. **Cross-modal sanity** (after GATE 1, vectors present): embed a query whose answer is obvious from tags (e.g. a high-frequency `content_type`), confirm `mode=text2image` returns `mode: "text2image"` (NOT `degraded_from`) and the top hits are visually on-topic. This is the real proof the text tower shares the image space — distinct from GATE 1's image-self-retrieval.
4. `GET /api/search?mode=text2image&q=...` returns `mode:"text2image"` only when `TEXT2IMAGE_GATE_PASSED=1` AND vectors exist; otherwise still degrades (existing degrade tests stay green).
5. `./venv/bin/pytest tests/ -q` green; degrade-path tests unchanged (the stub-replacement must not alter the no-vector / no-query degradation contract).
6. No write to `data/catalog.db` during a text query (read-only assertion).
