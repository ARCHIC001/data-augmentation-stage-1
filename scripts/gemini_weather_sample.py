"""Sample runner for Gemini weather prompts on a single image.

This script demonstrates how to call Gemini 2.5 Flash Image via the
`google-generativeai` client library for one source frame
(`input/test/0004.png`). For each weather variant defined in
`configs/gemini_weather.yaml` it applies the corresponding prompt and writes
the edited result to `outputimg/<variant>/0004_<variant>.png` at 1344x768.

Usage:
    python3 scripts/gemini_weather_sample.py

The script requires a Gemini API key. Either export `GEMINI_API_KEY` or place
the key inside the file referenced by `api_key_path` in the YAML config.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from google import genai
from google.genai import types
import yaml
from PIL import Image


CONFIG_PATH = Path("configs/gemini_weather.yaml")
SOURCE_IMAGE = Path("input/test/0004.png")
OUTPUT_ROOT = Path("outputimg")


@dataclass
class PromptTemplate:
    positive: str
    negative: str


@dataclass
class Variant:
    name: str
    prompt_file: Path
    creativity: float
    fidelity: float


@dataclass
class AppConfig:
    model_name: str
    output_width: int
    output_height: int
    api_key_path: Optional[Path]
    variants: Dict[str, Variant]


def load_yaml(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(config_path: Path = CONFIG_PATH) -> AppConfig:
    raw = load_yaml(config_path)
    cfg_dir = config_path.parent

    variants: Dict[str, Variant] = {}
    for item in raw.get("variants", []):
        variants[item["name"]] = Variant(
            name=item["name"],
            prompt_file=(cfg_dir / Path(item["prompt_file"])).resolve(),
            creativity=float(item.get("creativity", 0.2)),
            fidelity=float(item.get("fidelity", 0.7)),
        )

    api_path: Optional[Path] = None
    if raw.get("api_key_path"):
        api_path = (cfg_dir / Path(raw["api_key_path"])).resolve()

    return AppConfig(
        model_name=raw.get("model_name", "gemini-2.5-flash-image"),
        output_width=int(raw.get("output_width", 1344)),
        output_height=int(raw.get("output_height", 768)),
        api_key_path=api_path,
        variants=variants,
    )


def load_prompt(template_path: Path) -> PromptTemplate:
    data = load_yaml(template_path)
    return PromptTemplate(
        positive=data["positive"].strip(),
        negative=data["negative"].strip(),
    )


def read_image(path: Path) -> bytes:
    with path.open("rb") as f:
        return f.read()


def call_gemini_edit(
    client: genai.Client,
    model_name: str,
    prompt_text: str,
    image_bytes: bytes,
    creativity: float,
    fidelity: float,
    width: int,
    height: int,
) -> bytes:
    contents = [
        types.Part(text=prompt_text),
        types.Part(inline_data=types.Blob(data=image_bytes, mime_type="image/png")),
    ]

    config = types.GenerateContentConfig(
        temperature=creativity,
        top_p=0.9,
        top_k=40,
    )

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )

    raw_bytes: Optional[bytes] = None

    for candidate in response.candidates or []:
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                raw_bytes = part.inline_data.data
                break
        if raw_bytes is not None:
            break

    if raw_bytes is None:
        raise RuntimeError("No image data returned by Gemini")

    with Image.open(io.BytesIO(raw_bytes)) as img:
        img = img.convert("RGB")
        if img.size != (width, height):
            img = img.resize((width, height), Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()


def main() -> None:
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(f"Source image not found: {SOURCE_IMAGE}")

    config = load_config()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and config.api_key_path and config.api_key_path.exists():
        api_key = config.api_key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise EnvironmentError(
            "Gemini API key not provided. Set GEMINI_API_KEY or populate the file configured in api_key_path."
        )

    client = genai.Client(api_key=api_key)

    image_bytes = read_image(SOURCE_IMAGE)

    for variant in config.variants.values():
        prompt = load_prompt(variant.prompt_file)
        prompt_text = f"{prompt.positive}\nNegative prompt: {prompt.negative}"

        result_bytes = call_gemini_edit(
            client=client,
            model_name=config.model_name,
            prompt_text=prompt_text,
            image_bytes=image_bytes,
            creativity=variant.creativity,
            fidelity=variant.fidelity,
            width=config.output_width,
            height=config.output_height,
        )

        out_dir = OUTPUT_ROOT / variant.name
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"0004_{variant.name}.png"
        output_path.write_bytes(result_bytes)
        print(f"Saved: {output_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
