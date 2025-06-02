from ultralytics import YOLO
from PIL import Image
import cv2

# 加载训练好的YOLOv8模型
model = YOLO(r'C:\Users\xwm\Downloads\Det-SAM2-main\checkpoints\wuliohebest-yolov8.pt')  # 替换为你的模型权重文件路径

# 指定要检测的图片路径
image_path = r'D:\projects\cameraschedule2\data\factory_images\frame_0020.jpg'  # 替换为你的测试图片路径

# 加载图片
img = cv2.imread(image_path)

# 进行物体检测
results = model(img)

# 获取检测结果
detected = False
target_class = 'wuliaohe'  # 替换为你想检测的物体类别名称，例如 'car', 'person' 等

# 遍历检测结果
for result in results:
    boxes = result.boxes  # 获取边界框
    for box in boxes:
        cls = int(box.cls)  # 获取类别索引
        label = model.names[cls]  # 获取类别名称
        confidence = float(box.conf)  # 获取置信度
        if label == target_class and confidence > 0.5:  # 置信度阈值可调整
            detected = True
            print(f"检测到物体: {label}, 置信度: {confidence:.2f}")
            # 可选：绘制边界框
            x1, y1, x2, y2 = map(int, box.xyxy[0])  # 获取边界框坐标
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, f'{label} {confidence:.2f}', (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

# 输出检测结果
if not detected:
    print(f"未在图片中检测到 {target_class}")

# 保存或显示结果图片
cv2.imwrite('output.jpg', img)  # 保存带边界框的图片
# cv2.imshow('Result', img)  # 显示图片（可选，需取消注释）
# cv2.waitKey(0)
# cv2.destroyAllWindows()