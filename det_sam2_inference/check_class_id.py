from ultralytics import YOLO
import sys

try:
    # 加载模型
    print("正在加载YOLO模型...")
    model = YOLO(r'C:\Users\xwm\Downloads\Det-SAM2-main\checkpoints\wuliohebest-yolov8.pt')
    
    # 打印所有类别名称和对应的ID
    print("\nYOLO模型的类别信息：")
    print("-" * 50)
    for cls_id, cls_name in model.names.items():
        print(f"类别ID: {cls_id:2d} -> 类别名称: {cls_name}")
    print("-" * 50)
    
    # 特别检查wuliaohe
    found = False
    for cls_id, cls_name in model.names.items():
        if 'wuliaohe' in cls_name.lower():
            found = True
            print(f"\n找到 'wuliaohe' 相关类别：")
            print(f"类别ID: {cls_id} -> 类别名称: {cls_name}")
    
    if not found:
        print("\n未找到 'wuliaohe' 相关类别")
        print("请检查类别名称是否正确")
        
except Exception as e:
    print(f"发生错误: {type(e).__name__}: {str(e)}")
    sys.exit(1) 