"""
Vision Language Model (VLM) tagger for image analysis.
Supports multiple VLM backends: JoyCaption, Qwen2.5-VL-NSFW, Gemma 4, etc.
"""

import json
import logging
from pathlib import Path
from typing import Any

import requests
from PIL import Image

# Tag enum schema + validation extracted to pipeline.tag_schema — re-exported so
# existing imports (from pipeline.tagger import validate_and_correct_tags) and
# the OllamaTagger reference below keep resolving from this module's namespace.
from pipeline.tag_schema import (  # noqa: F401  (re-export facade)
    ALLOWED_ENUMS,
    REMAP,
    validate_and_correct_tags,
)

logger = logging.getLogger(__name__)


class BaseTagger:
    """Base class for VLM taggers."""

    def __init__(self, model_name: str, device: str = "mps"):
        self.model_name = model_name
        self.device = device
        self.model = None
        self.processor = None
        self.tokenizer = None

    def load_model(self):
        """Load model - to be implemented by subclasses."""
        raise NotImplementedError

    def analyze_image(self, image_path: Path) -> dict[str, Any]:
        """Analyze image and return structured tags."""
        raise NotImplementedError

    def batch_analyze(self, image_paths: list[Path]) -> list[dict[str, Any]]:
        """Analyze multiple images."""
        results = []
        for img_path in image_paths:
            try:
                result = self.analyze_image(img_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Error analyzing {img_path}: {e}")
                results.append({"error": str(e), "path": str(img_path)})
        return results


class OllamaTagger(BaseTagger):
    """Tagger using Ollama with multimodal models."""

    def __init__(self, model_name: str = "qwen2.5vl:7b-8k", device: str = "cpu"):
        super().__init__(model_name, device)
        self.ollama_url = "http://localhost:11434/api/generate"

    def load_model(self):
        # Check if Ollama is running
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                available = any(
                    m.get("name", "").startswith(self.model_name.split(":")[0])
                    for m in models
                )
                if not available:
                    logger.warning(
                        f"Model {self.model_name} may not be available in Ollama"
                    )
                return True
            else:
                logger.error(f"Ollama not responding: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            return False

    def analyze_image(self, image_path: Path) -> dict[str, Any]:
        import base64

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Prepare prompt
        prompt = """Analyze this image thoroughly and return ONLY valid JSON with these exact keys:
{
  "person": "name or unknown",
  "clothing": ["list", "of", "clothing", "items"],
  "content_type": "portrait/full_body/closeup/bodyscape/group",
  "pose": "standing/sitting/reclining/kneeling/leaning/laying",
  "composition": "headshot/half_body/three_quarter/full_body/wide",
  "setting": "indoor/outdoor/studio/urban/nature/domestic",
  "location": "bedroom/living_room/bathroom/kitchen/beach/pool/forest/street/car/office/gym/mirror_selfie",
  "lighting": "natural/studio/soft/harsh/golden_hour/dim/bright/backlit",
  "mood": "candid/posed/casual/glamour/artistic/intimate/playful",
  "rating": "sfw/suggestive/nsfw",
  "tags": ["descriptive", "keywords", "e.g.", "mirror_selfie", "lingerie"],
  "caption": "detailed objective description",
  "confidence": 0.85
}

CONFIDENCE: Rate your overall confidence in the analysis from 0.0 (guessing) to 1.0 (certain). Be honest — complex/ambiguous images should get lower scores.

RULES:
- rating: "nsfw" = explicit nudity/sexual content. "suggestive" = revealing but not explicit. "sfw" = fully clothed.
- content_type: "bodyscape" = body-focused abstract. "portrait" = face-focused. "full_body" = entire body visible.
- composition: "headshot" = head+shoulders. "half_body" = waist up. "three_quarter" = knees up. "full_body" = head to toe.
- person: Use the most likely name. Say "unknown" if unsure.
- Return ONLY the JSON object, no markdown, no explanation."""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": [image_data],
            "stream": False,
            "keep_alive": -1,
            "options": {"temperature": 0.1, "num_predict": 512},
        }

        try:
            response = requests.post(self.ollama_url, json=payload, timeout=240)
            response.raise_for_status()

            result_text = response.json().get("response", "")

            # Parse JSON
            try:
                # Find JSON in response
                start_idx = result_text.find("{")
                end_idx = result_text.rfind("}") + 1
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = result_text[start_idx:end_idx]
                    result = json.loads(json_str)
                else:
                    result = {"raw_response": result_text, "error": "No JSON found"}
            except json.JSONDecodeError as e:
                result = {
                    "raw_response": result_text,
                    "error": f"JSON parse error: {e}",
                }

            # Validate and correct enum values
            if "error" not in result:
                result, corrections = validate_and_correct_tags(result)
                if corrections:
                    result["_corrections"] = corrections
                    logger.info(f"Enum corrections for {image_path}: {corrections}")

            result["path"] = str(image_path)
            return result

        except Exception as e:
            logger.error(f"Ollama API error for {image_path}: {e}")
            return {"path": str(image_path), "error": str(e)}


class FallbackTagger(BaseTagger):
    """Fallback tagger using basic image analysis when VLM is not available."""

    def load_model(self):
        return True  # No model to load

    def analyze_image(self, image_path: Path) -> dict[str, Any]:
        """Basic image analysis without VLM."""

        try:
            with Image.open(image_path) as img:
                width, height = img.size
                format = img.format

                # Basic heuristic analysis
                aspect_ratio = width / height if height > 0 else 0

                if aspect_ratio > 1.5:
                    content_type = "landscape"
                elif aspect_ratio < 0.67:
                    content_type = "portrait"
                else:
                    content_type = "square"

                # Person extraction from path is intentionally disabled: the
                # hardcoded list of subject names was removed for privacy.
                person = "unknown"
                _KNOWN_SUBJECTS: set[str] = set()  # deliberately empty
                path_parts = Path(image_path).parts
                for part in path_parts:
                    if part in _KNOWN_SUBJECTS:
                        person = part
                        break

                result = {
                    "person": person,
                    "clothing": ["unknown"],
                    "content_type": content_type,
                    "setting": "unknown",
                    "rating": "unknown",
                    "tags": [f"size_{width}x{height}", f"format_{format}"],
                    "caption": f"{format} image {width}x{height}",
                    "path": str(image_path),
                }
                return result

        except Exception as e:
            logger.error(f"Error analyzing {image_path}: {e}")
            return {"path": str(image_path), "error": str(e)}


class VLMFactory:
    """Factory to create appropriate tagger based on configuration."""

    @staticmethod
    def create_tagger(config: dict[str, Any]) -> BaseTagger:
        """Create tagger instance based on config."""
        model_type = config.get("vlm", {}).get("model", "fallback")
        device = config.get("vlm", {}).get("device", "mps")

        if model_type.lower() == "ollama":
            model_name = config.get("vlm", {}).get("ollama_model", "qwen2.5vl:7b")
            return OllamaTagger(model_name, device)
        else:
            logger.warning(f"Using fallback tagger for model: {model_type}")
            return FallbackTagger("fallback", device)


def main():
    """Test the tagger."""
    import argparse
    from pathlib import Path

    import yaml

    parser = argparse.ArgumentParser(description="Test VLM tagger")
    parser.add_argument("--config", default="config.yaml", help="Configuration file")
    parser.add_argument("--image", required=True, help="Image to analyze")
    parser.add_argument("--output", help="Output JSON file")
    args = parser.parse_args()

    # Load config
    with open(args.config) as f:
        config = yaml.safe_load(f)

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Create tagger
    tagger = VLMFactory.create_tagger(config)

    # Analyze image
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        return

    print(f"Analyzing {image_path}...")
    result = tagger.analyze_image(image_path)

    # Output result
    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Saved to {args.output}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
