# Det-SAM2 模块依赖关系图

## 🏗️ 整体架构层次

```
┌─────────────────────────────────────────────────────┐
│                应用层 (Application Layer)              │
├─────────────────────────────────────────────────────┤
│ DetSAM2Pipeline  │  Evaluation Scripts  │  Notebooks │
├─────────────────────────────────────────────────────┤
│                 业务逻辑层 (Business Layer)            │
├─────────────────────────────────────────────────────┤
│ VideoPostProcessor (台球场景后处理)                     │
├─────────────────────────────────────────────────────┤
│                 推理层 (Inference Layer)               │
├─────────────────────────────────────────────────────┤
│ VideoProcessor (Det-SAM2核心推理)                      │
├─────────────────────────────────────────────────────┤
│                 模型层 (Model Layer)                   │
├─────────────────────────────────────────────────────┤
│ SAM2VideoPredictor    │    YOLOv8 Detector           │
├─────────────────────────────────────────────────────┤
│                 基础层 (Foundation Layer)              │
├─────────────────────────────────────────────────────┤
│ PyTorch  │  OpenCV  │  NumPy  │  其他工具库           │
└─────────────────────────────────────────────────────┘
```

## 🔗 核心模块依赖关系

### VideoProcessor (det_sam2_RT.py)
```
VideoProcessor
├── 依赖模块
│   ├── sam2.sam2_video_predictor.SAM2VideoPredictor
│   ├── ultralytics.YOLO (YOLOv8检测器)
│   ├── torch, cv2, numpy, pickle
│   └── sam2.build_sam.build_sam2_video_predictor
├── 输入接口
│   ├── video_path (MP4视频文件)
│   ├── frame_dir (视频帧文件夹)
│   └── inference_state (预加载记忆库)
└── 输出接口
    ├── video_segments.pkl (分割mask字典)
    ├── special_classes_detection.pkl (特殊类别检测)
    └── inference_state.pkl (记忆库保存)
```

### VideoPostProcessor (postprocess_det_sam2.py)
```
VideoPostProcessor
├── 依赖模块
│   ├── numpy, cv2, pickle, json
│   ├── matplotlib (可视化)
│   └── 自定义工具函数
├── 输入接口
│   └── video_segments.pkl (来自VideoProcessor)
└── 输出接口
    ├── 进球事件检测结果
    ├── 碰撞事件检测结果
    ├── 反弹事件检测结果
    └── 可视化渲染视频
```

### DetSAM2Pipeline (Det_SAM2_pipeline.py)
```
DetSAM2Pipeline
├── 依赖模块
│   ├── VideoProcessor (组合关系)
│   ├── VideoPostProcessor (组合关系)
│   ├── asyncio (异步处理)
│   └── threading (多线程)
├── 输入接口
│   ├── video_source (MP4文件或RTSP流)
│   └── 各种配置参数
└── 输出接口
    ├── 实时处理结果
    └── 最终事件检测报告
```

## 📊 数据流图详解

### 1. 基础推理流程 (det_sam2_RT.py)
```
视频输入 → 帧解码 → 帧缓冲 → 批量处理
                         ↓
检测器(YOLO) → 条件帧标记 → SAM2推理 → mask输出
                         ↓
记忆库管理 → 资源优化 → 结果保存
```

### 2. 完整Pipeline流程 (Det_SAM2_pipeline.py)
```
                    视频流输入
                        ↓
              ┌─────────┴─────────┐
              ↓                   ↓
        VideoProcessor      缓冲队列管理
              ↓                   ↓
        分割mask生成        异步数据传递
              ↓                   ↓
        VideoPostProcessor   结果聚合
              ↓                   ↓
        事件检测结果         最终输出
```

### 3. 评估流程 (eval_det-sam2.py)
```
参数网格 → 批量测试 → VideoProcessor → VideoPostProcessor
    ↓                                           ↓
配置组合 → 循环执行 → 分割推理 → 后处理 → 指标计算
    ↓                                           ↓
最优参数 ← 结果分析 ← 性能评估 ← 结果收集 ← JSON输出
```

## 🧩 关键组件交互

### SAM2与检测器的协作
```python
# 检测器提供条件帧
detection_results = yolo_model(frame)
for detection in detection_results:
    bbox = detection.bbox
    sam2_predictor.add_new_mask(frame_idx, bbox)

# SAM2基于条件帧传播推理
for frame_idx in range(start, end):
    masks = sam2_predictor.propagate_in_video(frame_idx)
```

### 记忆库管理机制
```python
# 记忆库状态管理
inference_state = {
    "images": [],           # 视频帧缓存
    "masks": {},           # 分割mask历史
    "obj_ids": set(),      # 对象ID集合
    "frame_idx": 0         # 当前帧索引
}

# 动态内存优化
if len(inference_state["images"]) > max_frames:
    # 释放旧帧，保持恒定内存占用
    release_old_frames(inference_state)
```

### 异步处理机制
```python
# Pipeline中的异步处理
async def process_video_stream():
    video_task = asyncio.create_task(video_processing())
    postprocess_task = asyncio.create_task(post_processing())
    
    # 并行执行
    await asyncio.gather(video_task, postprocess_task)
```

## 🔧 配置文件依赖

### SAM2模型配置
```
sam2/configs/
├── sam2.1_hiera_t.yaml    # Tiny模型配置
├── sam2.1_hiera_s.yaml    # Small模型配置  
├── sam2.1_hiera_b+.yaml   # Base+模型配置
└── sam2.1_hiera_l.yaml    # Large模型配置
```

### 检测器权重映射
```
det_sam2_inference/det_weights/
└── train_referee12_960.pt  # 台球场景YOLOv8权重
```

## 📦 外部依赖库

### 深度学习栈
- **PyTorch**: 核心深度学习框架
- **torchvision**: 视觉工具库
- **CUDA**: GPU加速支持

### 计算机视觉
- **OpenCV**: 图像处理和视频I/O
- **PIL/Pillow**: 图像处理
- **ultralytics**: YOLOv8实现

### 数据处理
- **NumPy**: 数值计算
- **Pickle**: 序列化存储
- **JSON**: 配置和结果存储

### 可视化和UI
- **Matplotlib**: 结果可视化
- **tqdm**: 进度条显示

## 🚀 扩展接口

### 自定义检测器接口
```python
class CustomDetector:
    def detect(self, frame):
        """返回检测结果: [bbox, confidence, class_id]"""
        pass
    
    def get_classes(self):
        """返回类别名称列表"""
        pass
```

### 自定义后处理器接口  
```python
class CustomPostProcessor:
    def process(self, video_segments):
        """处理分割结果，返回业务逻辑结果"""
        pass
    
    def visualize(self, results):
        """可视化处理结果"""
        pass
```

### 自定义事件检测器
```python
class EventDetector:
    def detect_events(self, trajectories):
        """基于轨迹检测特定事件"""
        pass
    
    def get_event_types(self):
        """返回支持的事件类型"""
        pass
```

---

通过这个模块依赖关系图，你可以：
1. 快速理解各组件的职责边界
2. 追踪数据在系统中的流转路径  
3. 定位需要修改的具体模块
4. 设计自定义扩展的接口

这些架构文件将帮助你和我在后续的开发中快速定位问题和实现新功能。 