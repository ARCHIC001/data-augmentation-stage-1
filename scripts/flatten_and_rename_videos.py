import os
import shutil
from pathlib import Path

# Define the shifan directory path
shifan_dir = Path("/Users/archicyan/Documents/googllle/data augmentation/input/shifan")

# Supported video extensions
video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv'}

# Collect all video files from subdirectories
video_files = []
for ext in video_extensions:
    video_files.extend(shifan_dir.rglob(f'*{ext}'))

# Sort files to ensure consistent ordering
video_files.sort()

# Move and rename files sequentially
for idx, file_path in enumerate(video_files, start=1):
    new_name = f"{idx}.mp4"
    destination = shifan_dir / new_name
    
    # Avoid overwriting existing files with same name
    counter = 1
    while destination.exists():
        new_name = f"{idx}_{counter}.mp4"
        destination = shifan_dir / new_name
        counter += 1
    
    shutil.move(str(file_path), str(destination))
    print(f"Moved and renamed: {file_path.name} -> {new_name}")

# Remove empty subdirectories
for item in shifan_dir.iterdir():
    if item.is_dir() and not any(item.iterdir()):
        item.rmdir()
        print(f"Removed empty directory: {item.name}")

print("All videos have been flattened and renamed.")