#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动修正弹痕标注工具

用法：
  python manual_edit.py              # 自动读取最新一轮结果
  python manual_edit.py <timestamp>  # 指定轮次
"""

import json
import sys
import os
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime

# 复用项目现有模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Process import ProcessClass


def find_latest_result(save_dir="./calibration_results"):
    """找到最新的校准结果"""
    p = Path(save_dir)
    if not p.exists():
        print(f"❌ 找不到目录: {save_dir}")
        return None
    
    results = sorted(p.glob("*_calibration_result.json"), reverse=True)
    if not results:
        print("❌ 没有找到校准结果文件")
        return None
    
    return results[0]


def load_result(file_path):
    """加载校准结果"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_hole_image(result_file, save_dir="./calibration_results"):
    """获取弹痕标注图"""
    base = Path(save_dir)
    timestamp = result_file.stem.split('_')[0]
    
    # 找标注图
    img_path = base / f"{timestamp}_bullet_holes_marked.png"
    if img_path.exists():
        return cv2.imread(str(img_path)), timestamp, img_path
    
    # 找结果图
    img_path = base / f"{timestamp}_result_wall.png"
    if img_path.exists():
        return cv2.imread(str(img_path)), timestamp, img_path
    
    return None, timestamp, None


def print_holes_table(result):
    """打印弹痕信息表"""
    details = result.get('details', [])
    if not details:
        print("⚠ 没有详细弹痕数据")
        return
    
    print(f"\n{'='*70}")
    print(f"  弹痕信息表  (共 {result.get('shot_count', '?')} 发)")
    print(f"{'='*70}")
    print(f"  {'编号':>4} {'实际Y间距':>12} {'理论Y间距':>12} {'比值':>8} {'状态':>8}")
    print(f"  {'-':->58}")
    
    for d in details:
        shot = d.get('shot', '?')
        actual = d.get('actual_dy', '?')
        theory = d.get('json_dy', '?')
        ratio = d.get('ratio', '?')
        status = d.get('status', '')
        
        if isinstance(ratio, (int, float)):
            if ratio > 1.3:
                st = "⚠偏大"
            elif ratio < 0.7:
                st = "⚠偏小"
            else:
                st = "✅正常"
        else:
            st = "?"
        
        print(f"  {shot:>4} {str(actual):>12} {str(theory):>12} {str(ratio):>8} {st:>8}")


def edit_holes_interactive(holes_data, img, result):
    """交互式编辑弹痕"""
    print(f"\n{'='*70}")
    print("  手动修正弹痕")
    print(f"{'='*70}")
    print("  1. 查看当前弹痕列表")
    print("  2. 修改某发子弹的 Y 值")
    print("  3. 删除某发子弹")
    print("  4. 添加新弹痕")
    print("  5. 完成并保存")
    print(f"{'='*70}")
    
    while True:
        choice = input("\n请选择操作 (1-5): ").strip()
        
        if choice == '1':
            # 查看
            print_holes_table(result)
            
        elif choice == '2':
            # 修改
            shot_str = input("  要修改第几发？: ").strip()
            try:
                shot_num = int(shot_str)
            except:
                print("  ❌ 无效编号")
                continue
            
            # 找到对应的细节
            details = result.get('details', [])
            found = None
            for i, d in enumerate(details):
                if d.get('shot') == shot_num:
                    found = d
                    break
            
            if not found:
                print(f"  ❌ 找不到第 {shot_num} 发")
                continue
            
            old_val = found.get('actual_dy', '?')
            new_val_str = input(f"  当前 Y 间距: {old_val}，新值: ").strip()
            try:
                new_val = float(new_val_str)
            except:
                print("  ❌ 无效数值")
                continue
            
            # 更新
            details[shot_num-1]['actual_dy'] = new_val
            result['details'][shot_num-1] = details[shot_num-1]
            print(f"  ✅ 第 {shot_num} 发 Y 间距已改为 {new_val}")
            
            # 重新计算
            recalculate(result)
            
        elif choice == '3':
            # 删除
            shot_str = input("  要删除第几发？: ").strip()
            try:
                shot_num = int(shot_str)
            except:
                print("  ❌ 无效编号")
                continue
            
            # 从 details 中移除
            details = result.get('details', [])
            if shot_num-1 >= 0 and shot_num-1 < len(details):
                details.pop(shot_num-1)
                # 更新编号
                for i, d in enumerate(details):
                    d['shot'] = i + 1
                result['details'] = details
                
                # 更新 shot_count
                result['shot_count'] = len(details) + 1
                
                print(f"  ✅ 第 {shot_num} 发已删除")
                recalculate(result)
            else:
                print(f"  ❌ 编号 {shot_num} 不存在")
            
        elif choice == '4':
            # 添加
            print("  目前还未支持交互式添加新弹痕")
            print("  请手动在弹痕标注图上添加标记后重新运行")
            
        elif choice == '5':
            # 保存
            return result
        
        else:
            print("  ❌ 无效选项")


def recalculate(result):
    """重新计算统计结果"""
    details = result.get('details', [])
    if not details:
        return
    
    actual_vals = [d.get('actual_dy', 0) for d in details]
    actual_valid = [v for v in actual_vals if v > 0]
    theory_vals = [d.get('json_dy', 0) for d in details]
    theory_valid = [v for v in theory_vals if v > 0]
    
    ratios = []
    for a, t in zip(actual_valid, theory_valid):
        if t > 0:
            ratios.append(a / t)
    
    if ratios:
        avg = np.mean(ratios)
        std = np.std(ratios)
        scope_val = result.get('current_scope', 1.0)
        suggested = round(scope_val * avg, 2)
        
        result['avg_ratio'] = round(float(avg), 3)
        result['std_ratio'] = round(float(std), 3)
        result['suggested_scope'] = suggested
        
        print(f"\n  📊 重新计算完成")
        print(f"  平均比值: {avg:.3f}")
        print(f"  建议倍镜系数: {suggested}")


def save_result(result, save_dir="./calibration_results"):
    """保存修改后的结果"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = Path(save_dir) / f"{timestamp}_calibration_result_edited.json"
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 结果已保存: {path}")
    return path


def main():
    print("🔧 弹痕手动修正工具")
    print("="*50)
    
    # 找结果文件
    if len(sys.argv) > 1:
        timestamp = sys.argv[1]
        result_file = Path("./calibration_results") / f"{timestamp}_calibration_result.json"
    else:
        result_file = find_latest_result()
    
    if not result_file or not result_file.exists():
        print("❌ 找不到校准结果文件")
        return
    
    print(f"使用结果: {result_file.name}")
    
    # 加载结果
    result = load_result(result_file)
    
    # 获取图片
    img, timestamp, img_path = get_hole_image(result_file)
    if img_path:
        print(f"弹痕图: {img_path.name}")
        print(f"提示: 如需查看图片请手动打开上面的文件")
    
    # 打印当前结果
    print_holes_table(result)
    print(f"\n当前建议倍镜系数: {result.get('suggested_scope', '?')}")
    
    # 交互式编辑
    edited_result = edit_holes_interactive(None, img, result)
    
    if edited_result:
        # 保存
        save_path = save_result(edited_result)
        print(f"\n✅ 修改完成！")
        print(f"   新结果: {save_path}")


if __name__ == "__main__":
    main()
