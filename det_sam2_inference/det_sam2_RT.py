import os
import psutil
import subprocess  # TODO 开发过程中查看资源占用的包，后续应当删除
# from pympler import asizeof  # TODO 开发过程中查看资源占用的包，后续应当删除
import cv2
import sys
import gc
import time
import torch
from sam2.build_sam import build_sam2_video_predictor
from .frames2video import frames_to_video
from sam2.utils.misc import tensor_to_frame_rgb
import ultralytics
from IPython import display
display.clear_output()  # clearing the output
ultralytics.checks()  # running checks
from ultralytics import YOLO  # importing YOLO
from IPython.display import display, Image
import matplotlib.pyplot as plt
from PIL import Image
import numpy as np
from tqdm import tqdm
import pickle

class VideoProcessor:
    '''
    这是一个接收视频流，自动化通过检测模型给SAM2添加条件提示的pipeline。
    '''
    def __init__(
        self,
        output_dir,
        sam2_checkpoint,
        model_cfg,
        detect_model_weights,
        detect_confidence=0.85,  # YOLO模型置信度
        skip_classes={11, 14, 15, 19},  # 在本模型yolo输出中: 0: black ball 1: blue ball 2: blue ball-t 3: brown ball 4: brown ball-t 5: green ball 6: green ball-t 7: orange ball 8: orange ball-t 9: pink ball 10: pink ball-t 11: pocket 12: red ball 13: red ball-t 14: table 15: triballs 16: white ball 17: yellow ball 18: yellow ball-t 19: Plam_cue
        vis_frame_stride=-1,  # 每隔几帧渲染一次分割结果， -1时不进行渲染
        visualize_prompt=False, # 是否可视化交互帧
        frame_buffer_size=30,  # 每次累积多少帧后执行推理
        detect_interval=30,  # 每隔多少帧执行一次检测（条件帧提示）, -1时不进行检测（不添加条件帧提示）但是需要所有帧中必须至少存在一帧条件帧（可以是系统提示帧）
        max_frame_num_to_track=60,  # 每次传播（propagate_in_video）时从最后一帧开始执行倒序追踪推理的最大长度。该限制可以有效降低长视频的重复计算开销
        max_inference_state_frames=60,  # 不应小于max_frame_num_to_track ; 限制inference_state中的帧数超出这个帧数时会不断释放掉旧的帧，-1表示不限制
        load_inference_state_path=None,  # 如果需要预加载内存库，则传入预加载内存库的路径(.pkl)
        save_inference_state_path=None,  # 如果需要保存已推理的内存库，则传入保存路径(.pkl)
    ):
        self.output_dir = output_dir  # 渲染后的结果保存路径
        self.sam2_checkpoint = sam2_checkpoint  # SAM2模型权重
        self.model_cfg = model_cfg  # SAM2模型配置文件
        self.detect_model_weights = detect_model_weights  # YOLO模型权重
        self.detect_confidence = detect_confidence  # YOLO模型置信度
        self.skip_classes = skip_classes  # 从YOLO检测输出到SAM条件输入中需要忽略的类别
        self.vis_frame_stride = vis_frame_stride  # 每隔几帧渲染一次分割结果
        self.visualize_prompt = visualize_prompt  # 是否可视化交互帧
        # 视频流累积推理 和 检测模型间隔推理
        self.frame_buffer_size = frame_buffer_size  # 每次累积多少帧后执行推理
        self.detect_interval = detect_interval  # 每隔多少帧执行一次检测
        self.frame_buffer = []  # 用于累积帧
        # 传播（propagate_in_video）时的最大追踪长度
        self.max_frame_num_to_track = max_frame_num_to_track
        # 限制inference_state中的帧数超出这个帧数时会不断释放掉旧的帧，-1表示不限制
        self.max_inference_state_frames = max_inference_state_frames  # 需要确保清理的帧不会再被使用,max_inference_state_frames一般需要大于等于max_frame_num_to_track最大传播长度
        # 预加载内存库和保存已推理内存库的路径
        self.load_inference_state_path = load_inference_state_path
        self.save_inference_state_path = save_inference_state_path
        self.pre_frames = 0  # 初始化预加载内存库的视频帧长度，如果不存在预加载，则该值恒为0不影响任何计算

        if save_inference_state_path is not None:
            assert max_inference_state_frames == -1, "如果需要保存已推理内存库以制作预加载内存库，则不应当释放任何旧的帧，max_inference_state_frames需要设置为-1"

        # 将检测模型的特殊类别（如袋口）进行单独的SAM2分析，并保存在字典中
        self.special_classes = 11  # 特殊类别在检测模型中的索引，这里11是台球场景下的球袋口。即会出现多个物体的类别，而SAM无法给多个物体赋予同一个ID
        self.special_classes_detection = []  # 用于存储特殊类别的检测结果

        print(
            f"---最大累积帧数:{self.frame_buffer_size},"
            f"检测间隔:{self.detect_interval},"
            f"最大传播长度:{self.max_frame_num_to_track},"
            f"推理保留帧数:{self.max_inference_state_frames},"
            f"预加载内存库:{self.load_inference_state_path},"
        )

        # 构建SAM2模型
        self.predictor = build_sam2_video_predictor(model_cfg, sam2_checkpoint)
        # 加载YOLOv8n模型
        self.detect_model = YOLO(detect_model_weights)

        # video_segments 包含逐帧的分割结果
        self.video_segments = {}
        # 全局inference_state占位，inference_state在process_frame第一帧中正式初始化
        self.inference_state = None

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)

        # 选择计算设备
        if torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")
        # print(f"---using device: {device}")
        if device.type == "cuda":
            # 使用 bfloat16 为整个脚本，可以推理速度快一倍以上
            torch.autocast("cuda", dtype=torch.bfloat16).__enter__()
            # 为 Ampere 架构 GPU 开启 tfloat32 (https://pytorch.org/docs/stable/notes/cuda.html#tensorfloat-32-tf32-on-ampere-devices)
            if torch.cuda.get_device_properties(0).major >= 8:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True

    # 获取 GPU 显存占用
    def print_gpu_memory(self):  # TODO:开发过程中查看资源占用，最终应当删除
        try:
            # 使用 nvidia-smi 获取显存信息
            result = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,nounits,noheader"])
            result = result.decode("utf-8").strip().split("\n")
            # 每个 GPU 的显存使用情况 (used, free)
            gpu_memory = [tuple(map(int, line.split(", "))) for line in result]
            if gpu_memory:
                for idx, (used, free) in enumerate(gpu_memory):
                    print(f"GPU{idx}显存 - 使用: {used} MB, 空余: {free} MB")

        except Exception as e:
            print(f"Error in getting GPU memory: {e}")
            return None

    def calculate_tensor_size(self,value):  # TODO:开发过程中查看资源占用，最终应当删除
        """
        计算张量的显存占用（MB）。
        """
        if isinstance(value, torch.Tensor):
            size = value.element_size() * value.nelement()
            return size
        return 0
    def calculate_object_size(self,value):  # TODO:开发过程中查看资源占用，最终应当删除
        """
        递归计算非张量对象（dict, list等）的显存占用，若包含张量则考虑显存占用。
        """
        total_size = 0
        if isinstance(value, dict):
            for k, v in value.items():
                total_size += self.calculate_tensor_size(v)
                total_size += self.calculate_object_size(v)
        elif isinstance(value, list):
            for item in value:
                total_size += self.calculate_tensor_size(item)
                total_size += self.calculate_object_size(item)
        return total_size
    def print_size_of(self, inference_state):  # TODO:开发过程中查看资源占用，最终应当删除
        """
        打印 inference_state 中的所有张量和其他对象的显存占用。
        """
        total_size = 0
        for key, value in inference_state.items():
            tensor_size = self.calculate_tensor_size(value)
            if tensor_size > 0:
                total_size += tensor_size
                print(f"{key}: {value.size() if isinstance(value, torch.Tensor) else type(value)}, "
                      f"{value.dtype if isinstance(value, torch.Tensor) else ''}, "
                      f"{tensor_size / (1024 ** 2):.2f} MB")
            else:
                object_size = self.calculate_object_size(value)
                if object_size > 0:
                    total_size += object_size
                    print(f"{key}: {type(value)}, size: {object_size / (1024 ** 2):.2f} MB")

        print(f"Total size: {total_size / (1024 ** 2):.2f} MB")

    # 获取 CPU 内存占用
    def print_cpu_memory(self):  # TODO:开发过程中查看资源占用，最终应当删除
        memory_info = psutil.virtual_memory()
        # 已用内存和总内存，单位 GB
        cpu_used = memory_info.used / (1024 ** 3)
        cpu_total = memory_info.total / (1024 ** 3)
        print(f"CPU 内存 - 使用/总计: {cpu_used:.2f}/{cpu_total:.2f}GB")

    def calculate_video_segments_memory(self, video_segments):   # TODO:开发过程中查看资源占用，最终应当删除
        total_memory = 0

        for frame_idx, objects in video_segments.items():
            for obj_id, mask_array in objects.items():
                if isinstance(mask_array, np.ndarray):
                    total_memory += mask_array.nbytes  # NumPy array内存占用
                else:
                    print(f"Warning: Object {obj_id} in frame {frame_idx} is not a NumPy array.")

        return total_memory


    def clear(self):
        """
        保留实例化的基础上，清除所有和本次视频推理有关的内容
        """
        self.frame_buffer = []  # 清空视频累积缓存
        self.pre_frames = 0  # 重置预加载视频帧长度
        self.special_classes_detection = []  # 清空特殊类别检测结果

        self.video_segments = {}
        self.inference_state = None  # 恢复全局inference_state占位


    def detect_predict(self, images, past_num_frames):
        """
        使用YOLO模型对多个图像（从images（self.frame_buffer）中选择符合self.detect_interval的帧）
        进行间隔检测，并返回对应帧索引（由past_num_frames、images和detect_interval计算得到）的检测结果。
        """

        selected_frames = []  # 从images中选择需要进行检测推理的帧
        absolute_indices = []  # 需要进行检测推理的帧在整个视频中的绝对索引
        detection_results = {}  # 初始化结果字典

        if self.detect_interval == -1:  # 如果detect_interval设置-1，则不进行检测推理
            return detection_results  # 返回空结果字典

        # 添加调试信息
        print(f"---开始检测: past_num_frames={past_num_frames}, buffer中有{len(images)}帧")
        
        # 遍历frame_buffer中的帧，选择符合detect_interval的帧
        for i, image in enumerate(images):
            # 计算每帧在视频中的绝对索引
            frame_idx = past_num_frames + i  # past_num_frames + 1 = 开始时本次预测第N帧，past_num_frames + 1 - 1 = 开始时本次预测的帧索引（从0开始）。

            # 如果该帧符合detect_interval间隔检测频率，选择该帧并将其转回原始cv2读取到的bgr格式
            if frame_idx % self.detect_interval == 0 or (frame_idx == 0 and past_num_frames == 0):
                selected_frames.append(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))  # 需要进行检测推理的帧
                absolute_indices.append(frame_idx)  # 需要进行检测推理的帧的绝对索引
                print(f"   选中检测帧: frame_{frame_idx}")

        if len(selected_frames) == 0:  # 如果该次累积帧中不存在需要检测的帧
            print(f"   本轮没有需要检测的帧")
            return detection_results  # 返回空结果字典

        # 推理selected_frames一个列表的图像
        results = self.detect_model(selected_frames, stream=True, conf=self.detect_confidence, iou=0.1, verbose=False)  # conf=0.85

        # 处理results对象生成器
        for i, result in enumerate(results):
            frame_detections = []  # 用于存储当前帧的检测结果
            boxes = result.boxes  # 获取 bounding box 输出的 Boxes 对象
            if boxes is not None:
                for box in boxes:
                    coords = box.xyxy[0].cpu().numpy()  # 获取左上角和右下角坐标 (x1, y1, x2, y2)
                    cls = box.cls.cpu().numpy()  # 获取物体类别
                    conf = box.conf.cpu().numpy()  # 获取置信度

                    frame_detections.append({
                        "coordinates": coords,
                        "class": cls,
                        "confidence": conf
                    })
                    # 添加调试信息：显示检测到的物体类别名称
                    class_id = int(cls[0]) if isinstance(cls, np.ndarray) else int(cls)
                    conf_value = float(conf[0]) if isinstance(conf, np.ndarray) else float(conf)
                    class_name = self.detect_model.names.get(class_id, "Unknown")
                    print(f"   检测到: {class_name} (ID: {class_id}), 置信度: {conf_value:.2f}, 帧: {absolute_indices[i]}")
                    # print(f"帧索引(不包含预加载){absolute_indices[i]-self.pre_frames}: 坐标: {coords}, 类别: {cls}, 置信度: {conf}")

                # 保证收集到的特殊类被检测结果为最大情况
                if not self.special_classes_detection:
                    self.special_classes_count = 0  # 如果不存在特殊类别检测结果，则初始化特殊类别计数器
                special_classes_count = sum(
                    [1 for detection in frame_detections if detection['class'] == self.special_classes])
                if special_classes_count > self.special_classes_count: # 如果当前特殊类别数量大于已有特殊类别数量
                    # 清空已有的特殊类别检测结果
                    self.special_classes_detection = []
                    # 更新特殊类别检测结果
                    for detection in frame_detections:
                        if detection['class'] == self.special_classes:
                            self.special_classes_detection.append(detection["coordinates"])
                    # 更新记录的特殊类别数量
                    self.special_classes_count = special_classes_count

            # 将当前帧的检测结果按照absolute_indices添加到总结果字典中的对应绝对帧索引中
            detection_results[f"frame_{absolute_indices[i]}"] = frame_detections

        return detection_results

    def Detect_2_SAM2_Prompt(self, detection_results_json):
        """
        将YOLO检测结果作为条件传递给SAM。
        """
        # 如果传入的detection_results_json为空，直接返回当前inference_state
        if not detection_results_json:
            # print(f"---detection_results_json字典为空，本轮累积的视频流长度中没有条件帧")
            return self.inference_state

        # 添加标志来跟踪是否有有效的检测结果
        has_valid_detections = False

        # 遍历每一帧的检测结果
        for frame_idx, detections in detection_results_json.items():
            ann_frame_idx = int(frame_idx.replace('frame_', ''))  # 获取帧索引

            if self.visualize_prompt:  # 如果可视化交互帧
                # 创建图像窗口并显示当前帧
                plt.figure(figsize=(9, 6))
                plt.title(f"frame {ann_frame_idx}")
                ann_img_tensor = self.inference_state["images"][ann_frame_idx:ann_frame_idx + 1]  # 从inference_state中获取当前帧  维度为 (1, 3, 1024, 1024)
                ann_frame_rgb = tensor_to_frame_rgb(ann_img_tensor)  # 将tensor转换为RGB图像
                plt.imshow(ann_frame_rgb)  # 显示当前帧图像

            for detection in detections:
                # 从检测结果中获取对象的类和坐标，确保 'class' 是标量或提取数组中的第一个元素
                obj_class = int(detection['class'][0]) if isinstance(detection['class'], np.ndarray) else int(detection['class'])
                # 检查对象类别是否在跳过的类别中
                if obj_class in self.skip_classes:
                    class_name = self.detect_model.names.get(obj_class, "Unknown")
                    print(f"   跳过类别: {class_name} (ID: {obj_class}) 在帧 {ann_frame_idx}")
                    continue  # 跳过当前检测结果，继续处理下一个

                box = detection['coordinates']
                # 将数据传递给 predictor
                _, out_obj_ids, out_mask_logits = self.predictor.add_new_points_or_box(
                    inference_state=self.inference_state,
                    frame_idx=ann_frame_idx,
                    obj_id=obj_class,  # 使用对象类作为 ID
                    box=np.array(box, dtype=np.float32),
                )
                
                # 标记有有效的检测结果
                has_valid_detections = True

                if self.visualize_prompt:  # 如果可视化交互帧
                    # 绘制检测框
                    self.show_box(box, plt.gca(), obj_class)
                    # 绘制遮罩
                    # self.show_mask((out_mask_logits[0] > 0.0).cpu().numpy(), plt.gca(), obj_id=out_obj_ids[0])

            if self.visualize_prompt:  # 如果可视化交互帧
                # 保存图像到指定目录
                save_path = os.path.join("temp_output/prompt_results", f"frame_{ann_frame_idx}.png")
                plt.savefig(save_path)
                plt.close()  # 关闭图形以释放内存

        # 如果没有有效的检测结果，打印提示信息
        if not has_valid_detections:
            print(f"---警告：在帧 {list(detection_results_json.keys())} 中没有检测到有效对象（所有对象都被跳过或没有检测到对象）")

        return self.inference_state

    def render_frame(self, out_frame_idx, frame_rgb, video_segments):
        """
        渲染单帧分割结果。
        """
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.set_title(f"frame {out_frame_idx-self.pre_frames}")  # 此处命名的帧索引不包含预加载帧
        ax.imshow(frame_rgb)

        ax.axis('off')  # 去除坐标轴

        # 在分割结果上渲染
        for out_obj_id, out_mask in video_segments[out_frame_idx].items():
            self.show_mask(out_mask, ax, obj_id=out_obj_id)

        # 保存渲染结果到output_dir
        save_path = os.path.join(self.output_dir, f"frame_{out_frame_idx:05d}.png")

        fig.savefig(save_path, bbox_inches='tight', pad_inches=0)  # 使用figure对象保存, 保存时去掉多余空白
        plt.close(fig)  # 关闭图形以释放内存

        # 如果想显示图像，可以在这里再次调用 plt.show()，但需要重新绘制：
        # plt.show()


    def Detect_and_SAM2_inference(self, frame_idx):
        """
        执行条件检测（detect_predict内部会判断是否需要执行），
        将新增缓存更新到inference_state中，
        执行SAM2推理self.Detect_2_SAM2_Prompt，
        并在所有已有帧上传播propagate_in_video。
        """
        # 如果存在self.inference_state则从self.inference_state获取，否则为第一次推理，历史帧为0
        past_num_frames = self.inference_state["num_frames"] if self.inference_state else 0
        # 将self.frame_buffer传递给检测模型预测，在self.detect_predict内部进行间隔处理
        detection_results_json = self.detect_predict(self.frame_buffer, past_num_frames)
        # print(detection_results_json)

        # 更新inference_state
        if self.inference_state is None:  # 如果是首次则初始化，使用init_state()
            self.inference_state = self.predictor.init_state(video_path=self.frame_buffer)
        else:  # 如果不是首次则使用update_state()
            self.inference_state = self.predictor.update_state(
                video_path=self.frame_buffer,
                inference_state=self.inference_state
            )

        # print("当前 inference_state 的特定键值：")
        # print(f"obj_id_to_idx: {self.inference_state['obj_id_to_idx']}")  # OrderedDict([(16, 0), (10, 1)])
        # print(f"obj_idx_to_id: {self.inference_state['obj_idx_to_id']}")  # OrderedDict([(0, 16), (1, 10)])
        # print(f"obj_ids: {self.inference_state['obj_ids']}")  # [16, 10]
        # print(f"point_inputs_per_obj: {self.inference_state['point_inputs_per_obj']}")  # {第0索引物体: {第N索引帧：提示信息的种类和坐标, 第M索引帧：提示信息的种类和坐标},第1索引物体: {第K索引帧：提示信息的种类和坐标}}
        # # {0: {90: {'point_coords': tensor([[[544.9968, 531.2661],[564.3727, 565.0934]]], device='cuda:0'),'point_labels': tensor([[2, 3]], device='cuda:0', dtype=torch.int32)},
        # #      105: {'point_coords': tensor([[[535.3818, 440.6492],[554.4316, 474.4221]]], device='cuda:0'),'point_labels': tensor([[2, 3]], device='cuda:0', dtype=torch.int32)}},
        # #  1: {105: {'point_coords': tensor([[[533.5795, 200.6569],[552.9704, 247.3801]]], device='cuda:0'),'point_labels': tensor([[2, 3]], device='cuda:0', dtype=torch.int32)}}
        # print(f"mask_inputs_per_obj: {self.inference_state['mask_inputs_per_obj']}")  # {0: {}, 1: {}}
        # print(f"output_dict_per_obj: {self.inference_state['output_dict_per_obj'].keys()}")  # dict_keys([0, 1])
        # print(f"temp_output_dict_per_obj: {self.inference_state['temp_output_dict_per_obj']}")
        # # {0: {'cond_frame_outputs': {}, 'non_cond_frame_outputs': {}},
        # #  1: {'cond_frame_outputs': {}, 'non_cond_frame_outputs': {}}}

        # SAM2推理
        try:
            self.inference_state = self.Detect_2_SAM2_Prompt(detection_results_json)
        except RuntimeError as e:   # 实现了支持在线添加新物体ID的功能后正常情况下不会走到这个分支了，但以防万一。
            if "reset_state" in str(e):
                print("---无法在线添加新出现的物体ID, 正在reset_state")
                self.predictor.reset_state(self.inference_state)
                self.inference_state = self.Detect_2_SAM2_Prompt(detection_results_json)

        # 检查是否有任何对象被添加到 inference_state
        # 如果 obj_ids 为空，说明没有有效的检测结果，跳过传播
        if not self.inference_state.get("obj_ids", []):
            # print("---没有检测到有效对象，跳过传播")
            return
        
        # 打印当前正在跟踪的物体
        print(f"   当前跟踪的物体IDs: {self.inference_state.get('obj_ids', [])}")

        # 执行追踪推理（传播操作）
        for out_frame_idx, out_obj_ids, out_mask_logits in self.predictor.propagate_in_video(
            self.inference_state,
            start_frame_idx=frame_idx,  # 传播函数中，从最后一帧为起始帧倒序追踪推理
            max_frame_num_to_track=self.max_frame_num_to_track,  # 最大追踪推理的长度
            reverse=True,  # 传播函数中，设置为从起始帧倒序追踪推理
        ):
            if out_frame_idx >= self.pre_frames:  # 不将预加载帧存入分割结果字典
                # print(f"将{out_frame_idx}帧渲染进video_segments")
                self.video_segments[out_frame_idx] = {
                    out_obj_id: (out_mask_logits[i] > 0.0).cpu().numpy()
                    for i, out_obj_id in enumerate(out_obj_ids)
                }

        # print("清理前：")
        # processor.print_cpu_memory()

        if self.max_inference_state_frames != -1 :  # 是否尝试释放旧的帧
            self.predictor.release_old_frames(
                self.inference_state,
                frame_idx,
                self.max_inference_state_frames,
                self.pre_frames,
                release_images=True if self.vis_frame_stride == -1 else False,  # 仅在不可视化的时候释放旧的图像张量
            )  # 释放旧帧

        # print("清理后：")
        # self.print_cpu_memory()
        # print(f"video_segments内存占用: {self.calculate_video_segments_memory(self.video_segments) / (1024 ** 2):.2f} MB")


        # processor.print_gpu_memory()
        # processor.print_size_of(self.inference_state)

    def process_frame(self, frame_idx, frame):
        """
        累积一定帧后再执行检测和分割。
        """
        # 累积帧到buffer
        self.frame_buffer.append(frame)

        # 当累积到一定帧数时执行YOLO检测和SAM2推理
        if len(self.frame_buffer) >= self.frame_buffer_size:
            # 符合条件则对视频流累积的缓存区执行一次推理
            self.Detect_and_SAM2_inference(frame_idx)
            # 清空缓冲区
            self.frame_buffer.clear()

        return self.inference_state


    # （下）一些可视化工具，与官方示例的基本相同

    def show_mask(self, mask, ax, obj_id=None, random_color=False):
        # 如果 random_color 为 True，随机生成颜色（包括 RGB 颜色和 alpha 通道的透明度）
        if random_color:
            # 生成随机的 RGB 颜色值，并添加 alpha 通道，值为 0.6 表示部分透明
            color = np.concatenate([np.random.random(3), np.array([0.6])], axis=0)
        else:
            # 使用 matplotlib 中的 'tab10' 颜色映射表，提供 10 种不同颜色
            cmap = plt.get_cmap("tab20")
            # 如果 obj_id 为 None，使用默认索引 0，否则使用 obj_id 作为颜色映射的索引
            cmap_idx = 0 if obj_id is None else obj_id
            # 从颜色映射中获取 RGB 颜色，并添加 alpha 通道，值为 0.6
            color = np.array([*cmap(cmap_idx)[:3], 0.6])
        # 获取 mask 的高度和宽度
        h, w = mask.shape[-2:]
        # 将 mask 调整为二维图像，乘以颜色向量，将颜色信息叠加在 mask 上
        mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
        # 在提供的 matplotlib 轴上显示处理后的 mask 图像
        ax.imshow(mask_image)

        # # 单独显示mask图像
        # # 创建一个新的图形窗口
        # plt.figure(figsize=(6, 4))
        # plt.title(f"Object ID: {obj_id}")
        # # 显示 mask 图像
        # plt.imshow(mask_image)
        # plt.axis('off')  # 关闭坐标轴
        # plt.show()  # 显示图像

    def show_box(self, box, ax, obj_class):
        # show_box只能为一个物体创建可视化框，没办法同时为多个box创建可视化框
        x0, y0 = box[0], box[1]
        w, h = box[2] - box[0], box[3] - box[1]
        ax.add_patch(plt.Rectangle((x0, y0), w, h, edgecolor='red', facecolor=(0, 0, 0, 0), lw=2))

        # 在框的上方显示类别ID
        text_x = x0 + w / 2  # 框的中心位置
        text_y = y0 - 10  # 在框上方位置
        ax.text(text_x, text_y, str(obj_class), fontsize=10, color='white', ha='center', va='bottom')

    def show_points(self, coords, labels, ax, marker_size=200):
        pos_points = coords[labels == 1]
        neg_points = coords[labels == 0]
        ax.scatter(pos_points[:, 0], pos_points[:, 1], color='green', marker='*', s=marker_size, edgecolor='white',
                   linewidth=1.25)
        ax.scatter(neg_points[:, 0], neg_points[:, 1], color='red', marker='*', s=marker_size, edgecolor='white',
                   linewidth=1.25)

    # （下）保存和加载inference_state（内存库）的方法

    def save_inference_state(self, save_path):
        # 获取文件夹路径并确保文件夹存在
        directory = os.path.dirname(save_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        # 保存 inference_state
        with open(save_path, 'wb') as f:
            pickle.dump(self.inference_state, f)
        print(f"---inference_state已保存到 {save_path},共{self.inference_state['num_frames']}帧")

    def load_inference_state(self, load_path):
        with open(load_path, 'rb') as f:
            pre_inference_state = pickle.load(f)
        print(f"---inference_state已从 {load_path} 加载,共{pre_inference_state['num_frames']}帧")
        return pre_inference_state

    # （下）从文件夹加载帧的方法

    def load_frames_from_folder(self, folder_path):
        frames = []
        # 获取文件夹中所有文件的文件名，按文件名排序以保证顺序
        frame_files = sorted([f for f in os.listdir(folder_path) if f.endswith(('.png', '.jpg', '.jpeg'))])

        for frame_file in frame_files:
            frame_path = os.path.join(folder_path, frame_file)
            frame = cv2.imread(frame_path)

            if frame is None:
                print(f"---无法读取帧文件: {frame_path}")
                continue

            # 如果需要将BGR转换为RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame_rgb)

        return frames

    def run(
            self,
            video_path=None, # 传入输入视频
            frame_dir=None, # 或者是帧文件夹
            output_video_segments_pkl_path="/root/autodl-tmp/temp_output/video_segments.pkl", # 保存视频分割结果的pkl路径
            output_special_classes_detection_pkl_path="/root/autodl-tmp/temp_output/special_classes_detection.pkl", # 保存特殊类别检测结果的pkl路径
    ):
        """
        运行视频处理流程。
        """
        # run_start_time = time.time()

        # 如果加载内存库路径不为空，则预加载指定内存库
        if self.load_inference_state_path is not None:
            self.inference_state = self.load_inference_state(self.load_inference_state_path)
            # 获取预加载内存库中条件帧和非条件帧索引，并保存记录在inference_state字典的"preloading_memory_cond_frame_idx"和"preloading_memory_non_cond_frames_idx"中
            preloading_memory_cond_frame_idx = list(self.inference_state["output_dict"]["cond_frame_outputs"].keys())
            preloading_memory_non_cond_frames_idx = list(
                self.inference_state["output_dict"]["non_cond_frame_outputs"].keys())
            self.inference_state["preloading_memory_cond_frame_idx"] = preloading_memory_cond_frame_idx
            self.inference_state["preloading_memory_non_cond_frames_idx"] = preloading_memory_non_cond_frames_idx
            # 获取预加载内存库的已有帧数，并更新self.pre_frames,同时保存在inference_state["preloading_memory_frames"]中
            self.pre_frames = self.inference_state["num_frames"]
            self.predictor.init_preloading_state(self.inference_state)  # 将预加载内存库中部分张量移动到CPU上

            # self.print_cpu_memory()
            # processor.print_gpu_memory()
            # processor.print_size_of(self.inference_state)

        # 如果目标视频路径存在
        if video_path is not None:
            # 从视频文件加载视频流
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"---无法打开视频文件: {video_path}")
                return

            frame_idx = 0  # 初始化当前视频流的帧索引计数器
            while True:
                ret, frame = cap.read()

                if not ret:  # 视频结束, 将缓存中累积的剩余视频帧进行推理
                    if self.frame_buffer is not None and len(self.frame_buffer) > 0:
                        # print(f"---视频结束推理剩余帧数: {len(self.frame_buffer)}")
                        self.Detect_and_SAM2_inference(frame_idx=self.pre_frames + frame_idx - 1)  # 最后一帧的索引，在循环中结束时注意需要-1
                    break

                # 将BGR图像转换为RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # shape = (1080, 1920, 3)
                self.inference_state = self.process_frame(self.pre_frames + frame_idx, frame_rgb)

                frame_idx += 1

            cap.release()

        # 如果目标视频帧文件夹存在
        elif frame_dir is not None:
            frames = self.load_frames_from_folder(frame_dir)

            if not frames:
                print(f"---未找到有效帧文件: {frame_dir}")
                return

            total_frames = len(frames)
            frame_idx = 0  # 初始化当前视频流的帧索引计数器

            while frame_idx < total_frames:
                frame_rgb = frames[frame_idx]  # 从文件夹读取的帧
                self.inference_state = self.process_frame(self.pre_frames + frame_idx, frame_rgb)

                frame_idx += 1

            # 视频结束时，处理缓存中的剩余帧
            if self.frame_buffer is not None and len(self.frame_buffer) > 0:
                # print(f"---处理剩余帧数: {len(self.frame_buffer)}")
                self.Detect_and_SAM2_inference(frame_idx=self.pre_frames + frame_idx - 1)

        # 既不是完整视频也不是帧文件夹
        else:
            print("---未提供有效的视频或帧文件夹路径")

        # run_end_time = time.time()
        # print("---推理总耗时：", run_end_time - run_start_time, "秒")

        # 支持后处理操作，将结果保存成pkl以供后处理读取
        # 保存self.video_segments分割结果的字典,保存的self.video_segments不应当带有预加载帧
        self.video_segments = {idx - self.pre_frames: segment for idx, segment in self.video_segments.items() if idx >= self.pre_frames}
        with open(output_video_segments_pkl_path, 'wb') as file:
            pickle.dump(self.video_segments, file)
        print(f"---self.video_segments分割结果保存至{output_video_segments_pkl_path}")
        # 保存后处理所需要的self.special_classes_detection球带检测字典
        if self.special_classes_detection is None:
            print(f"---{self.special_classes_detection}不满足收集条件,收集失败")
        else:
            with open(output_special_classes_detection_pkl_path, 'wb') as file:
                pickle.dump(self.special_classes_detection, file)
            print(f"---self.special_classes_detection特殊类别检测结果保存至{output_special_classes_detection_pkl_path}")

        # 是否保存本次推理的内存库信息
        if self.save_inference_state_path is not None:  # 如果保存路径不为空,则保存inference_state
            self.save_inference_state(self.save_inference_state_path)

        if self.vis_frame_stride == -1:
            print("---不对任何帧进行渲染,推理完成")
        else:
            # 首先清除self.output_dir文件夹下所有已有文件
            for file in os.listdir(self.output_dir):
                file_path = os.path.join(self.output_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)

            # print(self.video_segments.keys())
            # 统一渲染本次视频推理的所有帧
            images_tensor = self.inference_state["images"]
            for i in tqdm(range(self.pre_frames, images_tensor.shape[0]),desc="掩码可视化渲染进度"):  # 从预加载内存库后一帧开始渲染
                if i % self.vis_frame_stride == 0:  # i为本次推理视频帧的索引
                    # print("渲染帧索引",i)
                    tensor_img = images_tensor[i:i + 1]  # 从inferenced_state["images"]中获取self.frames，用于渲染。维度为 (1, 3, 1024, 1024)
                    frame_rgb = tensor_to_frame_rgb(tensor_img)  # 当前RGB帧的nd数组
                    self.render_frame(i-self.pre_frames, frame_rgb, self.video_segments)
            print(f"---按照每{self.vis_frame_stride}帧间隔渲染,渲染结束")
            frames_to_video(
                frames_folder=self.output_dir,
                output_video_path='/root/autodl-tmp/temp_output/output_video.mp4',
                fps=2
            )  # 将帧文件夹下所有帧制作成视频




if __name__ == '__main__':
    # video_path = 'videos/video中.mp4'
    video_path = '/root/autodl-tmp/data/Det-SAM2评估集/videos/video149.mp4' # /Det-SAM2评估集/videos/video5.mp4  # /长视频/5min.mp4
    rtsp_url = 'rtsp://175.178.18.243:19699/'
    frame_dir = '/root/autodl-tmp/data/预加载内存库10帧'  # 制作预加载内存库用
    output_dir = './temp_output/det_sam2_RT_output'
    sam2_checkpoint = '../checkpoints/sam2.1_hiera_large.pt' # '../checkpoints/sam2.1_hiera_base_plus.pt'
    model_cfg = 'configs/sam2.1/sam2.1_hiera_l.yaml' # 'configs/sam2.1/sam2.1_hiera_b+.yaml'
    detect_model_weights = 'det_weights/train_referee12_960.pt'
    load_inference_state_path = '/root/autodl-tmp/output_inference_state/inference_state_10frames.pkl'
    save_inference_state_path = '/root/autodl-tmp/output_inference_state/inference_state_10frames.pkl'

    # 初始化VideoProcessor类，包括
    processor = VideoProcessor(
        output_dir=output_dir,
        sam2_checkpoint=sam2_checkpoint,
        model_cfg=model_cfg,
        detect_model_weights=detect_model_weights,
        # load_inference_state_path=load_inference_state_path,  # 不传或传None,则不预加载内存库
        # save_inference_state_path=save_inference_state_path,  # 不传或传None,则不保存内存库
    )

    # processor.print_cpu_memory()
    # processor.print_gpu_memory()

    processor.run(
        video_path=rtsp_url,  # 传入视频路径（和帧文件夹二选一）
        # frame_dir=frame_dir,  # 传入帧文件夹（和视频路径二选一）
    )
