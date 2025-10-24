"""Batch VEO video generation using per-weather prompts and frame folders.

For each scene folder under `outputimg/`, this script locates weather variant
subfolders (e.g. `sunny`, `heavy_rain`) and uses the earliest and latest frame
files as references to generate a video via the VEO 3.1 API. Prompts for each
weather are loaded from YAML files similar to the image augmentation pipeline.

Usage:
    python3 scripts/veo_video_batch.py configs/veo_video_batch.yaml
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from google.genai import types
import yaml

try:
    from scripts.veo_video_generate import VideoJobConfig, run_generation
except ImportError:  # allow running as standalone script
    import sys

    current_dir = Path(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.append(str(current_dir))
    from veo_video_generate import VideoJobConfig, run_generation


@dataclass
class VariantConfig:
    name: str
    prompt_path: Path
    duration_seconds: Optional[int]
    aspect_ratio: Optional[str]
    resolution: Optional[str]
    use_first_frame_reference: Optional[bool]
    use_last_frame: Optional[bool]
    reference_type: Optional[str]


@dataclass
class BatchConfig:
    model_name: str
    api_key_path: Optional[Path]
    input_root: Path
    output_root: Path
    defaults: Dict[str, object]
    variants: List[VariantConfig]


def load_yaml(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_relative(base: Path, value: Optional[str]) -> Optional[Path]:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def load_batch_config(path: Path) -> BatchConfig:
    data = load_yaml(path)
    cfg_dir = path.parent

    variants: List[VariantConfig] = []
    for item in data.get("variants", []):
        variants.append(
            VariantConfig(
                name=item["name"],
                prompt_path=resolve_relative(cfg_dir, item["prompt_file"]),
                duration_seconds=item.get("duration_seconds"),
                aspect_ratio=item.get("aspect_ratio"),
                resolution=item.get("resolution"),
                use_first_frame_reference=item.get("use_first_frame_reference"),
                use_last_frame=item.get("use_last_frame"),
                reference_type=item.get("reference_type"),
            )
        )

    return BatchConfig(
        model_name=data.get("model_name", "models/veo-3.1-generate-preview"),
        api_key_path=resolve_relative(cfg_dir, data.get("api_key_path")),
        input_root=resolve_relative(cfg_dir, data.get("input_root") or "outputimg"),
        output_root=resolve_relative(cfg_dir, data.get("output_root") or "outputmp4"),
        defaults=data.get("defaults", {}),
        variants=variants,
    )


def load_prompt_text(path: Path) -> str:
    data = load_yaml(path)
    positive = data.get("positive", "").strip()
    negative = data.get("negative", "").strip()
    if negative:
        return f"{positive}\nNegative prompt: {negative}"
    return positive


def list_variant_frames(folder: Path) -> List[Path]:
    return sorted([p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}])


def pick_reference_frames(frames: List[Path]) -> tuple[Path, Optional[Path]]:
    if not frames:
        raise ValueError("No frames provided")
    first = frames[0]
    last = frames[-1]
    # Prefer explicit 0000 / 0008 style names if present
    for candidate in frames:
        if "0000" in candidate.stem:
            first = candidate
            break
    for candidate in reversed(frames):
        if "0008" in candidate.stem or "last" in candidate.stem.lower():
            last = candidate
            break
    return first, last if len(frames) > 1 else first


def group_folders(root: Path) -> Iterable[Path]:
    if not root or not root.exists():
        return []
    for path in sorted(p for p in root.iterdir() if p.is_dir()):
        yield path


def resolve_api_key(cfg: BatchConfig) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and cfg.api_key_path and cfg.api_key_path.exists():
        api_key = cfg.api_key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise EnvironmentError(
            "Gemini/VEO API key not provided. Set GEMINI_API_KEY or use api_key_path in config."
        )
    return api_key


def construct_job_config(
    batch_cfg: BatchConfig,
    api_key_path: Optional[Path],
    scene_name: str,
    variant_cfg: VariantConfig,
    first_frame: Path,
    last_frame: Optional[Path],
    prompt_text: str,
) -> VideoJobConfig:
    defaults = batch_cfg.defaults
    duration = int(variant_cfg.duration_seconds or defaults.get("duration_seconds", 6))
    aspect_ratio = variant_cfg.aspect_ratio or defaults.get("aspect_ratio")
    resolution = variant_cfg.resolution if variant_cfg.resolution is not None else defaults.get("resolution")
    poll_seconds = float(defaults.get("poll_interval_seconds", 10))

    use_first = (
        variant_cfg.use_first_frame_reference
        if variant_cfg.use_first_frame_reference is not None
        else bool(defaults.get("use_first_frame_reference", True))
    )
    use_last = (
        variant_cfg.use_last_frame
        if variant_cfg.use_last_frame is not None
        else bool(defaults.get("use_last_frame", False))
    )

    ref_type_name = variant_cfg.reference_type or defaults.get("reference_type", "ASSET")
    reference_type = types.VideoGenerationReferenceType[ref_type_name.upper()]

    output_dir = batch_cfg.output_root / scene_name / variant_cfg.name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{scene_name}_{variant_cfg.name}.mp4"

    return VideoJobConfig(
        model_name=batch_cfg.model_name,
        api_key_path=api_key_path,
        first_frame=first_frame,
        last_frame=last_frame if use_last else None,
        output_path=output_path,
        prompt=prompt_text,
        negative_prompt=None,
        duration_seconds=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        poll_interval_seconds=poll_seconds,
        reference_type=reference_type,
        use_first_frame_reference=use_first,
        use_last_frame=use_last and last_frame is not None,
    )


def process_scene_folder(batch_cfg: BatchConfig, scene_folder: Path) -> None:
    scene_name = scene_folder.name

    for variant in batch_cfg.variants:
        variant_folder = scene_folder / variant.name
        if not variant_folder.exists():
            continue

        frames = list_variant_frames(variant_folder)
        if not frames:
            continue

        first_frame, last_frame = pick_reference_frames(frames)

        prompt_text = load_prompt_text(variant.prompt_path)

        job_cfg = construct_job_config(
            batch_cfg=batch_cfg,
            api_key_path=batch_cfg.api_key_path,
            scene_name=scene_name,
            variant_cfg=variant,
            first_frame=first_frame,
            last_frame=last_frame,
            prompt_text=prompt_text,
        )

        if job_cfg.output_path.exists():
            continue

        run_generation(job_cfg)


def main(config_path: str = "configs/veo_video_batch.yaml") -> None:
    cfg = load_batch_config(Path(config_path))
    api_key = resolve_api_key(cfg)
    os.environ.setdefault("GEMINI_API_KEY", api_key)

    for scene in group_folders(cfg.input_root):
        process_scene_folder(cfg, scene)


if __name__ == "__main__":  # pragma: no cover
    parser = argparse.ArgumentParser(description="Batch VEO video generation")
    parser.add_argument(
        "config",
        nargs="?",
        default="configs/veo_video_batch.yaml",
        help="Path to batch configuration YAML",
    )
    args = parser.parse_args()
    main(args.config)
