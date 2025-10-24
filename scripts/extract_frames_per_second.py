import os
import cv2


def extract_frames(input_dir):
    """Extract frames at the start of each second from videos
    从视频中提取每秒开始时的帧"""
    for video_file in os.listdir(input_dir):
        if not video_file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            continue
        
        video_path = os.path.join(input_dir, video_file)
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[ERROR] Failed to open video: {video_file}")
            continue
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            print(f"[WARNING] Invalid FPS for {video_file}, skipping")
            cap.release()
            continue
        
        # Create output subfolder
        # 创建输出子文件夹
        folder_name = os.path.splitext(video_file)[0]
        output_subdir = os.path.join(input_dir, folder_name)
        os.makedirs(output_subdir, exist_ok=True)
        
        second = 0
        while True:
            frame_id = int(second * fps)
            if frame_id >= cap.get(cv2.CAP_PROP_FRAME_COUNT):
                break
            
            # Attempt precise frame positioning
            # 尝试精确定位帧位置
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
            ret, frame = cap.read()
            if not ret:
                # Fallback to sequential reading if precise seek fails
                # 如果精确定位失败则回退到顺序读取
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                for _ in range(frame_id):
                    if not cap.grab():
                        break
                ret, frame = cap.retrieve()
                
            if ret:
                # Save frame with 4-digit numbering
                # 使用4位数字编号保存帧
                img_path = os.path.join(output_subdir, f"{second:04d}.png")
                cv2.imwrite(img_path, frame)
            
            second += 1
        
        cap.release()
        print(f"[SUCCESS] Processed {video_file} ({second} frames extracted)")

if __name__ == "__main__":
    video_dir = "input/shifan"
    extract_frames(video_dir)