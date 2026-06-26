"""
Generate and cache smart-cropped thumbnails for media images.
Uses pyvips with Pillow fallback for attention-based cropping.
"""

import hashlib
import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# pyvips is optional (smart-crop). Pillow is the always-available fallback.
# Declared `Any` up-front so the module-level assignment to None (when the import
# fails) still types as Any, not None — keeps attribute access pyright-clean.
pyvips: Any = None
HAS_VIPS = False

try:
    import pyvips  # noqa: E402  (optional dep, imported after declarations)

    # Verify libvips actually loads by touching the API
    _ = pyvips.Image.new_from_file
    HAS_VIPS = True
    logger.info("pyvips loaded — smart-crop thumbnails enabled")
except (ImportError, OSError) as e:
    logger.warning(f"pyvips unavailable ({e}), falling back to Pillow")


class ThumbnailCache:
    """Lazy thumbnail generation with filesystem caching."""

    def __init__(self, cache_dir: Path, quality: int = 80, fmt: str = "webp"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.quality = quality
        self.fmt = fmt

    def get(self, image_path: Path, w: int, h: int, fit: str = "cover") -> Path | None:
        """Get cached thumbnail or generate one. Returns path to file."""
        key = hashlib.md5(f"{image_path}_{w}x{h}_{fit}".encode()).hexdigest()
        cache_path = self.cache_dir / f"{key}.{self.fmt}"

        if cache_path.exists():
            return cache_path

        try:
            self._generate(image_path, cache_path, w, h, fit)
            return cache_path if cache_path.exists() else None
        except Exception as e:
            logger.error(f"Thumbnail failed: {image_path} -> {e}")
            return None

    def _generate(self, src: Path, dst: Path, w: int, h: int, fit: str):
        if HAS_VIPS:
            self._generate_vips(src, dst, w, h, fit)
        else:
            self._generate_pillow(src, dst, w, h, fit)

    def _generate_vips(self, src: Path, dst: Path, w: int, h: int, fit: str):
        img = pyvips.Image.new_from_file(str(src), access="sequential")
        thumb = img.thumbnail_image(
            w, height=h, crop="attention" if fit == "cover" else "none"
        )
        thumb.write_to_file(str(dst), Q=self.quality)

    def _generate_pillow(self, src: Path, dst: Path, w: int, h: int, fit: str):
        with Image.open(src) as img:
            if img.mode in ("RGBA", "LA", "P"):
                if img.mode == "P":
                    img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (10, 12, 16))
                if img.mode == "RGBA":
                    bg.paste(img, mask=img.split()[3])
                else:
                    bg.paste(img)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            if fit == "cover":
                thumb = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
            else:
                img.thumbnail((w, h), Image.Resampling.LANCZOS)
                thumb = Image.new("RGB", (w, h), (10, 12, 16))
                thumb.paste(img, ((w - img.width) // 2, (h - img.height) // 2))

            thumb.save(dst, format="WEBP", quality=self.quality)
