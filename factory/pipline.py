import sys
import os
# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from det_sam2_inference.Det_SAM2_pipeline import DetSAM2Pipeline

# 初始化Pipeline
pipeline = DetSAM2Pipeline(
    sam2_output_frame_dir='./realtime_output/frames',
    sam2_checkpoint_path=r'C:\Users\xwm\Downloads\Det-SAM2-main\checkpoints\sam2.1_hiera_large.pt',
    sam2_config_path=r'C:\Users\xwm\Downloads\Det-SAM2-main\sam2\configs\sam2.1\sam2.1_hiera_l.yaml',
    detect_model_weights=r'C:\Users\xwm\Downloads\Det-SAM2-main\checkpoints\wuliohebest-yolov8.pt',
    output_video_dir='./realtime_output/results',
    visualize_postprocessor=False  # 实时场景建议关闭以提高性能
)

# 设置检测置信度阈值，确保0.82的物体能被检测到
pipeline.video_processor.detect_confidence = 0.4

# 针对实时视频优化参数
pipeline.video_processor.frame_buffer_size = 15  # 减小缓冲提高实时性
pipeline.video_processor.detect_interval = 10    # 更频繁的检测
pipeline.video_processor.max_frame_num_to_track = 30  # 缩短追踪长度
pipeline.video_processor.max_inference_state_frames = 100  # 限制内存

# 启用可视化输出以查看跟踪效果
pipeline.video_processor.vis_frame_stride = 2  # 每2帧渲染一次，生成跟踪视频

# 确保输出目录存在
os.makedirs('./realtime_output/frames', exist_ok=True)

# 支持的视频源
# 1. 本地摄像头
#video_source = 0  # 或 1, 2...

# 2. RTSP网络流
#video_source = 'rtsp://admin:password@192.168.1.100:554/stream'

# 3. HTTP流
#video_source = 'http://192.168.1.100:8080/video'

video_source = r"C:\Users\xwm\Downloads\Det-SAM2-main\factory\data\factory0.mp4"

# 开始实时处理
pipeline.inference(
    video_source=video_source,
    max_frames=100000  # 设置大值以持续运行
)