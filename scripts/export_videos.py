from pathlib import Path
from weather_aug.video.ffmpeg import frames_to_video


def main():
    frames_root = Path("outputimg")
    out_root = Path("outputmp4")
    fps = 1  # your frames are 1Hz extracted

    for group_dir in frames_root.glob("**/*"):
        if not group_dir.is_dir():
            continue
        # expects directories like outputimg/<group>/<variant>/
        pngs = list(group_dir.glob("*.png"))
        if not pngs:
            continue
        rel = group_dir.relative_to(frames_root)
        out_path = out_root / rel.with_suffix(".mp4")
        frames_to_video(group_dir, out_path, fps=fps)


if __name__ == "__main__":
    main()

