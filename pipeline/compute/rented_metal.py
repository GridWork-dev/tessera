"""Rented-metal backend — HTTP client for a self-hosted inference endpoint.

This is why the H100 run "just worked": the same seam, a different URL. Points
at your OWN rented box running vLLM / SGLang / Triton / LitServe (URL from
``config.yaml``). ``mode="batch"`` (offline runs) and ``privacy="private-infra"``
(your infra, not a third-party moderated API) — so the privacy gate lets
uncensored jobs through.

Uses ``requests`` (already a dependency; ``tier2_captioner`` uses it too) rather
than pulling in a second HTTP client. The remote-inference call bodies are
intentionally MINIMAL here — wave 1 is the seam, not the remote workload. What
must be real and correct: the interface, the config plumbing (base_url / api_key
/ timeout / per-capability paths), and ``health()`` pinging the endpoint.
"""

from __future__ import annotations

from typing import Any

import requests

from pipeline.compute.base import (
    Capability,
    Caption,
    CostEstimate,
    Health,
    ImageRef,
    Mode,
    Privacy,
    Regions,
    TagSet,
    Vector,
)
from pipeline.compute.registry import register

DEFAULT_TIMEOUT = 120
# Default per-capability endpoint paths on the remote server (override in config).
DEFAULT_PATHS: dict[str, str] = {
    "health": "/health",
    "embed": "/embed",
    "tag": "/tag",
    "caption": "/v1/chat/completions",
    "detect": "/detect",
}


@register("rented_metal")
class RentedMetalBackend:
    """OpenAI-compatible / REST client against a self-hosted GPU endpoint."""

    mode: Mode = "batch"
    privacy: Privacy = "private-infra"

    def __init__(
        self,
        base_url: str,
        name: str = "rented_metal",
        api_key: str | None = None,
        capabilities: list[str] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        paths: dict[str, str] | None = None,
        usd_per_image: float = 0.0,
        **_: Any,
    ) -> None:
        if not base_url:
            raise ValueError("rented_metal requires a base_url")
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.paths = {**DEFAULT_PATHS, **(paths or {})}
        self.usd_per_image = usd_per_image
        # Default to all four if the config doesn't narrow it.
        caps = capabilities or [c.value for c in Capability]
        self.capabilities: set[Capability] = {Capability(c) for c in caps}

    # -- request plumbing -----------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        resp = requests.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def _require(self, cap: Capability) -> None:
        if cap not in self.capabilities:
            raise NotImplementedError(
                f"backend {self.name!r} does not advertise {cap.value!r}"
            )

    # -- capabilities ---------------------------------------------------------
    # Bodies are minimal/stubbed: the seam's contract is the payload shape +
    # transport, not the remote model's exact response schema (that lands with
    # the actual remote workload, wave 2). Each sends ABSOLUTE paths — the
    # endpoint is YOUR box and reads files locally, matching tier2_captioner.
    def embed(self, refs: list[ImageRef]) -> list[Vector]:
        self._require(Capability.EMBED)
        payload = {"paths": [str(r.resolve()) for r in refs]}
        data = self._post(self.paths["embed"], payload)
        vectors = data.get("vectors", [])
        return [
            Vector(
                image_id=ref.image_id,
                values=list(vec),
                dim=len(vec),
                model=data.get("model", "remote"),
            )
            for ref, vec in zip(refs, vectors)
        ]

    def tag(self, refs: list[ImageRef]) -> list[TagSet]:
        self._require(Capability.TAG)
        payload = {"paths": [str(r.resolve()) for r in refs]}
        data = self._post(self.paths["tag"], payload)
        results = data.get("results", [])
        return [
            TagSet(image_id=ref.image_id, tags=list(tags))
            for ref, tags in zip(refs, results)
        ]

    def caption(self, refs: list[ImageRef]) -> list[Caption]:
        self._require(Capability.CAPTION)
        out: list[Caption] = []
        for ref in refs:
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": str(ref.resolve())},
                            }
                        ],
                    }
                ]
            }
            data = self._post(self.paths["caption"], payload)
            text = data["choices"][0]["message"]["content"].strip()
            out.append(
                Caption(
                    image_id=ref.image_id, text=text, model=data.get("model", "remote")
                )
            )
        return out

    def detect(self, refs: list[ImageRef]) -> list[Regions]:
        self._require(Capability.DETECT)
        payload = {"paths": [str(r.resolve()) for r in refs]}
        data = self._post(self.paths["detect"], payload)
        results = data.get("results", [])
        return [
            Regions(image_id=ref.image_id, regions=list(regions))
            for ref, regions in zip(refs, results)
        ]

    # -- health / cost --------------------------------------------------------
    def health(self) -> Health:
        """Ping the endpoint's health path; never raises."""
        try:
            resp = requests.get(
                f"{self.base_url}{self.paths['health']}",
                headers=self._headers(),
                timeout=5,
            )
            ok = bool(resp.ok)
            return Health(ok=ok, detail=f"{self.base_url} -> {resp.status_code}")
        except Exception as exc:  # network/DNS/timeout — report, don't raise
            return Health(ok=False, detail=f"{self.base_url} unreachable: {exc}")

    def cost_estimate(self, n: int, cap: Capability) -> CostEstimate:
        usd = round(self.usd_per_image * n, 4)
        return CostEstimate(usd=usd, n=n, capability=cap, detail=self.base_url)
