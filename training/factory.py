import cv2
import os
from ultralytics import YOLO
from sam2.build_sam import build_sam2_video_predictor

# 加载 YOLO 模型
yolo_model = YOLO("yolov8n.pt")

# 加载 SAM2 模型
sam2_checkpoint = "./checkpoints/sam2.1_hiera_tiny.pt"  # SAM2 模型权重路径
model_cfg = "configs/sam2.1/sam2.1_hiera_t.yaml"  # SAM2 配置文件
predictor = build_sam2_video_predictor(model_cfg, sam2_checkpoint)

# 处理视频帧的文件夹
video_dir = "./frames"
frame_names = [p for p in os.listdir(video_dir) if p.lower().endswith(('.png', '.jpg', '.jpeg'))]
frame_names.sort(key=lambda p: int(os.path.splitext(p)[0]))

# 初始化 SAM2 的推理状态
inference_state = predictor.init_state(video_path=video_dir)

# 对每一帧进行 YOLO 检测并生成 SAM2 提示
for frame_idx, frame_name in enumerate(frame_names):
    frame_path = os.path.join(video_dir, frame_name)
    frame = cv2.imread(frame_path)

    # 使用 YOLO 进行目标检测
    results = yolo_model.track(frame, persist=True, tracker="botsort.yaml")  # 启用跟踪

    # 提取检测结果（边界框）
    detections = []
    if results and len(results) > 0:
        for result in results:
            if hasattr(result, 'boxes'):
                for box in result.boxes:
                    bbox = box.xyxy[0].cpu().numpy()  # 获取边界框坐标
                    track_id = int(box.id.item()) if hasattr(box, 'id') else None
                    detections.append({"frame_id": frame_idx, "bbox": bbox.tolist(), "track_id": track_id})

    # 将 YOLO 的边界框作为 SAM2 的提示输入
    for detection in detections:
        bbox = detection["bbox"]
        predictor.add_new_points_or_boxes(
            inference_state=inference_state,
            frame_idx=frame_idx,
            obj_id=detection["track_id"],
            boxes=[bbox]  # 提供边界框作为提示
        )

# 进行 SAM2 的视频分割
masks, scores, _ = predictor.propagate_in_video(inference_state)

# 保存或处理分割结果
# （根据需要添加后处理代码，例如保存掩码或可视化）