# SigLIP SO400M quirks

Model: `google/siglip-so400m-patch14-384`.

- **Image embedding is 1152-dim, NOT 768** (768 is a common stale reference that bit
  this project). Use `pooler_output`, L2-normalize. The vec table is `vec_siglip_1152`.
- **Dual encoder**: the text tower shares the same 1152-dim space → enables true
  text→image search. **Trap**: a *timm vision-only* checkpoint yields 1152-dim vectors
  that are semantically wrong for text queries. **Verify before trusting**: re-embed
  ~20 known images via HF `get_image_features`, L2-normalize, confirm each image's top
  cosine match is itself (≈1.0). See `docs/specs/batched-siglip-embed.md`.
- MLX acceleration for SigLIP is still in flight upstream (as of 2026-06); embeds run
  via torch/MPS or ONNX. Batch the embed pass for throughput (parity-test first).
