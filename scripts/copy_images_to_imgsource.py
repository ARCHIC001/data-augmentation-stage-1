import os
import shutil
from pathlib import Path

# Define paths
shifan_dir = Path("/Users/archicyan/Documents/googllle/data augmentation/input/shifan")
imgsource_dir = Path("/Users/archicyan/Documents/googllle/data augmentation/imgsource")

# Create imgsource directory if it doesn't exist
imgsource_dir.mkdir(exist_ok=True)

# Process each subdirectory in shifan
for subdir in shifan_dir.iterdir():
    if subdir.is_dir() and subdir.name.isdigit():  # Check if it's a numbered directory
        # Create corresponding directory in imgsource
        target_subdir = imgsource_dir / subdir.name
        target_subdir.mkdir(exist_ok=True)
        
        # Copy 0000.png if it exists
        source_file_0000 = subdir / "0000.png"
        if source_file_0000.exists():
            target_file_0000 = target_subdir / "0000.png"
            shutil.copy2(source_file_0000, target_file_0000)
            print(f"Copied {source_file_0000} to {target_file_0000}")
        
        # Copy 0008.png if it exists
        source_file_0008 = subdir / "0008.png"
        if source_file_0008.exists():
            target_file_0008 = target_subdir / "0008.png"
            shutil.copy2(source_file_0008, target_file_0008)
            print(f"Copied {source_file_0008} to {target_file_0008}")

print("Image copying completed.")