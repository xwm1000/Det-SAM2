# Det-SAM2 快速参考手册

## 🚀 常用命令

### 基础推理
```bash
# 1. 仅Det-SAM2分割推理
python det_sam2_inference/det_sam2_RT.py

# 2. 完整pipeline (推荐)
python det_sam2_inference/Det_SAM2_pipeline.py

# 3. 参数评估优化
python det_sam2_inference/eval_det-sam2.py
```

## 📂 关键文件路径

### 核心脚本
- `det_sam2_inference/det_sam2_RT.py` - 核心推理模块
- `det_sam2_inference/postprocess_det_sam2.py` - 后处理模块  
- `det_sam2_inference/Det_SAM2_pipeline.py` - 完整pipeline
- `det_sam2_inference/eval_det-sam2.py` - 评估脚本

### 模型权重
- `checkpoints/sam2.1_hiera_large.pt` - SAM2大模型权重
- `det_sam2_inference/det_weights/train_referee12_960.pt` - YOLOv8台球检测权重

### 数据目录
- `det_sam2_inference/data/Det-SAM2-Evaluation/` - 评估数据集
- `det_sam2_inference/temp_output/` - 临时输出
- `det_sam2_inference/pipeline_output/` - Pipeline输出

## ⚙️ 关键参数速查

### VideoProcessor 核心参数
```python
# 模型配置
sam2_checkpoint = "../checkpoints/sam2.1_hiera_large.pt"
detect_model_weights = "det_weights/train_referee12_960.pt"
detect_confidence = 0.85

# 性能优化
frame_buffer_size = 30          # 帧缓冲大小
detect_interval = 30            # 检测间隔帧数  
max_frame_num_to_track = 60     # 最大追踪帧数
max_inference_state_frames = 60 # 最大记忆库帧数

# 预加载记忆库
load_inference_state_path = "output_inference_state/inference_state.pkl"
save_inference_state_path = "output_inference_state/inference_state.pkl"
```

### VideoPostProcessor 台球参数
```python
# 进球判断
pot_distance_threshold = 100    # 袋口距离阈值
pot_velocity_threshold = 0.9    # 进球速度阈值

# 碰撞检测
ball_distance_threshold = 120   # 球间距离阈值
ball_velocity_threshold = 10    # 碰撞速度阈值

# 反弹检测
table_margin = 100             # 桌边缓冲区
rebound_velocity_threshold = 0.7 # 反弹速度阈值
```

## 🎯 常用功能

### 1. 单独分割推理
```python
from det_sam2_inference.det_sam2_RT import VideoProcessor

processor = VideoProcessor(
    sam2_checkpoint="../checkpoints/sam2.1_hiera_large.pt",
    detect_model_weights="det_weights/train_referee12_960.pt"
)

processor.run(
    video_path="your_video.mp4",
    output_video_segments_pkl_path="output/segments.pkl"
)
```

### 2. 完整pipeline推理
```python
from det_sam2_inference.Det_SAM2_pipeline import DetSAM2Pipeline

pipeline = DetSAM2Pipeline(
    sam2_checkpoint_path="../checkpoints/sam2.1_hiera_large.pt",
    detect_model_weights="det_weights/train_referee12_960.pt"
)

pipeline.inference(
    video_source="your_video.mp4",
    max_frames=2000
)
```

### 3. 使用预加载记忆库
```python
# 先生成记忆库
processor = VideoProcessor(
    save_inference_state_path="memory_bank.pkl"
)
processor.run(video_path="reference_video.mp4")

# 然后使用记忆库
processor_new = VideoProcessor(
    load_inference_state_path="memory_bank.pkl",
    detect_interval=-1  # 不再检测，完全依靠记忆库
)
processor_new.run(video_path="new_video.mp4")
```

## 🔧 故障排除

### 常见错误
1. **显存不足**: 减小 `max_inference_state_frames`
2. **推理太慢**: 增大 `frame_buffer_size` 和 `detect_interval`
3. **精度不够**: 降低 `detect_confidence`，增加检测频率

### 性能调优
- **内存优化**: 设置合理的 `max_inference_state_frames`
- **速度优化**: 增大 `frame_buffer_size` 和 `detect_interval`
- **精度优化**: 使用更大的SAM2模型，调整后处理阈值

## 📊 输出文件说明

### 分割结果
- `video_segments.pkl` - SAM2分割mask字典
- `special_classes_detection.pkl` - 特殊类别检测结果

### 可视化输出  
- `det_sam2_RT_output/` - 分割可视化帧
- `pipeline_output/` - 完整pipeline输出
- `prompt_results/` - 检测提示可视化

### 评估结果
- `eval_results.json` - 参数评估结果
- 可用 `result_visualize.py` 可视化

## 🎱 台球场景事件

### 检测的事件类型
1. **进球事件** - 球进入袋口
2. **碰撞事件** - 球与球碰撞  
3. **反弹事件** - 球撞击桌边反弹

### 参数调优建议
- 进球太敏感: 减小 `pot_distance_threshold`
- 碰撞漏检: 增大 `ball_distance_threshold`
- 反弹误报: 减小 `table_margin`

## 💡 最佳实践

1. **首次使用**: 先用 `eval_det-sam2.py` 找到最佳参数
2. **长视频**: 使用 `Det_SAM2_pipeline.py` 确保恒定资源占用
3. **相似场景**: 利用预加载记忆库提高效率
4. **自定义场景**: 训练新的YOLOv8模型替换检测器

---
📚 **详细文档**: 参考 `PROJECT_ARCHITECTURE.md`  
🔗 **技术报告**: https://arxiv.org/abs/2411.18977 