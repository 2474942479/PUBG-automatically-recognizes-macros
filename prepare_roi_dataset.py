"""从 roi_debug 目录复制图片到训练数据集"""
import os
import shutil
from pathlib import Path
from core.paths import res_path

# ROI 截图目录
roi_debug_dir = res_path('logs', 'roi_debug')

# 目标数据集目录
datasets_dir = res_path('datasets')

# 类别映射（ROI 名称 -> 数据集类别）
category_mapping = {
    'Name_1': 'Name',
    'Name_2': 'Name',
    'Scope_1': 'Scope',
    'Scope_2': 'Scope',
    'Muzzle_1': 'Muzzle',
    'Muzzle_2': 'Muzzle',
    'Grip_1': 'Grip',
    'Grip_2': 'Grip',
    'Stock_1': 'Stock',
    'Stock_2': 'Stock',
}

def copy_roi_to_dataset():
    """将 ROI 截图按类别复制到数据集目录"""
    
    print("=" * 60)
    print("从 roi_debug 复制图片到训练数据集")
    print("=" * 60)
    
    for roi_folder, category in category_mapping.items():
        roi_path = os.path.join(roi_debug_dir, roi_folder)
        if not os.path.exists(roi_path):
            print(f"[跳过] {roi_folder} 不存在")
            continue
        
        # 统计该目录下的图片
        images = [f for f in os.listdir(roi_path) if f.endswith(('.png', '.jpg', '.jpeg'))]
        print(f"\n{roi_folder}: {len(images)} 张图片")
        
        if len(images) == 0:
            continue
        
        # 创建目标目录
        train_dir = os.path.join(datasets_dir, category, 'train')
        os.makedirs(train_dir, exist_ok=True)
        
        # 复制图片（按文件名前缀分组到不同子类别）
        copied = 0
        for img in images:
            src = os.path.join(roi_path, img)
            dst = os.path.join(train_dir, img)
            try:
                shutil.copy2(src, dst)
                copied += 1
            except Exception as e:
                print(f"  [错误] {img}: {e}")
        
        print(f"  ✅ 复制 {copied}/{len(images)} 张到 {category}/train/")

if __name__ == '__main__':
    copy_roi_to_dataset()
