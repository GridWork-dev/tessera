#!/usr/bin/env python3
"""
H100 OFFLOAD — portable, box-side entrypoint that runs all 4 tiers on a FLAT
directory of ``<image_id>.webp`` files and emits tiny artifacts to import back
into ``catalog.db`` on the Mac.

PRIVACY CONTRACT (read this first)
----------------------------------
This script runs on a RENTED, untrusted box. It is built so the box NEVER sees:
  * real filenames or directory paths,
  * the ``person`` / ``rating`` taxonomy,
  * ``catalog.db`` or any DB at all.
The ONLY input is a flat dir of ``<id>.webp`` where ``id`` is the catalog.db
integer primary key. Everything that maps an id back to a person/rating/path
lives in a LOCAL-ONLY manifest on the Mac (see ``prepare_remote_upload.py``).
The artifacts emitted here are keyed solely by that integer id.

This module is DEPENDENCY-SELF-CONTAINED for parity: it re-implements the exact
preprocessing of the local tier modules rather than importing them, so it runs
on a box that has no ``pipeline/`` package, no ``catalog.db``, and no content
root. The constants below are copied VERBATIM from the local tier modules and
are the parity contract — keep them in lock-step.

EXACT PREPROCESSING / PARITY CONTRACT (cite: pipeline/tier{0,1,3}_*.py)
----------------------------------------------------------------------
Tier 0 — WD-EVA02 (SmilingWolf wd-eva02) + JoyTag, both ONNX, multi-label:
  * Shared image size 448. Pad to centered square on WHITE (255,255,255),
    resize 448 with PIL BICUBIC.
  * WD-EVA02 input: [1,448,448,3] NHWC, **BGR**, float32 0..255 (NO /255, NO
    mean/std — the model normalizes internally). Output is ALREADY probabilities
    (sigmoid is IN-GRAPH) — do NOT sigmoid again.
      - general (selected_tags.csv category 0) prob >= 0.45  -> category "tags"
      - character (category 4)               prob >= 0.85  -> category "person"
      - rating  (category 9): single tag = argmax over the 4 rating probs
                                                              -> category "rating"
      tag_source = "wd_eva02".
  * JoyTag input: [1,3,448,448] NCHW, **RGB**, scaled [0,1] then CLIP-normalized
    (mean [0.48145466,0.4578275,0.40821073], std
    [0.26862954,0.26130258,0.27577711]). Output is RAW LOGITS — DO sigmoid.
      - prob >= 0.40 -> category "tags", tag_source = "joytag".
  * Labels: selected_tags.csv (index==logit index), top_tags.txt
    (.read().splitlines(), index==logit index).

Tier 1 — SigLIP SO400M (google/siglip-so400m-patch14-384, hidden_size 1152):
  * torch + transformers bf16/fp16 on CUDA (mirrors local MPS path exactly).
  * inputs = processor(images=img, return_tensors='pt')
    out = model.get_image_features(**inputs); emb = out.pooler_output  # (N,1152)
    Read ``.pooler_output`` — NOT a bare tensor, NOT last_hidden_state mean-pool.
  * L2-normalize each row -> float32[1152]. Emit embeddings.npy [N,1152] f32 +
    ids.npy [N] (parallel, row i <-> ids[i]).
  * The .idx (turbovec) is built LOCALLY on import — see import_h100_artifacts.py.

Tier 2 — JoyCaption Beta One (fancyfeast/llama-joycaption-beta-one-hf-llava),
  ~8B LLaVA, served by vLLM (OpenAI-compatible /v1/chat/completions):
  * model row written on import = "llama-joycaption-beta-one" (coexists with any
    prior Qwen rows via UNIQUE(image_id, model)).
  * DETERMINISM: temperature=0.0, top_p=1.0, seed=0, fixed max_tokens — required
    so validate_h100_parity.py can demand an exact caption match.
  * Reuses the local Tier-2 prompt by default (tier2_captioner.DEFAULT_PROMPT,
    copied below) for register consistency; override with --caption-prompt.

Tier 3 — NudeNet (small ONNX, metadata only — NEVER a gate, ADR-0001):
  * raw det {'class','score','box':[x,y,w,h]} (top-left + w/h) -> stored
    {'label','score' rounded 4dp,'box':[x1,y1,x2,y2]} with x2=x+w, y2=y+h.

OUTPUTS (written to --out-dir, all keyed by integer id):
  tags.jsonl       {"id": int, "rows": [{category,value,confidence,tag_source}]}
  embeddings.npy   float32 [N,1152]  (+ ids.npy int64 [N], parallel)
  captions.jsonl   {"id": int, "caption": str}
  nudenet.jsonl    {"id": int, "regions": [{label,score,box[x1,y1,x2,y2]}]}
  run_manifest.json  provenance: tier versions, thresholds, counts, timings.

Usage on the box (after weights are baked / pulled — see docker/Dockerfile.h100):
    python3 remote_pipeline_runner.py \
        --in-dir /work/images \
        --out-dir /work/artifacts \
        --models-dir /opt/models \
        --tiers 0,1,2,3 \
        --vllm-url http://127.0.0.1:8000

Tiers can be run independently (e.g. --tiers 2 for a caption-only re-run). Each
tier is resume-safe: it skips ids already present in its output artifact.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("remote_runner")

# ===========================================================================
# PARITY CONSTANTS — copied VERBATIM from pipeline/tier{0,1,2,3}_*.py.
# Changing any of these breaks parity with local output. Keep in lock-step.
# ===========================================================================

IMG_SIZE = 448  # tier0_tagger.IMG_SIZE

WD_NUM_TAGS = 10861
JOYTAG_NUM_TAGS = 5813

WD_CAT_GENERAL = 0
WD_CAT_CHARACTER = 4
WD_CAT_RATING = 9

WD_GENERAL_THRESHOLD = 0.45  # locked 2026-06-23
WD_CHARACTER_THRESHOLD = 0.85
JOYTAG_THRESHOLD = 0.40

# CLIP normalization for JoyTag (tier0_tagger.CLIP_MEAN/STD).
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

# Tier 1 (tier1_embedder).
SIGLIP_MODEL_ID = "google/siglip-so400m-patch14-384"
EMBEDDING_DIM = 1152

# Tier 2 (tier2_captioner.DEFAULT_PROMPT copied verbatim for register parity).
JOYCAPTION_MODEL_ID = "fancyfeast/llama-joycaption-beta-one-hf-llava"
# The model name written to the captions table on import (research brief 06).
JOYCAPTION_DB_MODEL = "llama-joycaption-beta-one"
DEFAULT_CAPTION_PROMPT = (
    "Describe this image for a searchable media catalog. In 1-3 concise, factual "
    "sentences, cover the subject, pose, clothing or state of dress, setting, and "
    "any notable visual attributes. Do not editorialize or add a preamble."
)
CAPTION_MAX_TOKENS = 256


# ===========================================================================
# Shared image helpers (parity with tier0_tagger._pad_to_square / preprocess).
# ===========================================================================
def _pad_to_square(img, fill: tuple[int, int, int]):
    """Pad a PIL RGB image to a centered square on a solid background."""
    w, h = img.size
    side = max(w, h)
    if w == side and h == side:
        return img
    from PIL import Image as _PILImage

    canvas = _PILImage.new("RGB", (side, side), fill)
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    return canvas


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def wd_preprocess(img) -> np.ndarray:
    """WD-EVA02 preprocess -> float32 [1,448,448,3] NHWC BGR 0..255 (no /255)."""
    from PIL import Image as _PILImage

    img = img.convert("RGB")
    img = _pad_to_square(img, (255, 255, 255))
    img = img.resize((IMG_SIZE, IMG_SIZE), _PILImage.BICUBIC)
    arr = np.asarray(img, dtype=np.float32)  # HWC RGB 0..255
    arr = arr[:, :, ::-1]  # RGB -> BGR
    arr = np.ascontiguousarray(arr)
    return arr[np.newaxis, ...]


def joytag_preprocess(img) -> np.ndarray:
    """JoyTag preprocess -> float32 [1,3,448,448] NCHW RGB CLIP-normalized."""
    from PIL import Image as _PILImage

    img = img.convert("RGB")
    img = _pad_to_square(img, (255, 255, 255))
    img = img.resize((IMG_SIZE, IMG_SIZE), _PILImage.BICUBIC)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - CLIP_MEAN) / CLIP_STD
    arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
    arr = np.ascontiguousarray(arr, dtype=np.float32)
    return arr[np.newaxis, ...]


# ===========================================================================
# Label loading (parity with tier0_tagger.load_wd_labels / load_joytag_labels).
# ===========================================================================
def load_wd_labels(csv_path: Path) -> dict[str, list]:
    import csv as _csv

    names: list[str] = []
    categories: list[int] = []
    rating_indices: list[int] = []
    rating_names: list[str] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = _csv.reader(f)
        header = next(reader)  # tag_id,name,category,count
        name_col = header.index("name")
        cat_col = header.index("category")
        for idx, row in enumerate(reader):
            names.append(row[name_col])
            cat = int(row[cat_col])
            categories.append(cat)
            if cat == WD_CAT_RATING:
                rating_indices.append(idx)
                rating_names.append(row[name_col])
    return {
        "names": names,
        "categories": categories,
        "rating_indices": rating_indices,
        "rating_names": rating_names,
    }


def load_joytag_labels(txt_path: Path) -> list[str]:
    with open(txt_path, encoding="utf-8") as f:
        return f.read().splitlines()


# ===========================================================================
# Logit -> tag mapping (parity with tier0_tagger.map_wd_logits/map_joytag_logits).
# ===========================================================================
def map_wd_logits(
    logits: np.ndarray, labels: dict[str, list]
) -> list[tuple[str, str, float]]:
    probs = np.asarray(logits, dtype=np.float32).reshape(-1)  # ALREADY probs
    names = labels["names"]
    cats = labels["categories"]
    out: list[tuple[str, str, float]] = []
    for idx, prob in enumerate(probs):
        cat = cats[idx]
        if cat == WD_CAT_GENERAL and prob >= WD_GENERAL_THRESHOLD:
            out.append(("tags", names[idx], float(prob)))
        elif cat == WD_CAT_CHARACTER and prob >= WD_CHARACTER_THRESHOLD:
            out.append(("person", names[idx], float(prob)))
    rating_indices = labels["rating_indices"]
    if rating_indices:
        rating_probs = probs[rating_indices]
        best = int(np.argmax(rating_probs))
        best_idx = rating_indices[best]
        out.append(("rating", names[best_idx], float(probs[best_idx])))
    return out


def map_joytag_logits(logits: np.ndarray, labels: list[str]) -> list[tuple[str, float]]:
    logits = np.asarray(logits, dtype=np.float32).reshape(-1)
    probs = _sigmoid(logits)
    out: list[tuple[str, float]] = []
    for idx, prob in enumerate(probs):
        if prob >= JOYTAG_THRESHOLD:
            out.append((labels[idx], float(prob)))
    return out


# ===========================================================================
# Discovery — enumerate <id>.webp in the flat input dir.
# ===========================================================================
def discover_ids(in_dir: Path) -> list[tuple[int, Path]]:
    """Return sorted [(id, path)] for every <int>.webp in the flat dir.

    Non-integer-stem files are skipped with a warning (privacy + parity: only
    pure-integer ids are valid catalog primary keys).
    """
    pairs: list[tuple[int, Path]] = []
    for p in sorted(in_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".webp":
            continue
        try:
            img_id = int(p.stem)
        except ValueError:
            logger.warning("skip non-integer filename: %s", p.name)
            continue
        pairs.append((img_id, p))
    pairs.sort(key=lambda t: t[0])
    return pairs


def _already_done_ids(jsonl_path: Path) -> set[int]:
    """Resume helper: ids already present in a JSONL artifact."""
    done: set[int] = set()
    if not jsonl_path.exists():
        return done
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(int(json.loads(line)["id"]))
            except ValueError, KeyError, json.JSONDecodeError:
                continue
    return done


def _log_fail(out_dir: Path, tier: str, img_id: int, err: object) -> None:
    """Record a per-image failure so nothing is silently dropped (observability)."""
    with open(out_dir / "failures.jsonl", "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps({"tier": tier, "id": int(img_id), "error": str(err)[:300]})
            + "\n"
        )


# ===========================================================================
# Tier 0 — WD-EVA02 + JoyTag (ONNX, GPU EP with CPU fallback).
# ===========================================================================
def _onnx_session(model_path: Path, providers: list[str]):
    # Load torch first so its bundled CUDA libs are resolved in-process before ORT
    # creates a CUDA session (the verified-working order). Harmless on CPU boxes.
    try:
        import torch  # noqa: F401
    except Exception:  # noqa: BLE001
        pass
    import onnxruntime as ort

    if not model_path.exists():
        raise FileNotFoundError(f"ONNX model missing on box: {model_path}")
    avail = ort.get_available_providers()
    use = [p for p in providers if p in avail] or ["CPUExecutionProvider"]
    # Disable TF32 on the CUDA EP: TF32 matmuls (default on Ampere/Hopper) shift
    # ONNX logits by ~0.3 vs the Mac's CPU fp32, breaking Tier-0 tag parity.
    # use_tf32=0 -> full fp32 (logit diff ~1e-3), tags match.
    entries = [
        ("CUDAExecutionProvider", {"use_tf32": 0})
        if p == "CUDAExecutionProvider"
        else p
        for p in use
    ]
    logger.info("ONNX %s providers=%s (cuda tf32=off)", model_path.name, use)
    return ort.InferenceSession(str(model_path), providers=entries)


def run_tier0(
    pairs: list[tuple[int, Path]], models_dir: Path, out_dir: Path, batch_size: int = 1
) -> int:
    from PIL import Image as PILImage

    wd_model = models_dir / "wd-eva02" / "model.onnx"
    wd_labels_path = models_dir / "wd-eva02" / "selected_tags.csv"
    joytag_model = models_dir / "joytag" / "model.onnx"
    joytag_labels_path = models_dir / "joytag" / "top_tags.txt"

    wd_labels = load_wd_labels(wd_labels_path)
    joytag_labels = load_joytag_labels(joytag_labels_path)

    # CUDA EP is the parity-safe GPU path. TensorRT is faster but its graph-build
    # is slow and numerically divergent (parity-risky), so it is intentionally
    # NOT in the default order; CPU is the fallback.
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    wd_sess = _onnx_session(wd_model, providers)
    joytag_sess = _onnx_session(joytag_model, providers)
    wd_in = wd_sess.get_inputs()[0].name
    joytag_in = joytag_sess.get_inputs()[0].name

    out_path = out_dir / "tags.jsonl"
    done = _already_done_ids(out_path)
    todo = [(i, p) for (i, p) in pairs if i not in done]
    bs = max(int(batch_size), 1)
    written = 0
    failed = 0
    next_log = 500
    t0 = time.time()

    def _emit(f, img_id: int, wd_logits, joytag_logits) -> None:
        rows: list[dict[str, Any]] = []
        for category, value, score in map_wd_logits(wd_logits, wd_labels):
            rows.append(
                {
                    "category": category,
                    "value": value,
                    "confidence": score,
                    "tag_source": "wd_eva02",
                }
            )
        for value, score in map_joytag_logits(joytag_logits, joytag_labels):
            rows.append(
                {
                    "category": "tags",
                    "value": value,
                    "confidence": score,
                    "tag_source": "joytag",
                }
            )
        f.write(json.dumps({"id": img_id, "rows": rows}) + "\n")

    with open(out_path, "a", encoding="utf-8") as f:
        for start in range(0, len(todo), bs):
            chunk = todo[start : start + bs]
            ids: list[int] = []
            wd_in_list: list[np.ndarray] = []
            joy_in_list: list[np.ndarray] = []
            for img_id, path in chunk:
                try:
                    with PILImage.open(path) as img:
                        img = img.convert("RGB")
                        wd_in_list.append(wd_preprocess(img))
                        joy_in_list.append(joytag_preprocess(img))
                    ids.append(img_id)
                except Exception as exc:  # noqa: BLE001 - per-image isolation
                    logger.warning("tier0 preprocess failed id=%s: %s", img_id, exc)
                    _log_fail(out_dir, "tier0", img_id, exc)
                    failed += 1
            if not ids:
                continue
            try:
                wd_out = wd_sess.run(None, {wd_in: np.concatenate(wd_in_list, 0)})[0]
                joy_out = joytag_sess.run(
                    None, {joytag_in: np.concatenate(joy_in_list, 0)}
                )[0]
            except Exception as exc:  # noqa: BLE001 - whole-batch isolation
                logger.warning("tier0 batch infer failed ids=%s: %s", ids, exc)
                for img_id in ids:
                    _log_fail(out_dir, "tier0", img_id, exc)
                failed += len(ids)
                continue
            for k, img_id in enumerate(ids):
                _emit(f, img_id, wd_out[k], joy_out[k])
                written += 1
            f.flush()
            if written + failed >= next_log:
                logger.info(
                    "tier0 %d/%d (%.1f img/s, %d failed)",
                    written + failed,
                    len(todo),
                    (written + failed) / max(time.time() - t0, 1e-6),
                    failed,
                )
                next_log += 500
    logger.info("tier0 wrote %d rows, %d failed -> %s", written, failed, out_path)
    return written


# ===========================================================================
# Tier 1 — SigLIP SO400M (torch + transformers, fp16/bf16 CUDA), batched.
# ===========================================================================
def run_tier1(
    pairs: list[tuple[int, Path]],
    out_dir: Path,
    batch_size: int = 256,
    dtype_name: str = "auto",
    revision: str | None = None,
) -> int:
    import torch
    from PIL import Image as PILImage
    from transformers import AutoModel, AutoProcessor

    emb_path = out_dir / "embeddings.npy"
    ids_path = out_dir / "ids.npy"

    # Resume: load any existing matrix and skip those ids.
    existing_ids: list[int] = []
    existing_vecs: list[np.ndarray] = []
    if emb_path.exists() and ids_path.exists():
        existing_vecs = list(np.load(emb_path).astype(np.float32))
        existing_ids = list(np.load(ids_path).astype(np.int64))
        logger.info("tier1 resume: %d existing embeddings", len(existing_ids))
    done = set(int(i) for i in existing_ids)
    todo = [(i, p) for (i, p) in pairs if i not in done]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if dtype_name == "fp32":
        dtype = torch.float32
    elif dtype_name == "bf16":
        dtype = torch.bfloat16
    elif dtype_name == "fp16":
        dtype = torch.float16
    else:  # auto: bf16 on CUDA (fast), fp32 on CPU
        dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
    logger.info(
        "tier1 loading %s on %s (%s) rev=%s", SIGLIP_MODEL_ID, device, dtype, revision
    )
    processor = AutoProcessor.from_pretrained(SIGLIP_MODEL_ID, revision=revision)
    model = (
        AutoModel.from_pretrained(SIGLIP_MODEL_ID, torch_dtype=dtype, revision=revision)
        .to(device)
        .eval()
    )

    all_ids: list[int] = list(existing_ids)
    all_vecs: list[np.ndarray] = list(existing_vecs)
    t0 = time.time()
    for start in range(0, len(todo), batch_size):
        chunk = todo[start : start + batch_size]
        chunk_ids = [i for i, _ in chunk]
        try:
            imgs = [PILImage.open(p).convert("RGB") for _, p in chunk]
            inputs = processor(images=imgs, return_tensors="pt").to(device)
            with torch.no_grad():
                out = model.get_image_features(**inputs)
            pooled = out.pooler_output  # (K, 1152)
            mat = pooled.detach().to(torch.float32).cpu().numpy().astype(np.float32)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tier1 batch failed ids=%s: %s", chunk_ids, exc)
            for _fid in chunk_ids:
                _log_fail(out_dir, "tier1", _fid, exc)
            continue
        # Per-row L2-normalize (matches tier1_embedder.embed_images_batched).
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        mat = (mat / norms).astype(np.float32)
        for img_id, row in zip(chunk_ids, mat):
            all_ids.append(int(img_id))
            all_vecs.append(row)
        # Checkpoint after every batch so a crash keeps prior work.
        np.save(emb_path, np.asarray(all_vecs, dtype=np.float32))
        np.save(ids_path, np.asarray(all_ids, dtype=np.int64))
        logger.info(
            "tier1 %d/%d (%.1f img/s)",
            start + len(chunk),
            len(todo),
            (start + len(chunk)) / max(time.time() - t0, 1e-6),
        )
    logger.info(
        "tier1 total embeddings=%d -> %s (+ %s)", len(all_ids), emb_path, ids_path
    )
    return len(all_ids) - len(existing_ids)


# ===========================================================================
# Tier 2 — JoyCaption Beta One via vLLM OpenAI-compatible API (deterministic).
# ===========================================================================
def _encode_image_data_url(path: Path) -> str:
    """Read a local <id>.webp and return a base64 data URL (no path leaks)."""
    import base64

    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/webp;base64,{b64}"


def run_tier2(
    pairs: list[tuple[int, Path]],
    out_dir: Path,
    vllm_url: str,
    prompt: str,
    served_model: str,
    concurrency: int = 1,
) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import requests

    out_path = out_dir / "captions.jsonl"
    done = _already_done_ids(out_path)
    todo = [(i, p) for (i, p) in pairs if i not in done]
    url = vllm_url.rstrip("/") + "/v1/chat/completions"
    session = requests.Session()
    written = 0
    failed = 0
    t0 = time.time()

    def _caption(item: tuple[int, Path]) -> tuple[int, str]:
        img_id, path = item
        payload = {
            "model": served_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": _encode_image_data_url(path)},
                        },
                    ],
                }
            ],
            # DETERMINISM knobs. NOTE: vLLM continuous batching under concurrency
            # is NOT bitwise-exact, so Tier-2 is gated on schema/coverage, not an
            # exact caption match (validate_h100_parity treats it as such).
            "max_tokens": CAPTION_MAX_TOKENS,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 0,
        }
        resp = session.post(url, json=payload, timeout=180)
        resp.raise_for_status()
        return img_id, resp.json()["choices"][0]["message"]["content"].strip()

    with open(out_path, "a", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=max(int(concurrency), 1)) as pool:
            futs = {pool.submit(_caption, it): it[0] for it in todo}
            for n, fut in enumerate(as_completed(futs)):
                img_id = futs[fut]
                try:
                    rid, caption = fut.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("tier2 caption failed id=%s: %s", img_id, exc)
                    _log_fail(out_dir, "tier2", img_id, exc)
                    failed += 1
                    continue
                if not caption:
                    logger.warning("tier2 empty caption id=%s; skipping", rid)
                    _log_fail(out_dir, "tier2", rid, "empty caption")
                    failed += 1
                    continue
                f.write(json.dumps({"id": rid, "caption": caption}) + "\n")
                f.flush()
                written += 1
                if (n + 1) % 200 == 0:
                    logger.info(
                        "tier2 %d/%d (%.2f img/s, %d failed)",
                        n + 1,
                        len(todo),
                        (n + 1) / max(time.time() - t0, 1e-6),
                        failed,
                    )
    logger.info("tier2 wrote %d captions, %d failed -> %s", written, failed, out_path)
    return written


# ===========================================================================
# Tier 3 — NudeNet (metadata only). Parity with tier3_nudenet.convert_regions.
# ===========================================================================
def convert_regions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for det in raw:
        x, y, w, h = det["box"]
        regions.append(
            {
                "label": det["class"],
                "score": round(det["score"], 4),
                "box": [x, y, x + w, y + h],
            }
        )
    return regions


def run_tier3(
    pairs: list[tuple[int, Path]],
    out_dir: Path,
    gpu: bool = False,
    batch_size: int = 64,
) -> int:
    from nudenet import NudeDetector

    out_path = out_dir / "nudenet.jsonl"
    done = _already_done_ids(out_path)
    todo = [(i, p) for (i, p) in pairs if i not in done]
    written = 0
    t0 = time.time()

    if gpu:
        # Full-run throughput path: CUDA EP + batched. Parity is gated on the CPU
        # path (the local tier3 uses per-image CPU detect), so GPU/batch is only
        # for the post-gate full run.
        detector = NudeDetector(
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        with open(out_path, "a", encoding="utf-8") as f:
            for start in range(0, len(todo), batch_size):
                chunk = todo[start : start + batch_size]
                paths = [str(p) for _, p in chunk]
                try:
                    batch_raw = detector.detect_batch(paths)
                except Exception as exc:  # noqa: BLE001 - per-image fallback
                    logger.warning("tier3 batch failed (%s); per-image fallback", exc)
                    batch_raw = []
                    for pth in paths:
                        try:
                            batch_raw.append(detector.detect(pth))
                        except Exception:  # noqa: BLE001
                            batch_raw.append([])
                for (img_id, _), raw in zip(chunk, batch_raw):
                    f.write(
                        json.dumps({"id": img_id, "regions": convert_regions(raw)})
                        + "\n"
                    )
                    written += 1
                f.flush()
                logger.info(
                    "tier3 %d/%d (%.1f img/s)",
                    start + len(chunk),
                    len(todo),
                    (start + len(chunk)) / max(time.time() - t0, 1e-6),
                )
    else:
        # Parity-safe path: CPU, per-image — byte-identical to tier3_nudenet.
        detector = NudeDetector()
        with open(out_path, "a", encoding="utf-8") as f:
            for i, (img_id, path) in enumerate(todo):
                try:
                    raw = detector.detect(str(path))
                    regions = convert_regions(raw)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("tier3 failed id=%s: %s", img_id, exc)
                    _log_fail(out_dir, "tier3", img_id, exc)
                    continue
                f.write(json.dumps({"id": img_id, "regions": regions}) + "\n")
                f.flush()
                written += 1
                if (i + 1) % 1000 == 0:
                    logger.info(
                        "tier3 %d/%d (%.1f img/s)",
                        i + 1,
                        len(todo),
                        (i + 1) / max(time.time() - t0, 1e-6),
                    )
    logger.info("tier3 wrote %d region rows -> %s", written, out_path)
    return written


# ===========================================================================
# Orchestration.
# ===========================================================================
def parse_tiers(raw: str) -> set[int]:
    return {int(t.strip()) for t in raw.split(",") if t.strip() != ""}


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="H100 offload: run all tiers on <id>.webp")
    ap.add_argument("--in-dir", required=True, help="Flat dir of <id>.webp files")
    ap.add_argument("--out-dir", required=True, help="Where to write artifacts")
    ap.add_argument(
        "--models-dir",
        default="/opt/models",
        help="Dir with wd-eva02/ + joytag/ ONNX weights + labels",
    )
    ap.add_argument("--tiers", default="0,1,2,3", help="Comma list of tiers")
    ap.add_argument(
        "--vllm-url",
        default="http://127.0.0.1:8000",
        help="vLLM OpenAI-compatible base URL (Tier 2)",
    )
    ap.add_argument(
        "--served-model",
        default=JOYCAPTION_MODEL_ID,
        help="Model name vLLM serves under (Tier 2)",
    )
    ap.add_argument("--caption-prompt", default=DEFAULT_CAPTION_PROMPT)
    ap.add_argument("--tier1-batch", type=int, default=256)
    ap.add_argument(
        "--tier1-dtype",
        default="auto",
        choices=["auto", "fp32", "bf16", "fp16"],
        help="SigLIP compute dtype. Use fp32 for parity with the local MPS path "
        "(the committed default 'auto' is bf16 on CUDA — fast, but ~4e-3 L2 off).",
    )
    ap.add_argument(
        "--siglip-revision",
        default=None,
        help="Pin the SigLIP HF revision (commit sha) for weight parity.",
    )
    ap.add_argument(
        "--tier3-gpu",
        action="store_true",
        help="Run NudeNet on the GPU (CUDA EP) + batched (full-run throughput). "
        "The parity gate uses the default CPU/per-image path (matches the Mac).",
    )
    ap.add_argument("--tier3-batch", type=int, default=64)
    ap.add_argument(
        "--tier0-batch",
        type=int,
        default=1,
        help="Tier-0 ONNX batch size. 1 = per-image (parity gate); >1 = batched "
        "GPU throughput for the full run (per-row numerically identical).",
    )
    ap.add_argument(
        "--tier2-concurrency",
        type=int,
        default=1,
        help="Concurrent caption requests to vLLM. 1 = sequential; raise (e.g. 32) "
        "for full-run throughput — vLLM continuous-batches them.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    models_dir = Path(args.models_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tiers = parse_tiers(args.tiers)

    pairs = discover_ids(in_dir)
    if not pairs:
        logger.error("no <id>.webp files found in %s", in_dir)
        return 2
    logger.info("discovered %d images; running tiers %s", len(pairs), sorted(tiers))

    summary: dict[str, Any] = {
        "n_images": len(pairs),
        "tiers": sorted(tiers),
        "thresholds": {
            "wd_general": WD_GENERAL_THRESHOLD,
            "wd_character": WD_CHARACTER_THRESHOLD,
            "joytag": JOYTAG_THRESHOLD,
        },
        "siglip_model": SIGLIP_MODEL_ID,
        "embedding_dim": EMBEDDING_DIM,
        "joycaption_model": JOYCAPTION_MODEL_ID,
        "joycaption_db_model": JOYCAPTION_DB_MODEL,
        "img_size": IMG_SIZE,
        "written": {},
        "timings_sec": {},
    }

    if 0 in tiers:
        t = time.time()
        summary["written"]["tier0"] = run_tier0(
            pairs, models_dir, out_dir, args.tier0_batch
        )
        summary["timings_sec"]["tier0"] = round(time.time() - t, 1)
    if 1 in tiers:
        t = time.time()
        summary["written"]["tier1"] = run_tier1(
            pairs,
            out_dir,
            args.tier1_batch,
            args.tier1_dtype,
            args.siglip_revision,
        )
        summary["timings_sec"]["tier1"] = round(time.time() - t, 1)
    if 2 in tiers:
        t = time.time()
        summary["written"]["tier2"] = run_tier2(
            pairs,
            out_dir,
            args.vllm_url,
            args.caption_prompt,
            args.served_model,
            args.tier2_concurrency,
        )
        summary["timings_sec"]["tier2"] = round(time.time() - t, 1)
    if 3 in tiers:
        t = time.time()
        summary["written"]["tier3"] = run_tier3(
            pairs, out_dir, args.tier3_gpu, args.tier3_batch
        )
        summary["timings_sec"]["tier3"] = round(time.time() - t, 1)

    # Observability: per-tier throughput + failure accounting (no silent drops).
    summary["img_per_s"] = {
        k: round(summary["written"].get(k, 0) / v, 2)
        for k, v in summary["timings_sec"].items()
        if v > 0
    }
    fpath = out_dir / "failures.jsonl"
    summary["failures"] = sum(1 for _ in open(fpath)) if fpath.exists() else 0
    (out_dir / "run_manifest.json").write_text(json.dumps(summary, indent=2))
    logger.info(
        "DONE. written=%s img_per_s=%s failures=%d",
        json.dumps(summary["written"]),
        json.dumps(summary["img_per_s"]),
        summary["failures"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
