# 项目介绍：POV 场景的批量天气增强与视频生成

本项目实现“输入关键帧 → 批量改换天气 → 生成视频”的整套自动化流程，针对摩托车第一人称（POV）视角场景优化，重点保证：
- 保留原图几何与交通要素（道路标线、交通标志、车辆）的位置与可读性；
- 组内帧的一致性（天气强度、色调、光照），同时避免帧间构图被相互“粘连”；
- 批量可复现、可配置，prompt 与参数尽量结构化。

---

## 功能总览
- 批量天气增强（Gemini 2.5 Flash Image）：
  - 独立逐帧生成，按天气变体应用结构化 prompt；
  - 按 `outputimg/<scene>/<weather>/<frame>_<weather>.png` 输出，便于后续视频拼接或评估；
  - 提供每种天气的 prompt 模板（正向/负向），可快速扩展与微调。
- 批量视频生成（VEO 3.1）：
  - 从 `outputimg/<scene>/<weather>/` 选取参考帧（优先 `0000*` 和 `0008*`），并使用首帧作为结构参考生成视频；
  - 统一时长（默认 8 秒）与比例（16:9），输出 `outputmp4/<scene>/<weather>/<scene>_<weather>.mp4`。

---

## 目录结构
```
input/                      # 原始抽帧（或按需自定义）
outputimg/                  # 天气增强后的帧输出
  └─ <scene>/<weather>/
       ├─ 0000_<weather>.png
       └─ 0008_<weather>.png
outputmp4/                  # 视频输出
configs/                    # 统一配置文件
  ├─ gemini_api_key.txt     # API Key（或使用环境变量 GEMINI_API_KEY）
  ├─ gemini_weather.yaml    # 天气增强批处理配置
  ├─ veo_video.yaml         # 单视频生成配置
  └─ veo_video_batch.yaml   # 视频批处理配置
prompts/                    # prompt 模板
  ├─ *.yaml                 # 图片增强 prompt
  └─ video/*.yaml           # 视频生成 prompt
scripts/                    # 脚本
  ├─ gemini_weather_pairs.py    # 批量图片天气增强（逐帧独立）
  ├─ gemini_weather_sample.py   # 单图示例
  ├─ veo_video_generate.py      # 单视频生成
  └─ veo_video_batch.py         # 批量视频生成
```

---

## 环境与安装
- Python 3.9+
- 安装依赖：
```bash
python3 -m pip install -r requirements.txt
```
- 设置 API Key（两种方式任一即可）：
  - 环境变量：`export GEMINI_API_KEY="<your_key>"`
  - 或在文件 `configs/gemini_api_key.txt` 中写入真实 key（脚本会自动读取）

---

## 天气增强（图片 → 图片）
- 配置：`configs/gemini_weather.yaml`
  - 模型名：`gemini-2.5-flash-image`
  - 输出尺寸：默认 1344x768（16:9）
  - 变体与 prompt 文件：`variants[].prompt_file`，对应 `prompts/*.yaml`
- 运行批处理（逐帧独立、避免构图“粘连”）：
```bash
python3 scripts/gemini_weather_pairs.py configs/gemini_weather.yaml
```
- 输出：`outputimg/<scene>/<weather>/<frame>_<weather>.png`

Prompt 模板要点：
- 正向：POV 视角与几何保持 + 天气特征（雨/雾/雪/晴/夕阳）+ 色调/光照描述；
- 负向：禁止新增/删除车辆，禁止改变道路结构、标志标线不可读、伪影/过曝/过饱和等；
- 组内一致性：同组共享同一 prompt 与低创造性（creativity），更高保真（fidelity）。

---

## 视频生成（帧 → 视频）
### 单视频
- 配置：`configs/veo_video.yaml`（示例）
  - `model_name: models/veo-3.1-generate-preview`
  - `first_frame`：首帧路径（建议 `0000*`）
  - `last_frame`：如需“首尾帧插值”，仅当模型支持时启用；预览模型通常不接受该参数
  - `duration_seconds: 8`、`aspect_ratio: "16:9"`
- 运行：
```bash
python3 scripts/veo_video_generate.py configs/veo_video.yaml
```
- 说明：当前预览模型支持“首帧参考”，`use_last_frame` 若打开可能返回 400 NOT SUPPORTED；正式模型或 Vertex 版本开放后，可改为 true。

### 批量视频
- 配置：`configs/veo_video_batch.yaml`
  - `input_root: ../outputimg`，`output_root: ../outputmp4`
  - `defaults.duration_seconds: 8`（可改），`use_first_frame_reference: true`，`use_last_frame: false`
  - 每种天气的 prompt 文件：`prompts/video/*.yaml`
- 固定参考帧选择：
  - 优先匹配文件名包含 `0000` 与 `0008`；如不存在，退回首/末元素；
  - 对应逻辑：`scripts/veo_video_batch.py::pick_reference_frames()`。
- 运行：
```bash
python3 scripts/veo_video_batch.py configs/veo_video_batch.yaml
```
- 输出：`outputmp4/<scene>/<weather>/<scene>_<weather>.mp4`

---

## 一致性与质量策略
- 逐帧独立生成（去除直接 style hint）避免构图互相复制，同时：
  - 固定 prompt + 低创造性（creativity）+ 较高保真（fidelity）；
  - 需要时可做后处理颜色对齐（LAB/HSV 统计）增强组内色调统一；
- 视频侧：首帧参考 + 稳定 prompt（视频用 `prompts/video/*.yaml`）；若 API 支持 `last_frame` 再开启插值；
- 负向约束：禁止新增/删除车辆、禁止改变道路/标志布局、禁止过曝/伪影，确保评测要素稳定。

---

## 常见问题（FAQ）
- 400 INVALID_ARGUMENT：
  - 预览版 VEO 模型不支持 `last_frame`、`fps`、`seed` 等字段；请在配置中移除或设 `use_last_frame: false`；
  - prompt 路径与输入/输出根目录需使用相对 `configs/` 的路径（批量 YAML 已内建相对解析）。
- 找不到 Key：
  - 确认 `GEMINI_API_KEY` 已导出，或 `configs/gemini_api_key.txt` 已写入真实 key（且批量 YAML 的 `api_key_path` 为 `gemini_api_key.txt`）。
- 批量无输出：
  - 检查 `outputimg/<scene>/<weather>/` 是否存在帧（如 `0000_*.png`、`0008_*.png`）；
  - 若 mp4 已存在则默认跳过，删除后重试即可。

---

## 快速开始（命令速查）
```bash
# 1) 安装依赖
python3 -m pip install -r requirements.txt

# 2) 设置 API Key（或写入 configs/gemini_api_key.txt）
export GEMINI_API_KEY="<your_key>"

# 3) 批量天气增强（独立逐帧）
python3 scripts/gemini_weather_pairs.py configs/gemini_weather.yaml

# 4) 批量视频生成（默认 8s、首帧参考）
python3 scripts/veo_video_batch.py configs/veo_video_batch.yaml
```

---

## 后续路线
- 获取/切换到支持 `last_frame` 的 VEO 正式模型，启用首尾帧插值；
- 按需加入颜色/LUT 统一、光流一致性指标（SSIM/ΔE）与自动重试逻辑；
- 扩展更多天气/时间段 prompt（雨夹雪、薄雾清晨、暴雨夜等）与更细颗粒的控制参数。

> 如需我为你的数据集新增自定义天气变体或编写更严格的视频 prompt，请告知具体场景与约束要点（道路类型、光源、交通密度等），我会补充模板并更新配置。
