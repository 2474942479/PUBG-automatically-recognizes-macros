#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 弹痕校准工具 - 离线分析版

流程：
1. 按 1 拍空白墙面（基线）
2. 手动打 N 发（可分多次，打完告诉程序打了几发）
3. 按 2 拍打完后的墙面
4. 自动识别弹痕 → 可视化 → 对比 JSON → 出参数建议
5. 支持手动增删改弹痕

依赖：mss, opencv-python, numpy, keyboard
"""

import cv2
import numpy as np
import mss
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

# 截图区域
ROI_SIZES = {
    "3840x2160": (0, 0, 1920, 1080),   # 4K 截图 1080p 区域（截中间最稳定的部分）
    "2560x1440": (0, 0, 1920, 1080),
    "1920x1080": (0, 0, 1920, 1080),
}

# 弹痕识别参数
DEFAULT_MIN_AREA = 20
DEFAULT_MAX_AREA = 800
DEFAULT_MIN_CIRCULARITY = 0.25
DEFAULT_COLOR_THRESHOLD = 15


class BulletHole:
    """单个弹痕"""
    def __init__(self, x, y, area=0, circularity=0, color_diff=0):
        self.x = int(x)
        self.y = int(y)
        self.area = area
        self.circularity = circularity
        self.color_diff = color_diff
        self.shot_num = 0  # 第几发子弹

    def __repr__(self):
        return f"Hole({self.x}, {self.y})"


class RecoilLogger:
    def __init__(self, save_dir="./calibration_results"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    def save_image(self, name, img):
        path = self.save_dir / f"{self.timestamp}_{name}.png"
        cv2.imwrite(str(path), img)
        print(f"  📷 {path.name}")
        return path

    def save_json(self, name, data):
        path = self.save_dir / f"{self.timestamp}_{name}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  📄 {path.name}")
        return path

    def log(self, msg):
        print(f"  {msg}")


class BulletHoleAnalyzer:
    """弹痕分析与可视化"""
    
    def __init__(self, resolution="3840x2160"):
        self.resolution = resolution
        self.roi = ROI_SIZES.get(resolution, ROI_SIZES["3840x2160"])
        self.logger = RecoilLogger()
        self.bullets = []  # List[BulletHole]
        self.shot_count = 0
        self.base_image = None
        self.result_image = None
        
        # 配置文件路径
        self.config_path = Path("./Config/config.json")
        self.gun_data_dir = Path("./_internal/GunData")
        
        # 识别参数
        self.min_area = DEFAULT_MIN_AREA
        self.max_area = DEFAULT_MAX_AREA
        self.min_circularity = DEFAULT_MIN_CIRCULARITY
        self.color_threshold = DEFAULT_COLOR_THRESHOLD
    
    def capture_screen(self):
        """截取屏幕 ROI"""
        x, y, w, h = self.roi
        with mss.mss() as sct:
            sct.monitors  # 初始化
            monitor = {"left": x, "top": y, "width": w, "height": h}
            img = sct.grab(monitor)
        return np.array(img)
    
    def wait_key(self, key, prompt=None):
        """等待按键"""
        if prompt:
            print(f"\n{prompt}")
        if HAS_KEYBOARD:
            keyboard.wait(str(key))
        else:
            input(f"按回车继续 (代替按 {key})...")
    
    def detect_holes(self, base_img, result_img):
        """
        帧差法检测弹痕
        返回 List[BulletHole]
        """
        print("\n🔍 开始检测弹痕...")
        
        # 1. 转灰度
        base_gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
        result_gray = cv2.cvtColor(result_img, cv2.COLOR_BGR2GRAY)
        
        # 2. 帧差
        diff = cv2.absdiff(base_gray, result_gray)
        
        # 3. 自适应阈值
        _, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 4. 形态学操作：闭运算填充弹痕内部
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        thresh = cv2.dilate(thresh, kernel, iterations=2)
        
        # 5. 查找轮廓
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 6. 过滤
        holes = []
        base_bgr = cv2.cvtColor(base_gray, cv2.COLOR_GRAY2BGR)
        result_bgr = result_img.copy()
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (self.min_area < area < self.max_area):
                continue
            
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * (area / (perimeter * perimeter))
            if circularity < self.min_circularity:
                continue
            
            # 计算质心
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            
            # 颜色变化验证：对比基线和结果图在弹痕位置的颜色差异
            mask = np.zeros(base_gray.shape[:2], dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            mean_base = cv2.mean(base_gray, mask=mask)[0]
            mean_result = cv2.mean(result_gray, mask=mask)[0]
            color_diff = abs(mean_result - mean_base)
            
            if color_diff < self.color_threshold:
                continue
            
            holes.append(BulletHole(cx, cy, area, circularity, color_diff))
        
        print(f"  找到 {len(holes)} 个疑似弹痕")
        return holes
    
    def sort_holes_by_shooting_order(self, holes, shot_count):
        """
        按射击顺序排序弹痕
        排序规则：
        1. 先按 Y 从上到下排序（弹道总体向下落，但上跳导致弹痕从下往上看）
        2. 实际 PUBG 弹道是枪口上跳 → 弹痕从上往下排列
        3. 所以按 Y 从小到排序就是射击顺序
        """
        if len(holes) <= 1:
            return holes
        
        # 按 Y 坐标排序（从上到下 = 从先到后）
        sorted_holes = sorted(holes, key=lambda h: (h.y, h.x))
        
        # 但有时用户手会微调，需要按实际弹道逻辑：
        # 第一发在最高处，后面依次往下
        # 检查：如果第一发在最低处，需要反转
        # 简单判断：看前50%和后50%的平均Y
        mid = len(sorted_holes) // 2
        top_avg = np.mean([h.y for h in sorted_holes[:mid]])
        bot_avg = np.mean([h.y for h in sorted_holes[mid:]])
        
        # 如果下半部分平均Y反而更小，说明排序反了
        if bot_avg < top_avg:
            sorted_holes = sorted_holes[::-1]
        
        # 标注序号
        result = []
        for i, h in enumerate(sorted_holes):
            h.shot_num = i + 1
            result.append(h)
        
        print(f"  已按射击顺序标注 {len(result)} 发")
        return result
    
    def generate_visualization(self, base_img, result_img, holes):
        """
        生成可视化图片：
        - 左半：基线图（不标注）
        - 右半：结果图（标注弹痕编号 + 连线）
        """
        h, w = result_img.shape[:2]
        
        # 在结果图上标注
        vis = result_img.copy()
        
        # 画连线（从第1发到最后一发）
        sorted_holes = sorted(holes, key=lambda h: h.shot_num)
        for i in range(len(sorted_holes) - 1):
            h1 = sorted_holes[i]
            h2 = sorted_holes[i + 1]
            
            # 连线颜色：绿色=正常，黄色=间距大，红色=间距异常
            dy = h2.y - h1.y
            if dy < 5:
                color = (0, 0, 255)  # 红色 - 间距异常
            elif dy < 15:
                color = (0, 255, 255)  # 黄色
            else:
                color = (0, 255, 0)  # 绿色
            
            cv2.line(vis, (h1.x, h1.y), (h2.x, h2.y), color, 2)
            
            # 箭头
            cv2.arrowedLine(vis, (h1.x, h1.y), (h2.x, h2.y), color, 2, tipLength=0.3)
        
        # 画弹痕标记
        for h in sorted_holes:
            # 编号颜色：前5发红色，中间黄色，后面绿色
            if h.shot_num <= 5:
                color = (0, 0, 255)  # BGR: 红
            elif h.shot_num <= 15:
                color = (0, 165, 255)  # BGR: 橙
            else:
                color = (0, 255, 0)  # BGR: 绿
            
            # 外圈
            cv2.circle(vis, (h.x, h.y), 8, color, 2)
            # 中心点
            cv2.circle(vis, (h.x, h.y), 3, color, -1)
            # 编号
            cv2.putText(vis, str(h.shot_num), (h.x + 12, h.y - 8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        # 添加图例
        legend_y = 40
        cv2.putText(vis, f"共 {len(holes)} 发", (10, legend_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # 间距信息
        if len(sorted_holes) >= 2:
            dys = []
            for i in range(1, len(sorted_holes)):
                dy = sorted_holes[i].y - sorted_holes[i-1].y
                dys.append(dy)
            
            legend_y += 30
            cv2.putText(vis, f"平均间距: {np.mean(dys):.1f}px", (10, legend_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            legend_y += 25
            cv2.putText(vis, f"最大间距: {max(dys):.1f}px  (第{dys.index(max(dys))+1}→{dys.index(max(dys))+2}发)", 
                       (10, legend_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            legend_y += 25
            cv2.putText(vis, f"最小间距: {min(dys):.1f}px  (第{dys.index(min(dys))+1}→{dys.index(min(dys))+2}发)", 
                       (10, legend_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        self.logger.save_image("bullet_holes_marked", vis)
        return vis
    
    def generate_trajectory_chart(self, holes):
        """生成弹道间距柱状图"""
        if len(holes) < 2:
            return None
        
        sorted_holes = sorted(holes, key=lambda h: h.shot_num)
        
        # 计算间距
        data = []
        for i in range(1, len(sorted_holes)):
            dx = sorted_holes[i].x - sorted_holes[i-1].x
            dy = sorted_holes[i].y - sorted_holes[i-1].y
            data.append({
                'shot': sorted_holes[i].shot_num,
                'dx': dx,
                'dy': dy,
                'dist': np.sqrt(dx**2 + dy**2)
            })
        
        # 画图
        width = 900
        height = 400
        chart = np.zeros((height, width, 3), dtype=np.uint8)
        chart[:] = (30, 30, 30)
        
        if not data:
            return chart
        
        max_dy = max(abs(d['dy']) for d in data)
        if max_dy == 0:
            max_dy = 1
        
        bar_width = max(15, (width - 80) // len(data))
        chart_height = height - 100
        baseline = 60
        
        # Y 轴刻度
        for i in range(0, int(max_dy) + 5, 5):
            y = baseline + int(i / max_dy * (chart_height - baseline))
            cv2.line(chart, (50, y), (70, y), (150, 150, 150), 1)
            cv2.putText(chart, f"{i}px", (10, y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        
        # 画柱状图
        for i, d in enumerate(data):
            x = 80 + i * bar_width
            bar_h = int(abs(d['dy']) / max_dy * (chart_height - baseline))
            
            if d['dy'] > 0:
                y_end = baseline + (chart_height - baseline) - bar_h
            else:
                y_end = baseline + (chart_height - baseline) + bar_h
            
            # 柱子颜色
            if d['dy'] < 2:
                color = (0, 0, 255)  # 红 - 异常
            elif d['dy'] < 8:
                color = (0, 165, 255)  # 橙 - 偏小
            elif d['dy'] > 20:
                color = (255, 100, 0)  # 深蓝 - 偏大
            else:
                color = (0, 255, 0)  # 绿 - 正常
            
            cv2.rectangle(chart, (x, y_end), (x + bar_width - 2, baseline + chart_height - baseline),
                         color, -1)
            
            # 数值
            cv2.putText(chart, f"{d['dy']:.0f}", (x + 3, y_end - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            
            # X 轴标签
            cv2.putText(chart, str(d['shot']), (x + bar_width // 2 - 5, height - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # 标题
        cv2.putText(chart, "每发子弹间距 (Y轴)", (width//2 - 80, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        self.logger.save_image("trajectory_chart", chart)
        return chart
    
    def compare_with_json(self, holes, gun_name="m762", scope_name="hongdian"):
        """与实际弹道 JSON 对比"""
        if len(holes) < 2:
            return None
        
        sorted_holes = sorted(holes, key=lambda h: h.shot_num)
        
        # 加载 JSON
        gun_path = self.gun_data_dir / f"{gun_name.lower()}.json"
        if not gun_path.exists():
            print(f"⚠ 找不到 {gun_path}")
            return None
        
        with open(gun_path, 'r', encoding='utf-8') as f:
            gun_data = json.load(f)
        
        # 获取理论弹道（默认无配件 A0B0C0）
        json_key = "A0B0C0"
        json_ballistic = gun_data.get(json_key, [])
        
        if not json_ballistic:
            print(f"⚠ {gun_name} 无弹道数据")
            return None
        
        # 加载 config 获取倍镜系数
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            sensitivity = config.get('sensitivity', {})
            scope_value = sensitivity.get(scope_name.lower(), 1.0)
        except:
            scope_value = 1.0
        
        posture = gun_data.get('none', 1)
        
        # 计算实际间距
        actual_dys = []
        for i in range(1, min(len(sorted_holes), len(json_ballistic) // 2 + 1)):
            dy = sorted_holes[i].y - sorted_holes[i-1].y
            actual_dys.append(dy)
        
        if not actual_dys:
            return None
        
        # JSON 理论间距：每隔 2 个值取 1 个（[Y, 0, Y, 0, ...] 格式）
        json_dys = [json_ballistic[i] for i in range(0, len(actual_dys) * 2, 2)]
        
        # 理论值 = JSON值 × 倍镜系数 × 姿态系数
        json_theoretical = [j * scope_value * posture for j in json_dys if j != 0]
        actual_valid = [d for d in actual_dys if d > 0]
        
        print(f"\n{'='*60}")
        print(f"  弹道对比分析")
        print(f"{'='*60}")
        print(f"枪械: {gun_name.upper()} | 倍镜: {scope_name} | 姿态: 站立")
        print(f"当前倍镜系数: {scope_value}")
        print(f"姿态系数: {posture}")
        
        print(f"\n{'发数':>4} {'实际间距':>10} {'理论间距':>10} {'比值':>8} {'状态'}")
        print(f"{'-'*50}")
        
        ratios = []
        for i in range(min(len(actual_valid), len(json_theoretical))):
            ratio = actual_valid[i] / json_theoretical[i] if json_theoretical[i] > 0 else 0
            ratios.append(ratio)
            
            if ratio > 1.3:
                status = "⚠ 偏大"
            elif ratio < 0.7:
                status = "⚠ 偏小"
            else:
                status = "✅ 正常"
            
            print(f"{i+1:>4} {actual_valid[i]:>10.1f} {json_theoretical[i]:>10.1f} {ratio:>8.2f} {status}")
        
        if ratios:
            avg_ratio = np.mean(ratios)
            std_ratio = np.std(ratios)
            suggested_scope = round(scope_value * avg_ratio, 2)
            
            print(f"\n{'-'*50}")
            print(f"平均比值: {avg_ratio:.3f} (标准差: {std_ratio:.3f})")
            print(f"建议倍镜系数: {suggested_scope} (当前: {scope_value}, 调整: {abs(suggested_scope-scope_value):.2f})")
            
            if avg_ratio > 1.1:
                print("📈 实际间距大于理论值，建议调大倍镜系数")
            elif avg_ratio < 0.9:
                print("📉 实际间距小于理论值，建议调小倍镜系数")
            else:
                print("✅ 当前参数基本准确")
            
            # 保存对比结果
            result = {
                'gun': gun_name,
                'scope': scope_name,
                'current_scope_value': scope_value,
                'suggested_scope_value': suggested_scope,
                'avg_ratio': round(float(avg_ratio), 3),
                'std_ratio': round(float(std_ratio), 3),
                'details': []
            }
            for i in range(min(len(actual_valid), len(json_theoretical))):
                result['details'].append({
                    'shot': i + 1,
                    'actual_dy': round(float(actual_valid[i]), 1),
                    'json_dy': round(float(json_theoretical[i]), 1),
                    'ratio': round(float(ratios[i]), 3)
                })
            
            self.logger.save_json("calibration_result", result)
            return result
        
        return None
    
    def run_calibration(self, gun_name="m762", scope_name="hongdian"):
        """运行完整校准流程"""
        print("\n" + "="*60)
        print("  PUBG 弹痕校准工具")
        print("="*60)
        print(f"\n配置：{gun_name.upper()} | {scope_name} 倍镜")
        print(f"分辨率：{self.resolution}")
        print(f"截图区域：{self.roi}")
        
        # 步骤1：拍摄基线
        print(f"\n{'='*60}")
        print("  第1步：拍摄空白墙面基线")
        print("="*60)
        print("1. 进训练场，拿好枪")
        print("2. 开镜，对准空白墙面")
        print("3. 确认画面干净，没有弹痕/杂物")
        input("\n就绪后按回车...")
        
        self.base_image = self.capture_screen()
        self.logger.save_image("base_wall", self.base_image)
        print("✓ 基线已保存")
        
        # 步骤2：告诉打了多少发
        print(f"\n{'='*60}")
        print("  第2步：开火 + 拍摄结果")
        print("="*60)
        shot_count_str = input("请告诉我打了几发子弹: ").strip()
        try:
            self.shot_count = int(shot_count_str)
        except:
            print(f"⚠ 输入无效，默认为 10 发")
            self.shot_count = 10
        
        print(f"\n现在去打枪，可分多次打同一面墙")
        print(f"打完回到原位后，按回车拍摄...")
        input(f"确认要打 {self.shot_count} 发，回车保存结果图...")
        
        self.result_image = self.capture_screen()
        self.logger.save_image("result_wall", self.result_image)
        print("✓ 结果图已保存")
        
        # 步骤3：检测弹痕
        print(f"\n{'='*60}")
        print("  第3步：弹痕检测")
        print("="*60)
        holes = self.detect_holes(self.base_image, self.result_image)
        
        if not holes:
            print("✗ 未检测到弹痕，请检查：")
            print("  1. 基线和结果图是不是同一个位置")
            print("  2. 弹痕是否在截图区域内")
            print("  3. 可以尝试调整识别参数")
            return None
        
        # 步骤4：标注序号
        sorted_holes = self.sort_holes_by_shooting_order(holes, self.shot_count)
        
        # 步骤5：可视化
        print(f"\n{'='*60}")
        print(f"  第4步：生成可视化")
        print(f"{'='*60}")
        self.generate_visualization(self.base_image, self.result_image, sorted_holes)
        self.generate_trajectory_chart(sorted_holes)
        
        # 步骤6：对比 JSON
        print(f"\n{'='*60}")
        print("  第5步：参数对比")
        print(f"{'='*60}")
        result = self.compare_with_json(sorted_holes, gun_name, scope_name)
        
        return {
            'holes': sorted_holes,
            'result': result,
            'shot_count': self.shot_count
        }
    
    def run_manual_edit(self, result_data):
        """手动修正弹痕标注"""
        if not result_data or 'holes' not in result_data:
            return
        
        print(f"\n{'='*60}")
        print("  弹痕手动修正")
        print("="*60)
        print("功能尚未实现 GUI 手动编辑，建议直接查看可视化图片后修改弹痕坐标")
        print(f"查看目录: {self.logger.save_dir}")
        print("后续版本将支持交互式修正")


def show_help():
    print("""
    PUBG 弹痕校准工具 - 使用说明
    ════════════════════════════

    运行方式：
      python bullet_hole_calibrate.py [枪名] [倍镜名]

    参数：
      枪名：m762, akm, m416, scar-l, aug, ...（默认 m762）
      倍镜：none, hongdian, quanxi, 2bei, 3bei, 4bei, 6bei, 8bei, 15bei（默认 hongdian）

    示例：
      python bullet_hole_calibrate.py                    # 默认 M762 + 红点
      python bullet_hole_calibrate.py m416 4bei          # M416 + 4倍镜
      python bullet_hole_calibrate.py akm quanxi         # AKM + 全息

    操作步骤：
      1. 进训练场，拿好枪装好配件
      2. 开镜对准空白墙面
      3. 运行程序，按提示拍摄基线
      4. 手动打 N 发子弹（可分多次）
      5. 回到原位，拍摄结果图
      6. 程序自动识别弹痕，输出参数建议

    输出：
      - 标注弹痕编号的墙面图
      - 每发子弹间距柱状图
      - 与 JSON 理论弹道的对比表
      - 建议的倍镜系数调整值

    依赖：
      pip install mss opencv-python numpy keyboard
    """)


def main():
    # 解析参数
    gun_name = sys.argv[1] if len(sys.argv) > 1 else "m762"
    scope_name = sys.argv[2] if len(sys.argv) > 2 else "hongdian"
    
    print(f"🎯 压枪校准：{gun_name.upper()} + {scope_name}")
    
    analyzer = BulletHoleAnalyzer(resolution="3840x2160")
    result = analyzer.run_calibration(gun_name, scope_name)
    
    if result and result['result']:
        print(f"\n✅ 校准完成！")
        print(f"   建议倍镜系数: {result['result']['suggested_scope_value']}")
    elif result:
        print(f"\n✅ 弹痕检测完成，共 {result['shot_count']} 发")
        print(f"   查看可视化图片: {analyzer.logger.save_dir}")
    else:
        print(f"\n❌ 校准失败")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        show_help()
    else:
        main()
