# Det-SAM2 项目架构文档

## 项目概述
Det-SAM2是一个基于SAM2(Segment Anything Model 2)的无人工干预视频物体追踪pipeline。项目结合YOLOv8检测模型和SAM2分割模型，实现自动化的视频实例分割，特别针对台球场景进行了优化。

### 核心特性
- 🚀 无需人工提示的自动视频实例分割
- 🎯 支持推理过程中动态添加新类别
- 💾 预加载记忆库功能(preload memory bank)
- ⚡ 恒定显存与内存开销，支持无限长视频推理
- 🎱 完整的台球场景业务逻辑(进球判断、碰撞检测、反弹检测)

## 项目结构

```
Det-SAM2-main/
├── sam2/                           # SAM2核心模块 (基于Facebook SAM2.1)
│   ├── modeling/                   # 模型架构
│   ├── configs/                    # 配置文件
│   ├── sam2_video_predictor.py    # 视频预测器 (修改版)
│   └── utils/                      # 工具函数
├── det_sam2_inference/            # 主要推理代码目录
│   ├── Det_SAM2_pipeline.py       # 全流程pipeline (异步并行)
│   ├── det_sam2_RT.py             # Det-SAM2核心推理模块
│   ├── postprocess_det_sam2.py    # 后处理模块 (台球场景)
│   ├── eval_det-sam2.py           # 评估脚本
│   ├── data/                      # 数据目录
│   ├── det_weights/               # 检测模型权重
│   ├── eval_output/               # 评估结果
│   ├── output_inference_state/    # 预加载记忆库
│   └── temp_output/               # 临时输出
├── checkpoints/                   # SAM2模型权重
├── training/                      # 训练相关
├── tools/                         # 工具脚本
└── notebooks/                     # Jupyter笔记本示例
```

## 核心组件架构

### 1. 检测层 (Detection Layer)
- **组件**: YOLOv8检测模型
- **功能**: 为SAM2提供自动提示(prompt)
- **输入**: 视频帧
- **输出**: 检测框 + 类别ID
- **特点**: 可配置检测间隔、置信度阈值、跳过特定类别

### 2. 分割层 (Segmentation Layer)  
- **组件**: SAM2视频预测器
- **功能**: 基于检测提示进行精确分割
- **输入**: 视频帧 + 检测提示
- **输出**: 分割mask字典
- **特点**: 支持记忆库优化、帧缓冲机制

### 3. 后处理层 (Post-processing Layer)
- **组件**: VideoPostProcessor
- **功能**: 台球场景业务逻辑判断
- **输入**: 分割mask字典
- **输出**: 事件检测结果(进球、碰撞、反弹)
- **特点**: 基于物理运动规律的算法

### 4. 管道层 (Pipeline Layer)
- **组件**: DetSAM2Pipeline
- **功能**: 异步并行处理，恒定资源占用
- **特点**: 支持实时视频流、RTSP输入

## 数据流图

```
视频输入 → 帧提取 → YOLOv8检测 → SAM2分割 → 后处理 → 结果输出
    ↓         ↓         ↓         ↓        ↓
  帧缓冲   → 提示生成 → 记忆库 → mask字典 → 事件检测
                      ↓
                 预加载记忆库
```

## 主要类结构

### VideoProcessor 类 (det_sam2_RT.py)
```python
class VideoProcessor:
    """Det-SAM2核心处理器"""
    - 初始化SAM2和YOLOv8模型
    - 管理帧缓冲和检测间隔
    - 执行分割推理和记忆库管理
    - 支持预加载记忆库功能
```

### VideoPostProcessor 类 (postprocess_det_sam2.py)
```python
class VideoPostProcessor:
    """台球场景后处理器"""
    - 球的轨迹跟踪和速度计算
    - 进球判断 (基于位置和速度向量)
    - 碰撞检测 (基于距离和速度变化)
    - 反弹检测 (基于边界区域和速度分量)
```

### DetSAM2Pipeline 类 (Det_SAM2_pipeline.py)
```python
class DetSAM2Pipeline:
    """异步并行全流程pipeline"""
    - 异步处理视频流
    - 内存优化和资源管理
    - 支持实时和批处理模式
```

### EvalDetSAM2PostProcess 类 (eval_det-sam2.py)
```python
class EvalDetSAM2PostProcess:
    """参数评估和优化"""
    - 自动参数网格搜索
    - 评估指标计算
    - 结果可视化
```

## 关键技术创新

### 1. 预加载记忆库 (Preload Memory Bank)
- **原理**: 将前一段视频的推理记忆应用到新视频
- **优势**: 新视频无需任何提示即可开始推理
- **实现**: 保存inference_state到pkl文件

### 2. 恒定资源占用
- **内存优化**: 限制记忆库最大帧数
- **显存优化**: 动态释放旧帧信息
- **帧缓冲**: 批量处理提高效率

### 3. 动态类别添加
- **功能**: 推理过程中不中断状态添加新类别
- **实现**: 灵活的检测模型类别过滤

## 使用场景

### 1. 单独使用Det-SAM2框架
```bash
python det_sam2_inference/det_sam2_RT.py
```

### 2. 完整台球场景pipeline
```bash
python det_sam2_inference/Det_SAM2_pipeline.py
```

### 3. 参数优化评估
```bash
python det_sam2_inference/eval_det-sam2.py
```

## 性能特点

### 支持的输入格式
- 本地MP4视频文件
- RTSP实时视频流  
- 视频帧文件夹

### 输出格式
- 分割mask的pkl字典
- 可视化渲染视频
- 事件检测结果JSON
- 评估指标报告

## 台球场景业务逻辑

### 进球判断
- **位置检测**: 球心距离袋口的阈值判断
- **速度检测**: 球的运动方向是否指向袋口
- **参数**: `pot_distance_threshold`, `pot_velocity_threshold`

### 碰撞检测  
- **距离判断**: 两球之间的最小距离
- **速度变化**: 碰撞前后的加速度变化
- **参数**: `ball_distance_threshold`, `ball_velocity_threshold`

### 反弹检测
- **边界区域**: 桌边缓冲区域定义
- **速度分量**: 垂直桌边的速度分量变化
- **参数**: `table_margin`, `rebound_velocity_threshold`

## 技术栈

### 深度学习框架
- PyTorch
- SAM2.1 (Facebook)
- YOLOv8 (Ultralytics)

### 计算机视觉
- OpenCV
- PIL/Pillow

### 数据处理
- NumPy
- Pickle

### 可视化
- Matplotlib
- 自定义渲染函数

## 部署建议

### 硬件要求
- GPU: 至少8GB显存(推荐RTX 3080以上)
- RAM: 至少16GB内存
- 存储: 足够空间存储模型权重(~2GB)

### 环境配置
1. 基于SAM2.1环境
2. 安装额外依赖包
3. 下载模型权重
4. 配置数据路径

## 扩展方向

### 1. 其他场景适配
- 替换YOLOv8检测模型
- 修改后处理逻辑
- 调整参数配置

### 2. 性能优化
- 模型量化
- 推理加速
- 并行处理优化

### 3. 功能增强
- 多相机支持
- 3D轨迹重建
- 实时预警系统

---

**技术报告**: https://arxiv.org/abs/2411.18977  
**作者**: Det-SAM2团队  
**版本**: 基于SAM2.1 