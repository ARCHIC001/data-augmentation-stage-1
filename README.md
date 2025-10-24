Weather Augmentation Pipeline (POV motorcycle)

- Purpose: Automate image → weather change → video for first-person motorcycle POV frames, with per-group consistency.

Quick start

- Install deps (optional virtualenv recommended):
  - `python3 -m pip install -r requirements.txt`
- Run rule-based weather augmentation:
  - `python3 -m weather_aug.cli configs/weather_batch.yaml`
- Export videos (1 fps):
  - `python3 scripts/export_videos.py`
- (Optional) Call Gemini 2.5 Flash Image for prompt-driven weather edits:
  - 设置 `GEMINI_API_KEY` 或在 `configs/gemini_api_key.txt` 中写入 key。
  - Customize standalone prompt files in `prompts/` and update `configs/gemini_weather.yaml`.
  - `python3 scripts/gemini_weather_pipeline.py configs/gemini_weather.yaml`
- Run single-image sample (input `input/test/0004.png` → 1344x768 outputs):
  - `python3 scripts/gemini_weather_sample.py`
- Batch convert folders (pairs per subfolder under `input/imgsource`):
  - `python3 scripts/gemini_weather_pairs.py`
- Prepare VEO 3.1 video generation (reads first/last frame, writes operation result):
  - Edit `configs/veo_video.yaml` (set frames, prompt, durations, etc.)
  - `python3 scripts/veo_video_generate.py configs/veo_video.yaml`
- Batch VEO videos from weather frames:
  - Populate prompts in `prompts/video/` and adjust `configs/veo_video_batch.yaml`
  - `python3 scripts/veo_video_batch.py`

Key ideas for consistency

- Same seed per group + variant; same params; optional tiny jitter.
- Geometry-preserving overlays (rain/fog/snow) avoid structural drift.

Next step (generative models)

- Use Stable Diffusion/ComfyUI with fixed seed, shared prompts/LoRA, ControlNet (canny/depth) to lock geometry; feed consecutive frames to a frames-to-video model for temporal coherence.

More details: `docs/WORKFLOW_AND_PROMPTS.md`.
