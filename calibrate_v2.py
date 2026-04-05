#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 弹痕校准工具 V2 - 自动识别枪/配件/姿势 + 弹痕离线分析

复用现有识别模块：
  - recognition.py  → 自动识别枪械名称、倍镜、枪口、握把、枪托
  - fire_data.py    → 配件码映射 (KEY_DATA)
  - Process.py      → 单例 ProcessClass（直接调用它的识别结果）

流程：
1. 按 Tab 打开背包 → 自动识别枪+配件+姿势
2. 对准空白墙面 → 拍基线
3. 手动打 N 发（分多次也行）
4. 回到原位 → 拍结果图
5. 自动识别弹痕 → 可视化 → 对比 JSON → 出参数建议

依赖：opencv-python, numpy, mss, simplejson, keyboard
"""

import cv2
import numpy as np
import mss
import sys
import os
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime

# 复用项目现有模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fire_data import KEY_DATA
from resolution_setting import RESOLUTION_SETTINGS, Zishi
from Process import ProcessClass

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

# 截图区域（墙面弹痕用 1080p）
WALL_ROI = {
    "3840x2160": (0, 0, 1920, 1080),
    "2560x1440": (0, 0, 1920, 1080),
    "1920x1080": (0, 0, 1920, 1080),
}

# 弹痕识别参数
DEFAULT_MIN_AREA = 20
DEFAULT_MAX_AREA = 800
DEFAULT_MIN_CIRCULARITY = 0.25
DEFAULT_COLOR_THRESHOLD = 15


class RecoilLogger:
    def __init__(self, save_dir="./calibration_results"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    def save_image(self, name, img):
        path = self.save_dir / f"{self.timestamp}_{name}.png"
        cv2.imwrite(str(path), img)
        return path

    def save_json(self, name, data):
        path = self.save_dir / f"{self.timestamp}_{name}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path


class GunRecognizer:
    """复用 ProcessClass 的识别能力"""
    
    def __init__(self):
        self.PC = ProcessClass()
        self.resolution = self.PC.Monitor
        self.gun_info = None
        self.posture = "none"
        self.scope_name = "none"
        self.gun_name = "m762"
        self.accessories_code = "A0B0C0"
        self.scope_value = 1.0
        self.posture_value = 1.0

    def recognize(self):
        """执行完整识别：武器+配件+姿势"""
        print("\n" + "="*60)
        print("  步骤1：自动识别枪械信息")
        print("="*60)
        print("  📸 识别武器和配件...")
        self.PC.recognize_all_guns_info(lambda ev, data: None)
        time.sleep(0.3)
        
        # 关闭背包
        print("  → 关闭背包...")
        if HAS_KEYBOARD:
            keyboard.press('tab')
            keyboard.release('tab')
        else:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(0x09, 0, 0, 0)
            time.sleep(0.1)
            user32.keybd_event(0x09, 0, 2, 0)
        time.sleep(1.5)
        
        # 姿势识别
        print("  📸 识别姿势...")
        self.PC.recognize_zishi_info()
        self.posture = self.PC.Current_posture.lower()
        if self.posture not in ('none', 'c', 'z'):
            self.posture = "none"
        
        # 获取识别结果
        guns = self.PC.get_guns_info()
        if not guns or guns.get("Name", "None") in ("None", "", None):
            print("  ⚠ 未识别到枪械，请确认背包已正确打开")
            manual = input("  输入枪械JSON文件名 (留空=m762): ").strip()
            self.gun_name = manual if manual else "m762"
            guns = {"Name": self.gun_name, "Scope": "hongdian",
                    "Muzzle": "none", "Grip": "none", "Stock": "none"}
        else:
            raw_name = guns.get("Name", "m762")
            self.gun_name = self._to_gun_filename(raw_name)
        
        # 解析配件码
        self.scope_name = guns.get("Scope", "none").lower()
        muzzle = guns.get("Muzzle", "none").lower()
        grip = guns.get("Grip", "none").lower()
        stock = guns.get("Stock", guns.get("GunStock", "none")).lower()
        
        muzzle_code = KEY_DATA["Muzzle"].get(muzzle, "0")
        grip_code = KEY_DATA["Grip"].get(grip, "0")
        stock_code = KEY_DATA["Stock"].get(stock, "0")
        self.accessories_code = f"A{muzzle_code}B{grip_code}C{stock_code}"
        
        # 读取配置获取倍镜系数
        try:
            config = self.PC.get_config_data('a')
            sensitivity = config.get('sensitivity', {})
            self.scope_value = sensitivity.get(self.scope_name, 1.0)
        except Exception as e:
            print(f"  ⚠ 读取配置失败: {e}")
            self.scope_value = 1.0
        
        # 姿态系数从枪 JSON 读
        gun_path = Path(f"./_internal/GunData/{self.gun_name}.json")
        if gun_path.exists():
            with open(gun_path, 'r', encoding='utf-8') as f:
                gun_data = json.load(f)
            self.posture_value = gun_data.get(self.posture, 1)
        
        # 打印结果
        print(f"\n  {'━'*50}")
        print(f"  枪械: {self.gun_name}")
        print(f"  倍镜: {self.scope_name} (系数: {self.scope_value})")
        print(f"  枪口: {muzzle} (码: {muzzle_code})")
        print(f"  握把: {grip} (码: {grip_code})")
        print(f"  枪托: {stock} (码: {stock_code})")
        print(f"  姿势: {self.posture} (系数: {self.posture_value})")
        print(f"  配件码: {self.accessories_code}")
        print(f"  {'━'*50}")
        
        self.gun_info = guns
        return self.gun_info

    def _to_gun_filename(self, name):
        """中文名/拼音 → JSON 文件名"""
        name_map = {
            "m762": "m762", "akm": "akm", "m416": "m416",
            "scar-l": "scar-l", "aug": "aug", "groza": "groza",
            "dp28": "dp28", "m249": "m249",
            "uzi": "uzi", "micro_uzi": "uzi",
            "vector": "vector", "mp5k": "mp5k", "ump45": "ump45",
            "mini14": "mini14", "sks": "sks", "qbz": "qbz",
            "g36c": "g36c", "mk12": "mk12", "mk14": "mk14",
            "mk47": "mk47", "qbu": "qbu", "vss": "vss",
            "mg3": "mg3", "js9": "js9", "k2": "k2",
            "p90": "p90", "pp19": "pp19", "famas": "famas",
            "ace32": "ace32",
        }
        n = name.lower().strip()
        return name_map.get(n, n)

    def _posture_cn(self, p):
        m = {"none": "站立", "c": "蹲下", "z": "趴下"}
        return m.get(p, p)

    def _scope_cn(self, s):
        m = {"none":"机瞄","hongdian":"红点","quanxi":"全息",
             "2bei":"2倍","3bei":"3倍","4bei":"4倍",
             "6bei":"6倍","8bei":"8倍","15bei":"15倍"}
        return m.get(s, s)


class BulletHoleAnalyzer:
    """弹痕分析与可视化"""
    
    def __init__(self, resolution="3840x2160"):
        self.resolution = resolution
        self.roi = WALL_ROI.get(resolution, WALL_ROI["3840x2160"])
        self.logger = RecoilLogger()
        self.shot_count = 0
        self.base_image = None
        self.result_image = None
        self.min_area = DEFAULT_MIN_AREA
        self.max_area = DEFAULT_MAX_AREA
        self.min_circularity = DEFAULT_MIN_CIRCULARITY
        self.color_threshold = DEFAULT_COLOR_THRESHOLD

    def capture_screen(self):
        """截取屏幕 ROI"""
        x, y, w, h = self.roi
        with mss.mss() as sct:
            monitor = {"left": x, "top": y, "width": w, "height": h}
            return np.array(sct.grab(monitor))
    
    def detect_holes(self, base_img, result_img):
        """帧差法检测弹痕"""
        print("\n🔍 开始检测弹痕...")
        
        base_gray = cv2.cvtColor(base_img, cv2.COLOR_BGR2GRAY)
        result_gray = cv2.cvtColor(result_img, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(base_gray, result_gray)
        _, thresh = cv2.threshold(diff, 0, 255,
                                   cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
        thresh = cv2.dilate(thresh, kernel, iterations=2)
        
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        
        holes = []
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
            
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            
            mask = np.zeros(base_gray.shape[:2], dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            mean_base = cv2.mean(base_gray, mask=mask)[0]
            mean_result = cv2.mean(result_gray, mask=mask)[0]
            color_diff = abs(mean_result - mean_base)
            if color_diff < self.color_threshold:
                continue
            
            holes.append({
                'x': cx, 'y': cy, 'area': area,
                'circularity': circularity, 'color_diff': color_diff
            })
        
        print(f"  找到 {len(holes)} 个弹痕")
        return holes
    
    def sort_holes(self, holes):
        """按射击顺序排序"""
        if len(holes) <= 1:
            if holes: holes[0]['shot_num'] = 1
            return holes
        
        sorted_holes = sorted(holes, key=lambda h: (h['y'], h['x']))
        mid = len(sorted_holes) // 2
        top_avg = np.mean([h['y'] for h in sorted_holes[:mid]])
        bot_avg = np.mean([h['y'] for h in sorted_holes[mid:]])
        if bot_avg < top_avg:
            sorted_holes = sorted_holes[::-1]
        
        for i, h in enumerate(sorted_holes):
            h['shot_num'] = i + 1
        return sorted_holes
    
    def generate_visualization(self, result_img, holes):
        """弹痕标注：编号 + 连线 + 间距"""
        h, w = result_img.shape[:2]
        vis = result_img.copy()
        s = sorted(holes, key=lambda x: x['shot_num'])
        
        for i in range(len(s) - 1):
            dy = s[i+1]['y'] - s[i]['y']
            if dy < 5: color = (0, 0, 255)
            elif dy < 15: color = (0, 255, 255)
            else: color = (0, 255, 0)
            cv2.line(vis, (s[i]['x'], s[i]['y']),
                     (s[i+1]['x'], s[i+1]['y']), color, 2)
            cv2.arrowedLine(vis, (s[i]['x'], s[i]['y']),
                            (s[i+1]['x'], s[i+1]['y']), color, 2, tipLength=0.3)
        
        for hv in s:
            n = hv['shot_num']
            if n <= 5: color = (0, 0, 255)
            elif n <= 15: color = (0, 165, 255)
            else: color = (0, 255, 0)
            cv2.circle(vis, (hv['x'], hv['y']), 10, color, 2)
            cv2.circle(vis, (hv['x'], hv['y']), 3, color, -1)
            cv2.putText(vis, str(n), (hv['x']+14, hv['y']-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
        
        if len(s) >= 2:
            dys = [s[i]['y']-s[i-1]['y'] for i in range(1, len(s))]
            y = 35
            cv2.putText(vis, f"共 {len(holes)} 发",
                       (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2); y+=28
            cv2.putText(vis, f"平均间距: {np.mean(dys):.1f}px",
                       (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2); y+=28
            mi = dys.index(max(dys))
            cv2.putText(vis, f"最大: {max(dys):.1f}px ({mi+1}→{mi+2}发)",
                       (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2); y+=28
            mi = dys.index(min(dys))
            cv2.putText(vis, f"最小: {min(dys):.1f}px ({mi+1}→{mi+2}发)",
                       (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2)
        
        self.logger.save_image("bullet_holes_marked", vis)
        print(f"  ✅ 弹痕标注图已保存")
        return vis
    
    def generate_trajectory_chart(self, holes):
        """柱状图：每发子弹 Y 间距"""
        if len(holes) < 2: return None
        s = sorted(holes, key=lambda h: h['shot_num'])
        data = [{'shot': s[i]['shot_num'],
                 'dy': s[i]['y']-s[i-1]['y']} for i in range(1, len(s))]
        
        W, H = 1000, 450
        chart = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.putText(chart, "Bullet Spacing (Y-axis px)",
                   (W//2-130, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        
        max_dy = max(abs(d['dy']) for d in data) or 1
        bar_w = max(18, (W - 110) // len(data))
        plot_h = H - 140
        base = 70
        
        for i, d in enumerate(data):
            x = 90 + i * bar_w
            bh = int(abs(d['dy']) / max_dy * plot_h)
            dy = d['dy']
            if dy < 2: c = (0,0,255)
            elif dy < 8: c = (0,165,255)
            elif dy > 20: c = (255,100,0)
            else: c = (0,255,0)
            
            cv2.rectangle(chart, (x, base+plot_h-bh), (x+bar_w-3, base+plot_h), c, -1)
            cv2.putText(chart, f"{dy:.0f}", (x+3, base+plot_h-bh-5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
            cv2.putText(chart, str(d['shot']), (x+bar_w//2-5, H-15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255,255,255), 1)
        
        # Y 轴
        cv2.line(chart, (82, 60), (82, base+plot_h+5), (100,100,100), 1)
        for px in range(0, int(max_dy)+5, 5):
            yy = base + plot_h - int(px / max_dy * plot_h)
            cv2.line(chart, (75, yy), (82, yy), (100,100,100), 1)
            cv2.putText(chart, f"{px}", (50, yy+4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180,180,180), 1)
        
        self.logger.save_image("trajectory_chart", chart)
        print(f"  ✅ 间距柱状图已保存")
        return chart
    
    def compare_with_json(self, holes, gun_name, acc_code, scope_val, posture_val, gr):
        """对比实际 vs JSON"""
        if len(holes) < 2: return None
        s = sorted(holes, key=lambda h: h['shot_num'])
        
        gun_path = Path(f"./_internal/GunData/{gun_name.lower()}.json")
        if not gun_path.exists():
            print(f"⚠ 找不到 {gun_path}")
            return None
        with open(gun_path, 'r', encoding='utf-8') as f:
            gun_data = json.load(f)
        
        raw = gun_data.get(acc_code, [])
        if not raw:
            raw = gun_data.get("A0B0C0", [])
            if not raw:
                print(f"⚠ 无弹道数据")
                return None
        
        actual = [s[i]['y']-s[i-1]['y'] for i in range(1, len(s))]
        json_dys = [raw[j] for j in range(0, min(len(actual)*2, len(raw)), 2)]
        theory = [j * scope_val * posture_val for j in json_dys if j != 0]
        actual_v = [d for d in actual if d > 0]
        
        print(f"\n{'='*60}")
        print("  📊  对比分析")
        print(f"{'='*60}")
        print(f"  枪械: {gr.gun_name} | 配件码: {acc_code}")
        print(f"  倍镜: {gr._scope_cn(gr.scope_name)} ({gr.scope_name}) 系数={scope_val}")
        print(f"  姿势: {gr._posture_cn(gr.posture)} 系数={posture_val}")
        print(f"{'  ':->50}")
        print(f"  {'发数':>4} {'实际':>8} {'理论':>8} {'比值':>8} {'状态'}")
        print(f"  {'-':->46}")
        
        ratios = []
        for i in range(min(len(actual_v), len(theory))):
            r = actual_v[i] / theory[i] if theory[i] > 0 else 0
            ratios.append(r)
            if r > 1.3: st = "⚠偏大"
            elif r < 0.7: st = "⚠偏小"
            else: st = "✅正常"
            print(f"  {i+1:>4} {actual_v[i]:>8.1f} {theory[i]:>8.1f} {r:>8.2f} {st}")
        
        if ratios:
            avg = np.mean(ratios)
            std = np.std(ratios)
            suggested = round(scope_val * avg, 2)
            print(f"  {'-':->46}")
            print(f"  平均比值: {avg:.3f} (标准差: {std:.3f})")
            print(f"  建议倍镜系数: {suggested} (当前: {scope_val})")
            if avg > 1.1: print("  📈 建议调大")
            elif avg < 0.9: print("  📉 建议调小")
            else: print("  ✅ 基本准确")
            
            result = {
                'gun': gun_name, 'accessories_code': acc_code,
                'scope_name': gr.scope_name, 'current_scope': scope_val,
                'suggested_scope': suggested,
                'posture': gr.posture, 'posture_value': posture_val,
                'avg_ratio': round(float(avg), 3),
                'std_ratio': round(float(std), 3),
                'shot_count': len(actual_v)+1, 'details': []
            }
            for i in range(min(len(actual_v), len(theory))):
                result['details'].append({
                    'shot': i+1,
                    'actual_dy': round(float(actual_v[i]), 1),
                    'json_dy': round(float(theory[i]), 1),
                    'ratio': round(float(ratios[i]), 3)
                })
            self.logger.save_json("calibration_result", result)
            return result
        return None

    def run(self, gr):
        """运行完整校准"""
        # 步骤2：拍基线
        print("\n" + "="*60)
        print("  步骤2：拍摄空白墙面基线")
        print("="*60)
        print("  1. 开镜，对准空白墙面")
        print("  2. 确认画面干净")
        input("  就绪后按回车...")
        
        self.base_image = self.capture_screen()
        self.logger.save_image("base_wall", self.base_image)
        print("  ✓ 基线已保存")
        
        # 步骤3：开火
        print("\n" + "="*60)
        print("  步骤3：开火 + 拍摄结果")
        print("="*60)
        shot_str = input("  打了几发？: ").strip()
        try: self.shot_count = int(shot_str)
        except: self.shot_count = 10
        
        print(f"\n  去打枪（可分多次），打完后回来按回车...")
        input("  确认已打完，按回车拍摄结果图...")
        
        self.result_image = self.capture_screen()
        self.logger.save_image("result_wall", self.result_image)
        print("  ✓ 结果图已保存")
        
        # 步骤4：检测
        print("\n" + "="*60)
        print("  步骤4：弹痕检测 + 可视化")
        print("="*60)
        holes = self.detect_holes(self.base_image, self.result_image)
        if not holes:
            print("  ✗ 未检测到弹痕")
            return None
        
        s = self.sort_holes(holes)
        self.generate_visualization(self.result_image, s)
        self.generate_trajectory_chart(s)
        
        # 步骤5：对比
        print("\n" + "="*60)
        print("  步骤5：参数对比")
        print("="*60)
        result = self.compare_with_json(
            s, gr.gun_name, gr.accessories_code,
            gr.scope_value, gr.posture_value, gr
        )
        
        return {'holes': s, 'result': result, 'shot_count': self.shot_count}


def main():
    print("""
    PUBG 弹痕校准工具 V2
    ══════════════════════
    自动识别枪/配件/姿势 + 弹痕分析
    """)
    
    # 1. 识别
    gr = GunRecognizer()
    gr.recognize()
    
    # 2. 校准
    analyzer = BulletHoleAnalyzer(gr.resolution)
    result = analyzer.run(gr)
    
    if result and result['result']:
        print(f"\n✅ 校准完成！")
        print(f"   建议倍镜系数: {result['result']['suggested_scope']}")
        print(f"   保存目录: {analyzer.logger.save_dir}")
    elif result:
        print(f"\n✅ 检测完成，{result['shot_count']} 发")
        print(f"   保存目录: {analyzer.logger.save_dir}")
    else:
        print(f"\n❌ 校准失败")


if __name__ == "__main__":
    main()
