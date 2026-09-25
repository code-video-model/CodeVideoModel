"""GPT-Image-2 strict appearance, text-guided generation, or single-anchor editing."""
import base64
import io
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from PIL import Image

from . import IMAGE_MODEL
from .pair import TYPES

ENDPOINT = "https://openrouter.ai/api/v1/images"
REFERENCE_SIZE = (1536, 864)


def payload(frame: Path, *, edit: str | None = None, pair_type: str | None = None,
            group_id: str = "pair", variant: str = "target",
            text_prompt: str | None = None) -> dict:
    encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
    if (edit is None) != (pair_type is None):
        raise ValueError("Supply both a pair type and the requested image edit.")
    if text_prompt is not None and (edit is not None or pair_type is not None):
        raise ValueError("Text-guided reference generation cannot be combined with Pair editing.")
    prompts = Path(__file__).resolve().parents[1] / "prompts"
    if text_prompt is not None:
        if not text_prompt.strip():
            raise ValueError("The text prompt must not be empty.")
        prompt = (prompts / "reference_guided.txt").read_text().strip()
        prompt += "\n\nScene intent:\n" + text_prompt.strip()
    elif edit is None:
        prompt = (prompts / "reference.txt").read_text().strip()
    else:
        if pair_type not in TYPES or not edit.strip():
            raise ValueError("Pair editing requires a supported type and a non-empty edit.")
        template = json.loads((prompts / "reference_pair.json").read_text())
        prompt = (
            f"{template['instruction']} {template['rules'][pair_type]} "
            f"Group: {group_id}. Target variant: {variant}. Pair type: {pair_type}."
            " Retain the supplied anchor's existing photographic style, "
            "exposure, materials, and grade. Do not restyle it."
            " Correct the following previously observed visual failure while "
            "preserving every other reference-role and pair constraint: "
            f"{edit.strip()}"
        )
    with Image.open(frame) as image:
        if image.format not in ("PNG", "JPEG", "WEBP"):
            raise ValueError("Expected a PNG, JPEG or WebP reference.")
        mime = Image.MIME[image.format]
        size = image.size if pair_type is not None else REFERENCE_SIZE
    return {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "input_references": [{"type": "image_url", "image_url": {
            "url": f"data:{mime};base64,{encoded}"}}],
        "size": f"{size[0]}x{size[1]}",
        "quality": "medium",
        "n": 1,
        "provider": {"only": ["openai"], "allow_fallbacks": False},
    }


def generate(frame: Path, output: Path, *, edit: str | None = None,
             pair_type: str | None = None, group_id: str = "pair",
             variant: str = "target", text_prompt: str | None = None) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to repeat a paid edit over {output}")
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("Set OPENROUTER_API_KEY in your environment.")
    request_data = payload(frame, edit=edit, pair_type=pair_type,
                           group_id=group_id, variant=variant, text_prompt=text_prompt)
    expected_size = tuple(int(value) for value in request_data["size"].split("x"))
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(request_data).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GPT-Image-2 request failed: HTTP {error.code}") from error
    data = result.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ValueError("GPT-Image-2 returned no image.")
    encoded = data[0].get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("GPT-Image-2 returned no base64 image.")
    raw = base64.b64decode(encoded, validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.size != expected_size:
            raise ValueError(
                f"GPT-Image-2 returned {image.width}x{image.height}; "
                f"requested {expected_size[0]}x{expected_size[1]}. No resizing was applied."
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            image.convert("RGB").save(stream, format="PNG")
