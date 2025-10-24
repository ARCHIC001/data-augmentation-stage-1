"""Batch weather augmentation for folders using Gemini 2.5 Flash Image.

For every immediate subdirectory under `input/imgsource`, this script
processes each image independently while sharing the same prompt per weather
variant, ensuring consistent textual guidance without reusing generated pixels.

Outputs are written to `outputimg/<subfolder>/<variant>/<filename>.png`.

Usage:
    python3 scripts/gemini_weather_pairs.py configs/gemini_weather.yaml

Requirements:
    - google-genai >= 1.46.0
    - Pillow
    - API key supplied via `GEMINI_API_KEY` or the `api_key_path` in the
      configuration.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from google import genai
from google.genai import types
from PIL import Image
import yaml


INPUT_ROOT = Path("input/imgsource")
OUTPUT_ROOT = Path("outputimg")


@dataclass
class PromptTemplate:
    positive: str
    negative: str


@dataclass
class VariantConfig:
    name: str
    prompt_path: Path
    creativity: float
    fidelity: float


@dataclass
class AppConfig:
    model_name: str
    output_width: int
    output_height: int
    api_key_path: Optional[Path]
    variants: List[VariantConfig]


def load_yaml(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_relative(base: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def load_config(path: Path) -> AppConfig:
    data = load_yaml(path)
    cfg_dir = path.parent

    variants: List[VariantConfig] = []
    for item in data.get("variants", []):
        variants.append(
            VariantConfig(
                name=item["name"],
                prompt_path=resolve_relative(cfg_dir, item["prompt_file"]),
                creativity=float(item.get("creativity", 0.2)),
                fidelity=float(item.get("fidelity", 0.7)),
            )
        )

    api_path = data.get("api_key_path")
    api_key_path = resolve_relative(cfg_dir, api_path) if api_path else None

    return AppConfig(
        model_name=data.get("model_name", "gemini-2.5-flash-image"),
        output_width=int(data.get("output_width", 1344)),
        output_height=int(data.get("output_height", 768)),
        api_key_path=api_key_path,
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
    parts = [
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
        contents=parts,
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


def iter_subfolders(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    for path in sorted(p for p in root.iterdir() if p.is_dir()):
        yield path


def process_folder(
    client: genai.Client,
    cfg: AppConfig,
    folder: Path,
    prompt_cache: Dict[Path, PromptTemplate],
) -> None:
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if not images:
        return

    for variant in cfg.variants:
        template = prompt_cache.get(variant.prompt_path)
        if template is None:
            template = load_prompt(variant.prompt_path)
            prompt_cache[variant.prompt_path] = template
        prompt_text = f"{template.positive}\nNegative prompt: {template.negative}"

        out_base = OUTPUT_ROOT / folder.name / variant.name
        out_base.mkdir(parents=True, exist_ok=True)

        for img_path in images:
            raw = read_image(img_path)
            result_bytes = call_gemini_edit(
                client=client,
                model_name=cfg.model_name,
                prompt_text=prompt_text,
                image_bytes=raw,
                creativity=variant.creativity,
                fidelity=variant.fidelity,
                width=cfg.output_width,
                height=cfg.output_height,
            )

            out_path = out_base / f"{img_path.stem}_{variant.name}.png"
            out_path.write_bytes(result_bytes)


def main(config_path: str = "configs/gemini_weather.yaml") -> None:
    cfg = load_config(Path(config_path))

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and cfg.api_key_path and cfg.api_key_path.exists():
        api_key = cfg.api_key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise EnvironmentError(
            "Gemini API key not provided. Set GEMINI_API_KEY or populate the file configured in api_key_path."
        )

    client = genai.Client(api_key=api_key)
    prompt_cache: Dict[Path, PromptTemplate] = {}

    for folder in iter_subfolders(INPUT_ROOT):
        process_folder(client, cfg, folder, prompt_cache)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Batch weather augmentation for folder pairs")
    parser.add_argument(
        "config",
        nargs="?",
        default="configs/gemini_weather.yaml",
        help="Path to YAML configuration file",
    )
    args = parser.parse_args()
    main(args.config)
