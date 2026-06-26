---
title: Compute providers
description: Route each pipeline capability to a compute backend — local by default, with a privacy gate that keeps uncensored work from ever leaving the box.
group: Reference
order: 95
---

Tessera's pipeline runs four capabilities — `embed` (Tier 1 SigLIP), `tag`
(Tier 0), `caption` (Tier 2 VLM), and `detect` (Tier 3 NudeNet). Each one is
routed to a named **compute backend**. By default every route points at the local
machine, and you can re-point any of them by editing config — no code change.

## Routes and backends

The `compute:` block maps each capability to a backend, and configures each
backend by value:

```yaml
compute:
  routes:
    embed: local_mps
    tag: local_mps
    caption: local_mps
    detect: local_mps
  backends:
    local_mps:
      type: local_mps
    rented_metal:
      type: rented_metal
      base_url: "http://your-box.example:8000"
      api_key: null            # name of a secret, resolved at call time — never the key
      timeout: 120
```

Swapping a backend is a config-value edit. The four routes are independent, so
you can keep tagging and embedding local while offloading only captions.

## Local backends are auto-selected

On first run, Tessera probes the host and picks the best local backend for the
hardware, then writes the choice into the resolved config so you do not hand-edit
it:

- `local_mps` — Apple Silicon (CoreML execution provider)
- `local_cuda` — NVIDIA GPUs (CUDA / TensorRT)
- `local_directml` — Windows with a DirectML GPU
- `local_cpu` — fallback when no accelerator is present

All four are `local` privacy: pixels never leave the machine.

## Captions

Tier 2 captions run against a local **mlx Qwen2.5-VL** server (default
`http://127.0.0.1:8081`, model `mlx-community/Qwen2.5-VL-7B-Instruct-4bit`). The
server reads image files directly on the box, so paths and pixels are never
uploaded. On Windows and Linux, where mlx is macOS-only, point the caption route
at any OpenAI-compatible local server (Ollama, llama.cpp, LM Studio, vLLM) — a
config change, not a code change. See [Platform support](/docs/platform-support).

## The privacy gate

Privacy is a first-class attribute of every backend, not an afterthought. Each
declares one of:

- `local` — pixels never leave the box (the local backends above)
- `private-infra` — your own rented endpoint (`rented_metal`)
- `hosted-moderated` — a third-party API that may inspect or refuse content

The dispatcher enforces a hard rule: an **uncensored job must never reach a
`hosted-moderated` backend**. Your own infrastructure (`private-infra`) is
allowed, because the boundary is about who can see the pixels, not where the
compute runs. The backends that ship today are all `local` or `private-infra`;
the gate is in place for the day a hosted route is added.

## Offloading to your own infra

`rented_metal` targets a self-hosted, OpenAI-compatible endpoint (vLLM, SGLang,
Triton) by `base_url`. It runs in batch mode and is treated as `private-infra`,
so it can take uncensored work. An optional `api_key` field holds the *name* of a
secret, resolved from your environment at call time — the key itself never lands
in the config file.

Every value here also has a `MEDIA_PIPELINE_*` environment-variable form for
per-run overrides. See [Configuration](/docs/configuration) for precedence.
