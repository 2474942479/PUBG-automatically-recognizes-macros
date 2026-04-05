#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 弹痕校准工具
══════════════════
1. 自动识别枪械/配件/姿势
2. 快捷键截图（F5 基线 → 打枪 → F6 结果 → F7 分析）
3. 弹痕可视化 + JSON 对比 + 参数建议
4. 分析后可交互式修正弹痕编号/间距

运行：python calibrate.py
依赖：opencv-python, numpy, mss, keyboard（可选，有键盘库用快捷键，无则手动输入）
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

WALL_ROI = {
    "3840x2160": (0, 0, 1920, 1080),
    "2560x1440": (0, 0, 1920, 1080),
    "1920x1080": (0, 0, 1920, 1080),
}

MIN_AREA = 20
MAX_AREA = 800
MIN_CIRCULARITY = 0.25
COLOR_THRESHOLD = 15


# ═══════════════════════════════════════════
# 日志 & 文件保存
# ═══════════════════════════════════════════

class Logger:
    def __init__(self, save_dir="./calibration_results"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    def save_image(self, name, img):
        path = self.save_dir / f"{self.timestamp}_{name}.png"
        cv2.imwrite(str(path), img)
        print(f"    📷 {path.name}")
        return path

    def save_json(self, name, data):
        path = self.save_dir / f"{self.timestamp}_{name}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"    📄 {path.name}")
        return path


# ═══════════════════════════════════════════
# 枪械识别（复用 ProcessClass）
# ═══════════════════════════════════════════

class GunRecognizer:
    """
    按 Tab → 识别武器+配件 → 姿势 → 组装配件码
    全程自动，不用手动输入
    """
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
        print("\n" + "=" * 60)
        print("  步骤1：自动识别枪械信息")
        print("=" * 60)

        print("  📸 识别武器和配件...")
        self.PC.recognize_all_guns_info(lambda ev, data: None)
        time.sleep(0.3)

        print("  ➜ 关闭背包...")
        self._press_tab()
        time.sleep(1.5)

        print("  📸 识别姿势...")
        self.PC.recognize_zishi_info()
        self.posture = self.PC.Current_posture.lower()
        if self.posture not in ('none', 'c', 'z'):
            self.posture = "none"

        guns = self.PC.get_guns_info()
        raw = guns.get("Name", "m762") if guns else "m762"
        if not guns or guns.get("Name", "None") in ("None", "", None):
            print("  ⚠ 未识别到枪械")
            manual = input("  输入枪械JSON文件名 (留空=m762): ").strip()
            self.gun_name = manual if manual else "m762"
            guns = {"Name": self.gun_name, "Scope": "hongdian",
                    "Muzzle": "none", "Grip": "none", "Stock": "none"}
        else:
            self.gun_name = self._to_gun_filename(raw)

        self.scope_name = guns.get("Scope", "none").lower()
        muzzle = guns.get("Muzzle", "none").lower()
        grip = guns.get("Grip", "none").lower()
        stock = guns.get("Stock", guns.get("GunStock", "none")).lower()

        m_c = KEY_DATA["Muzzle"].get(muzzle, "0")
        g_c = KEY_DATA["Grip"].get(grip, "0")
        s_c = KEY_DATA["Stock"].get(stock, "0")
        self.accessories_code = f"A{m_c}B{g_c}C{s_c}"

        try:
            config = self.PC.get_config_data('a')
            self.scope_value = config.get('sensitivity', {}).get(self.scope_name, 1.0)
        except Exception as e:
            print(f"  ⚠ 读配置失败: {e}, 使用 1.0")
            self.scope_value = 1.0

        gp = Path(f"./_internal/GunData/{self.gun_name}.json")
        if gp.exists():
            with open(gp, encoding='utf-8') as f:
                self.posture_value = json.load(f).get(self.posture, 1)

        print(f"\n  \u2501" * 50)
        print(f"  枪械: {self.gun_name}")
        print(f"  倍镜: {self._scope_cn(self.scope_name)} ({self.scope_name}) 系数={self.scope_value}")
        print(f"  枪口: {muzzle} 码={m_c}")
        print(f"  握把: {grip} 码={g_c}")
        print(f"  枪托: {stock} 码={s_c}")
        print(f"  姿势: {self._posture_cn(self.posture)} 系数={self.posture_value}")
        print(f"  配件码: {self.accessories_code}")
        print(f"  \u2501" * 50)
        self.gun_info = guns
        return guns

    def _press_tab(self):
        if HAS_KEYBOARD:
            keyboard.press('tab'); keyboard.release('tab')
        else:
            import ctypes
            u = ctypes.windll.user32
            u.keybd_event(0x09, 0, 0, 0)
            time.sleep(0.1)
            u.keybd_event(0x09, 0, 2, 0)

    def _to_gun_filename(self, name):
        m = {"m762":"m762","akm":"akm","m416":"m416","scar-l":"scar-l",
             "aug":"aug","groza":"groza","dp28":"dp28","m249":"m249",
             "uzi":"uzi","micro_uzi":"uzi","vector":"vector","mp5k":"mp5k",
             "ump45":"ump45","mini14":"mini14","sks":"sks","qbz":"qbz",
             "g36c":"g36c","mk12":"mk12","mk14":"mk14","mk47":"mk47",
             "qbu":"qbu","vss":"vss","mg3":"mg3","js9":"js9","k2":"k2",
             "p90":"p90","pp19":"pp19","famas":"famas","ace32":"ace32"}
        return m.get(name.lower().strip(), name.lower().strip())

    def _posture_cn(self, p): return {"none":"站","c":"蹲","z":"趴"}.get(p, p)
    def _scope_cn(self, s):
        return {"none":"机瞄","hongdian":"红点","quanxi":"全息",
                "2bei":"2倍","3bei":"3倍","4bei":"4倍",
                "6bei":"6倍","8bei":"8倍","15bei":"15倍"}.get(s, s)


# ═══════════════════════════════════════════
# 弹痕分析器
# ═══════════════════════════════════════════

class Analyzer:
    def __init__(self, resolution="3840x2160"):
        self.resolution = resolution
        self.roi = WALL_ROI.get(resolution, WALL_ROI["3840x2160"])
        self.log = Logger()
        self.shot_count = 10
        self.base_image = None
        self.result_image = None

    def capture_screen(self):
        x, y, w, h = self.roi
        with mss.mss() as sct:
            monitor = {"left": x, "top": y, "width": w, "height": h}
            return np.array(sct.grab(monitor))

    def detect_holes(self, base, result):
        print("\n🔍 检测弹痕...")
        bg = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
        rg = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(bg, rg)
        _, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        k = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k, iterations=2)
        thresh = cv2.dilate(thresh, k, iterations=2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        holes = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (MIN_AREA < area < MAX_AREA): continue
            peri = cv2.arcLength(cnt, True)
            if peri == 0: continue
            circ = 4 * np.pi * (area / (peri * peri))
            if circ < MIN_CIRCULARITY: continue
            M = cv2.moments(cnt)
            if M["m00"] == 0: continue
            cx, cy = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])
            mask = np.zeros(bg.shape[:2], dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            cd = abs(cv2.mean(bg, mask=mask)[0] - cv2.mean(rg, mask=mask)[0])
            if cd < COLOR_THRESHOLD: continue
            holes.append({'x': cx, 'y': cy, 'area': area, 'circularity': circ})
        print(f"  找到 {len(holes)} 个弹痕")
        return holes

    def sort_holes(self, holes):
        if not holes: return holes
        s = sorted(holes, key=lambda h: (h['y'], h['x']))
        if len(s) > 1:
            mid = len(s) // 2
            if np.mean([h['y'] for h in s[mid:]]) < np.mean([h['y'] for h in s[:mid]]):
                s = s[::-1]
        for i, h in enumerate(s): h['shot_num'] = i + 1
        return s

    def visualize(self, img, holes):
        h, w = img.shape[:2]
        vis = img.copy()
        s = sorted(holes, key=lambda x: x['shot_num'])
        for i in range(len(s) - 1):
            dy = s[i+1]['y'] - s[i]['y']
            color = (0,0,255) if dy<5 else (0,255,255) if dy<15 else (0,255,0)
            cv2.line(vis, (s[i]['x'],s[i]['y']), (s[i+1]['x'],s[i+1]['y']), color, 2)
            cv2.arrowedLine(vis, (s[i]['x'],s[i]['y']), (s[i+1]['x'],s[i+1]['y']),
                            color, 2, tipLength=0.3)
        for hv in s:
            n = hv['shot_num']
            col = (0,0,255) if n<=5 else (0,165,255) if n<=15 else (0,255,0)
            cv2.circle(vis, (hv['x'],hv['y']), 10, col, 2)
            cv2.circle(vis, (hv['x'],hv['y']), 3, col, -1)
            cv2.putText(vis, str(n), (hv['x']+14,hv['y']-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
        if len(s) >= 2:
            dys = [s[i]['y']-s[i-1]['y'] for i in range(1, len(s))]
            y = 35
            for t in [
                f"共 {len(holes)} 发",
                f"平均间距: {np.mean(dys):.1f}px",
                f"最大: {max(dys):.1f}px ({dys.index(max(dys))+1}\u2192{dys.index(max(dys))+2}发)",
                f"最小: {min(dys):.1f}px ({dys.index(min(dys))+1}\u2192{dys.index(min(dys))+2}发)",
            ]:
                cv2.putText(vis, t, (10,y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2)
                y += 28
        self.log.save_image("bullet_holes_marked", vis)
        return vis

    def trajectory_chart(self, holes):
        if len(holes) < 2: return
        s = sorted(holes, key=lambda h: h['shot_num'])
        data = [{'shot': s[i]['shot_num'], 'dy': s[i]['y']-s[i-1]['y']} for i in range(1, len(s))]
        W, H = 1000, 450
        chart = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.putText(chart, "Bullet Spacing (Y-axis px)", (W//2-130,28),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        max_dy = max(abs(d['dy']) for d in data) or 1
        bar_w = max(18, (W-110)//len(data))
        ph, base = H-140, 70
        for i, d in enumerate(data):
            x, bh = 90+i*bar_w, int(abs(d['dy'])/max_dy*ph)
            c = (0,0,255) if d['dy']<2 else (0,165,255) if d['dy']<8 else (255,100,0) if d['dy']>20 else (0,255,0)
            cv2.rectangle(chart, (x, base+ph-bh), (x+bar_w-3, base+ph), c, -1)
            cv2.putText(chart, f"{d['dy']:.0f}", (x+3,base+ph-bh-5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
            cv2.putText(chart, str(d['shot']), (x+bar_w//2-5,H-15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255,255,255), 1)
        cv2.line(chart,(82,60),(82,base+ph+5),(100,100,100),1)
        for px in range(0,int(max_dy)+5,5):
            yy = base+ph-int(px/max_dy*ph)
            cv2.line(chart,(75,yy),(82,yy),(100,100,100),1)
            cv2.putText(chart,f"{px}",(50,yy+4),cv2.FONT_HERSHEY_SIMPLEX,0.35,(180,180,180),1)
        self.log.save_image("trajectory_chart", chart)

    def compare_with_json(self, holes, gr):
        if len(holes) < 2: return None
        s = sorted(holes, key=lambda h: h['shot_num'])
        gp = Path(f"./_internal/GunData/{gr.gun_name}.json")
        if not gp.exists():
            print(f"\u26a0 找不到 {gp}"); return None
        with open(gp, encoding='utf-8') as f:
            gun = json.load(f)
        raw = gun.get(gr.accessories_code, gun.get("A0B0C0", []))
        if not raw:
            print("\u26a0 无弹道数据"); return None

        actual = [s[i]['y']-s[i-1]['y'] for i in range(1, len(s))]
        jd = [raw[j] for j in range(0, min(len(actual)*2, len(raw)), 2)]
        theory = [j*gr.scope_value*gr.posture_value for j in jd if j != 0]
        av = [d for d in actual if d > 0]

        print(f"\n{'='*60}")
        print("  \U0001f4ca  对比分析")
        print(f"{'='*60}")
        print(f"  {'发数':>4} {'实际':>8} {'理论':>8} {'比值':>8} {'状态'}")
        print(f"  {'-'*42}")

        ratios = []
        for i in range(min(len(av), len(theory))):
            r = av[i]/theory[i] if theory[i]>0 else 0
            ratios.append(r)
            st = "\u26a0偏大" if r>1.3 else "\u26a0偏小" if r<0.7 else "\u2705正常"
            print(f"  {i+1:>4} {av[i]:>8.1f} {theory[i]:>8.1f} {r:>8.2f} {st}")

        if ratios:
            avg = np.mean(ratios)
            std = np.std(ratios)
            suggested = round(gr.scope_value * avg, 2)
            print(f"  {'-'*42}")
            print(f"  平均比值: {avg:.3f} (标准差: {std:.3f})")
            print(f"  建议倍镜系数: {suggested} (当前: {gr.scope_value})")
            if avg>1.1: print("  \U0001f4c8 建议调大")
            elif avg<0.9: print("  \U0001f4c9 建议调小")
            else: print("  \u2705 基本准确")
            result = {
                'gun': gr.gun_name, 'accessories_code': gr.accessories_code,
                'scope_name': gr.scope_name, 'current_scope': gr.scope_value,
                'suggested_scope': suggested,
                'posture': gr.posture, 'posture_value': gr.posture_value,
                'avg_ratio': round(float(avg), 3),
                'std_ratio': round(float(std), 3),
                'shot_count': len(av)+1, 'details': []
            }
            for i in range(min(len(av), len(theory))):
                r = av[i]/theory[i] if theory[i]>0 else 0
                result['details'].append({
                    'shot': i+1,
                    'actual_dy': round(float(av[i]), 1),
                    'json_dy': round(float(theory[i]), 1),
                    'ratio': round(float(r), 3)
                })
            self.log.save_json("calibration_result", result)
            return result
        return None

    def run(self, gr):
        """快捷键模式：F5/F6/F7/F8"""
        print("\n" + "="*60)
        print("  快捷键操作指南")
        print("="*60)
        print("  F5  \u2500 拍空白墙面（基线）")
        print("  F6  \u2500 拍打完后的墙面（结果）")
        print("  F7  \u2500 开始分析（检测弹痕 + 对比）")
        print("  F8  \u2500 退出")
        print("="*60)
        print("  流程：1.开镜对准墙 2.F5 3.打枪 4.F6 5.F7分析")
        print("="*60)

        key_q = queue.Queue()
        def on_key(event):
            if event.name in ('f5','f6','f7','f8'):
                key_q.put(event.name)

        if HAS_KEYBOARD:
            keyboard.on_press(on_key)

        base_done = False
        result_done = False

        while True:
            if not HAS_KEYBOARD:
                cmd = input("\n命令 (f5/f6/f7/f8): ").strip().lower()
                key = cmd
            else:
                key = key_q.get()

            if key == 'f5':
                print("  \U0001f4f8 基线...")
                self.base_image = self.capture_screen()
                self.log.save_image("base_wall", self.base_image)
                print("  \u2705 基线已保存")
                base_done = True

            elif key == 'f6':
                if not base_done:
                    print("  \u26a0 先按 F5 拍基线")
                    continue
                shot_s = input("  打了几发: ").strip()
                try: self.shot_count = int(shot_s)
                except: self.shot_count = 10
                self.result_image = self.capture_screen()
                self.log.save_image("result_wall", self.result_image)
                print("  \u2705 结果已保存")
                result_done = True

            elif key == 'f7':
                if not base_done:
                    print("  \u26a0 先按 F5 拍基线")
                    continue
                if not result_done:
                    shot_s = input("  打了几发: ").strip()
                    try: self.shot_count = int(shot_s)
                    except: self.shot_count = 10
                    self.result_image = self.capture_screen()
                    self.log.save_image("result_wall", self.result_image)
                    result_done = True
                break

            elif key == 'f8':
                print("  退出")
                return None

        if HAS_KEYBOARD:
            keyboard.unhook_all()

        # 分析
        print("\n" + "="*60)
        print("  分析中...")
        print("="*60)
        holes = self.detect_holes(self.base_image, self.result_image)
        if not holes:
            print("  \u2717 未检测到弹痕"); return None

        s = self.sort_holes(holes)
        self.visualize(self.result_image, s)
        self.trajectory_chart(s)

        result = self.compare_with_json(s, gr)
        if result:
            # 交互式修正
            self.interactive_edit(s, result, gr)

        return {'holes': s, 'result': result, 'shot_count': self.shot_count}

    def print_holes_table(self, holes, avg_ratio=None):
        """打印弹痕信息表"""
        s = sorted(holes, key=lambda h: h['shot_num'])
        print(f"\n  {'='*55}")
        print(f"  弹痕列表 (共 {len(s)} 发)")
        print(f"  {'='*55}")
        print(f"  {'编号':>4} {'  X':>6} {'  Y':>6} {'间距':>8} {' 比值':>8} {'状态':>8}")
        print(f"  {'-'*50}")
        for i, hv in enumerate(s):
            if i == 0:
                print(f"  {hv['shot_num']:>4} {hv['x']:>6} {hv['y']:>6} {'---':>8} {'---':>8} {'首发':>6}")
            else:
                dy = hv['y'] - s[i-1]['y']
                # 估算比值（基于当前平均比值）
                if avg_ratio:
                    theory_dy = 5  # 估算
                    ratio_est = dy / (theory_dy * 1.0)  # 简化
                    st = "\u26a0偏大" if dy>20 else "\u26a0偏小" if dy<2 else "\u2705"
                else:
                    ratio_est = "?"
                    st = "?"
                print(f"  {hv['shot_num']:>4} {hv['x']:>6} {hv['y']:>6} {dy:>8} {str(ratio_est):>8} {st:>6}")

    def interactive_edit(self, holes, result, gr):
        """交互式修正弹痕"""
        print(f"\n  {'='*55}")
        print(f"  交互修正 (可选)")
        print(f"  {'='*55}")
        self.print_holes_table(holes)

        while True:
            print(f"\n  1=修改Y值  2=删除弹痕  3=完成")
            choice = input("  选择: ").strip()

            if choice == '3':
                break
            elif choice == '1':
                n = input("  修改第几发? ").strip()
                try: n = int(n)
                except: continue
                idx = n - 1
                if 0 <= idx < len(holes):
                    old_y = holes[idx]['y']
                    new_y = input(f"  当前Y={old_y}, 新Y: ").strip()
                    try:
                        holes[idx]['y'] = int(new_y)
                        # 重新排序
                        holes = self.sort_holes(holes)
                        print(f"  \u2705 第{n}发Y改为{new_y}")
                    except: pass
                else:
                    print("  \u2717 编号不存在")
            elif choice == '2':
                n = input("  删除第几发? ").strip()
                try: n = int(n)
                except: continue
                idx = n - 1
                if 0 <= idx < len(holes):
                    holes.pop(idx)
                    holes = self.sort_holes(holes)
                    print(f"  \u2705 第{n}发已删除")
                    self.print_holes_table(holes)
                else:
                    print("  \u2717 编号不存在")
            else:
                print("  \u2717 无效选项")


def main():
    print("""
    PUBG 弹痕校准工具
    \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    自动识别枪/配件/姿势 + 弹痕分析
    快捷键：F5基线 | F6结果 | F7分析 | F8退出
    """)

    gr = GunRecognizer()
    gr.recognize()

    analyzer = Analyzer(gr.resolution)
    result = analyzer.run(gr)

    if result and result.get('result'):
        r = result['result']
        print(f"\n\u2705 \u2705 校准完成")
        print(f"   建议倍镜系数: {r['suggested_scope']}")
        print(f"   保存目录: {analyzer.log.save_dir}")
    elif result:
        print(f"\n\u2705 检测完成 ({result.get('shot_count')} 发)")
        print(f"   保存目录: {analyzer.log.save_dir}")
    else:
        print("\n\u2717 校准失败")


if __name__ == "__main__":
    main()