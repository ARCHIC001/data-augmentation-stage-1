"""Generate POV motorcycle video clips with VEO 3.1 using Gemini video API.

This script prepares a video generation job that uses a first-person
motorcycle frame as both the initial reference and an optional last-frame
constraint. Configuration is supplied via a YAML file (default
`configs/veo_video.yaml`). The script does **not** execute automatically; run it
manually after editing the config and providing your API key.

Usage:
    python3 scripts/veo_video_generate.py configs/veo_video.yaml

Prerequisites:
    - `google-genai` >= 1.46.0 (`pip install google-genai`)
    - API key stored in `GEMINI_API_KEY` or the file referenced by
      `api_key_path` in the YAML config.
    - Valid first/last frame image paths.
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
import yaml
from google import genai
from google.genai import types


DEFAULT_POLL_SECONDS = 10


@dataclass
class VideoJobConfig:
    model_name: str
    api_key_path: Optional[Path]
    first_frame: Optional[Path]
    last_frame: Optional[Path]
    output_path: Path
    prompt: str
    negative_prompt: Optional[str]
    duration_seconds: int
    aspect_ratio: Optional[str]
    resolution: Optional[str]
    poll_interval_seconds: float
    reference_type: types.VideoGenerationReferenceType
    use_first_frame_reference: bool
    use_last_frame: bool = False


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def load_config(path: Path) -> VideoJobConfig:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cfg_dir = path.parent

    api_key_path = data.get("api_key_path")
    api_key_path_resolved = _resolve_path(cfg_dir, api_key_path) if api_key_path else None

    reference_type_str = data.get("reference_type", "ASSET").upper()
    try:
        reference_type = types.VideoGenerationReferenceType[reference_type_str]
    except KeyError as exc:
        raise ValueError(f"Invalid reference_type: {reference_type_str}") from exc

    return VideoJobConfig(
        model_name=data.get("model_name", "veo-3.1"),
        api_key_path=api_key_path_resolved,
        first_frame=_resolve_path(cfg_dir, data["first_frame"]) if data.get("first_frame") else None,
        last_frame=_resolve_path(cfg_dir, data["last_frame"]) if data.get("last_frame") else None,
        output_path=_resolve_path(cfg_dir, data["output_path"]),
        prompt=data["prompt"].strip(),
        negative_prompt=data.get("negative_prompt", "").strip() or None,
        duration_seconds=int(data.get("duration_seconds", 6)),
        aspect_ratio=data.get("aspect_ratio"),
        resolution=data.get("resolution"),
        poll_interval_seconds=float(data.get("poll_interval_seconds", DEFAULT_POLL_SECONDS)),
        reference_type=reference_type,
        use_first_frame_reference=bool(data.get("use_first_frame_reference", False)),
        use_last_frame=bool(data.get("use_last_frame", False)),
    )


def read_image_bytes(path: Path) -> bytes:
    if path is None:
        raise ValueError("Image path is None")
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    with path.open("rb") as f:
        return f.read()


def build_generate_videos_config(
    cfg: VideoJobConfig,
    first_bytes: Optional[bytes],
    last_bytes: Optional[bytes],
) -> types.GenerateVideosConfig:
    config_kwargs = {
        "duration_seconds": cfg.duration_seconds,
    }
    if cfg.aspect_ratio:
        config_kwargs["aspect_ratio"] = cfg.aspect_ratio
    if cfg.resolution:
        config_kwargs["resolution"] = cfg.resolution
    if cfg.negative_prompt:
        config_kwargs["negative_prompt"] = cfg.negative_prompt

    if cfg.use_last_frame and last_bytes is not None:
        config_kwargs["last_frame"] = types.Image(
            image_bytes=last_bytes,
            mime_type="image/png",
        )

    if cfg.use_first_frame_reference and first_bytes is not None:
        config_kwargs["reference_images"] = [
            types.VideoGenerationReferenceImage(
                image=types.Image(image_bytes=first_bytes, mime_type="image/png"),
                reference_type=cfg.reference_type,
            )
        ]

    return types.GenerateVideosConfig(**config_kwargs)


def run_generation(cfg: VideoJobConfig) -> Path:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and cfg.api_key_path and cfg.api_key_path.exists():
        api_key = cfg.api_key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise EnvironmentError(
            "Gemini/VEO API key not provided. Set GEMINI_API_KEY or populate the file referenced in api_key_path."
        )

    client = genai.Client(api_key=api_key)

    first_bytes = read_image_bytes(cfg.first_frame) if cfg.first_frame else None
    last_bytes = read_image_bytes(cfg.last_frame) if cfg.last_frame else None

    prompt_text = cfg.prompt

    source_kwargs = {"prompt": prompt_text}
    if first_bytes is not None:
        source_kwargs["image"] = types.Image(image_bytes=first_bytes, mime_type="image/png")
    source = types.GenerateVideosSource(**source_kwargs)

    video_config = build_generate_videos_config(cfg, first_bytes, last_bytes)

    operation = client.models.generate_videos(
        model=cfg.model_name,
        source=source,
        config=video_config,
    )

    print(f"Submitted video generation operation: {operation.name}")

    while not operation.done:
        time.sleep(cfg.poll_interval_seconds)
        operation = client.operations.get(operation)
        status = "done" if operation.done else "running"
        print(f"Polling operation {operation.name}: {status}")

    if operation.error:
        raise RuntimeError(f"Video generation failed: {operation.error}")

    result = operation.result
    if not result or not result.generated_videos:
        raise RuntimeError("No video content returned from operation")

    video = result.generated_videos[0].video
    if video.video_bytes:
        output_path = cfg.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as f:
            f.write(video.video_bytes)
        print(f"Saved video to {output_path}")
        return output_path
    if video.uri:
        output_path = cfg.output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {"x-goog-api-key": api_key}
        response = requests.get(video.uri, headers=headers, timeout=300)
        response.raise_for_status()
        with output_path.open("wb") as f:
            f.write(response.content)
        print(f"Downloaded video from URI to {output_path}")
        return output_path

    raise RuntimeError("Video response missing data and URI")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate POV motorcycle video with VEO 3.1")
    parser.add_argument(
        "config",
        type=Path,
        nargs="?",
        default=Path("configs/veo_video.yaml"),
        help="Path to YAML configuration file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    run_generation(cfg)


if __name__ == "__main__":  # pragma: no cover
    main()
