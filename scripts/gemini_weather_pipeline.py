"""Batch weather augmentation via Gemini 2.5 Flash Image API.

This script reads a YAML configuration listing standalone prompt files for each
weather scenario, assembles the structured prompt, and sends edit requests for
every image located under the input directory. Enhanced frames are written to
`<output_root>/<variant>/<relative_path>` to keep grouping consistent.

Usage:
    python3 scripts/gemini_weather_pipeline.py configs/gemini_weather.yaml

Requirements:
    - google-genai >= 1.46.0
    - Set environment variable GEMINI_API_KEY with a valid key (or use api_key_path).

The script is intentionally not executed automatically; run it manually after
reviewing configuration and ensuring the API key is available.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml
from PIL import Image

try:
    from google import genai
    from google.genai import types
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "google-genai package is required. Install with `pip install google-genai`."
    ) from exc


DEFAULT_RATE_LIMIT_QPS = 0.5  # Adjust to respect project quota
MAX_RETRIES = 3


@dataclass
class VariantConfig:
    name: str
    prompt_path: Path
    creativity: float
    fidelity: float


@dataclass
class PromptTemplate:
    positive: str
    negative: str


@dataclass
class PipelineConfig:
    input_root: Path
    output_root: Path
    api_key_path: Optional[Path]
    model_name: str
    output_width: int
    output_height: int
    variants: List[VariantConfig]


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def load_config(path: Path) -> PipelineConfig:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cfg_dir = path.parent

    variants: List[VariantConfig] = []
    for item in data.get("variants", []):
        variants.append(
            VariantConfig(
                name=item["name"],
                prompt_path=_resolve_path(cfg_dir, item["prompt_file"]),
                creativity=float(item.get("creativity", 0.2)),
                fidelity=float(item.get("fidelity", 0.7)),
            )
        )

    input_root = _resolve_path(cfg_dir, data["input_root"])
    output_root = _resolve_path(cfg_dir, data["output_root"])
    api_key_path = None
    if data.get("api_key_path"):
        api_key_path = _resolve_path(cfg_dir, data["api_key_path"])

    model_name = data.get("model_name", "gemini-2.5-flash-image")
    output_width = int(data.get("output_width", 1024))
    output_height = int(data.get("output_height", 1024))

    return PipelineConfig(
        input_root=input_root,
        output_root=output_root,
        api_key_path=api_key_path,
        model_name=model_name,
        output_width=output_width,
        output_height=output_height,
        variants=variants,
    )


def load_prompt_template(path: Path) -> PromptTemplate:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return PromptTemplate(
        positive=data["positive"].strip(),
        negative=data["negative"].strip(),
    )


def build_prompt(template: PromptTemplate) -> str:
    return f"{template.positive}\nNegative prompt: {template.negative}"


def read_image(path: Path) -> bytes:
    with path.open("rb") as f:
        return f.read()


def call_gemini_edit(
    client: genai.Client,
    model_name: str,
    prompt: str,
    image_bytes: bytes,
    creativity: float,
    fidelity: float,
    width: int,
    height: int,
) -> bytes:
    contents = [
        types.Part(text=prompt),
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


def iter_images(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            yield path


def process_images(cfg: PipelineConfig, rate_limit_qps: float = DEFAULT_RATE_LIMIT_QPS) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and cfg.api_key_path and cfg.api_key_path.exists():
        api_key = cfg.api_key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise EnvironmentError(
            "Gemini API key not provided. Set GEMINI_API_KEY or populate the file configured in api_key_path."
        )

    client = genai.Client(api_key=api_key)

    delay = 1.0 / max(rate_limit_qps, 1e-6)

    prompt_cache: Dict[Path, PromptTemplate] = {}

    for variant in cfg.variants:
        template = prompt_cache.get(variant.prompt_path)
        if template is None:
            template = load_prompt_template(variant.prompt_path)
            prompt_cache[variant.prompt_path] = template
        prompt = build_prompt(template)

        for img_path in iter_images(cfg.input_root):
            relative = img_path.relative_to(cfg.input_root)
            out_dir = cfg.output_root / variant.name / relative.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / (relative.stem + "_" + variant.name + ".png")

            if out_path.exists():
                continue  # skip already processed

            image_bytes = read_image(img_path)

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    result_bytes = call_gemini_edit(
                        client=client,
                        model_name=cfg.model_name,
                        prompt=prompt,
                        image_bytes=image_bytes,
                        creativity=variant.creativity,
                        fidelity=variant.fidelity,
                        width=cfg.output_width,
                        height=cfg.output_height,
                    )
                    out_path.write_bytes(result_bytes)
                    break
                except Exception as exc:
                    if attempt == MAX_RETRIES:
                        raise
                    time.sleep(delay * attempt)

            time.sleep(delay)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch weather edit via Gemini 2.5 Flash Image")
    parser.add_argument(
        "config",
        type=Path,
        help="Path to YAML configuration file (e.g. configs/gemini_weather.yaml)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=DEFAULT_RATE_LIMIT_QPS,
        help="Maximum requests per second to Gemini API (default: 0.5)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    cfg = load_config(args.config)
    process_images(cfg, rate_limit_qps=args.rate_limit)


if __name__ == "__main__":  # pragma: no cover
    main()
