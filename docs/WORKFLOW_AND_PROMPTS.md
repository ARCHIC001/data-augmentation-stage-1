# Weather Augmentation Workflow

- 输入关键帧：`input/<group_id>/0000.png` 形式按组存放。
- 输出目录：
  - 传统增强（OpenCV）→ `outputimg/<组>/<variant>/`
  - Gemini API 增强 → `outputimg/<variant>/<…>`（由脚本自动创建）

## 脚本入口

- 传统确定性增强：`python3 -m weather_aug.cli configs/weather_batch.yaml`
- Gemini 2.5 Flash Image 批处理：
  1. 设置环境变量 `GEMINI_API_KEY` 或在 `configs/gemini_api_key.txt` 中填入 key
  2. 按需编辑独立 prompt 文件（`prompts/*.yaml`）
  3. 调整 `configs/gemini_weather.yaml`（指向对应 prompt 文件）
  4. 运行 `python3 scripts/gemini_weather_pipeline.py configs/gemini_weather.yaml`
- Gemini 样例（对 `input/test/0004.png` 出 1344x768 图像）：`python3 scripts/gemini_weather_sample.py`
- VEO 3.1 视频生成：
  1. 编辑 `configs/veo_video.yaml`（首帧/尾帧路径、prompt、时长、fps 等）
  2. 设置 API key（环境变量或 `configs/gemini_api_key.txt`）
  3. 运行 `python3 scripts/veo_video_generate.py configs/veo_video.yaml`
- VEO 批量视频（基于 `outputimg/<scene>/<weather>/` 帧）
  1. 为视频场景准备 prompt 文件（`prompts/video/*.yaml`）
  2. 编辑 `configs/veo_video_batch.yaml`（模型、默认参数、变体映射）
  3. 运行 `python3 scripts/veo_video_batch.py`
- Gemini 批量天气（按文件夹、成对处理）：
  1. 将待处理图片按子文件夹放在 `input/imgsource/<scene>/`
  2. 编辑 `configs/gemini_weather.yaml`（prompt/参数）
  3. 运行 `python3 scripts/gemini_weather_pairs.py`
- 视频合成（1 fps 校验）：`python3 scripts/export_videos.py`

## Gemini Prompt 结构

脚本自动读取 `prompts/<scene>.yaml`，每个文件包含：

1. `positive`：场景描述、几何保持、光照/天气特征。
2. `negative`：约束不允许的变化（新增物体、布局漂移、伪影等）。

同一场景的所有帧共享该 prompt 文件，脚本自动拼接 `Positive + Negative`。

## 一致性策略

- 组内同 Prompt + 同风格参考（如配置）。
- 降低 `creativity`、提高 `fidelity`（YAML 中控制）。
- 如需保护区域，可在脚本中扩展掩膜合成逻辑。
- 后处理可做色彩匹配、光流一致性检查（留待后续扩展）。

## 后续扩展建议

- 自定义 `style_root` 放置参考风格图；脚本会在 variant 中引用。
- 加入光流扭曲的上一帧作为附加条件（若 Gemini 开放），或在本地做一致性验证。
- 对输出做 SSIM/ΔE 的组内统计，用于回归检测。
