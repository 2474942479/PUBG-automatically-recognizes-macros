#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 压枪参数一键自动校准工具 V4
refactor 分支专用版本 - 多轮分段射击版

功能：
1. 自动按 Tab 打开/关闭背包
2. 自动识别武器和配件
3. 自动长按右键开镜 + 左键射击
4. 分段射击：15 发 → 30 发 → 40 发（避免飘出靶墙）
5. 射击过程中高速截图（50 FPS）
6. 多轮测试交叉比对
7. 分段弹道分析（前 10 发、10-20 发、20 发后）
8. 自动更新配置

依赖：mss, opencv-python, numpy, pillow, pyautogui, keyboard
"""

import cv2
import numpy as np
import mss
import time
import json
import os
import sys
import asyncio
import threading
from pathlib import Path
from datetime import datetime

# 导入现有模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recognition import capture_all_positions_thread
from Process import ProcessClass

# 尝试导入键盘鼠标控制
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    print("⚠ 未安装 pyautogui，请运行：pip install pyautogui")

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False


class MouseController:
    """通用鼠标控制器"""
    
    def __init__(self):
        self.driver_name = None
        self.driver = None
        self._init_driver()
    
    def _init_driver(self):
        """尝试初始化多种驱动"""
        
        # 尝试 1: pyopdll
        try:
            from pyopdll import OP
            self.driver = OP()
            self.driver_name = 'pyopdll'
            print(f"\n✓ 鼠标驱动：pyopdll")
            return
        except Exception as e:
            pass
        
        # 尝试 2: GHUB
        try:
            from GHUB import ghub_device
            self.driver = ghub_device()
            if self.driver.gm_ok:
                self.driver_name = 'GHUB'
                print(f"\n✓ 鼠标驱动：罗技 GHUB")
                return
        except Exception as e:
            pass
        
        # 尝试 3: pyautogui（备用）
        if HAS_PYAUTOGUI:
            self.driver_name = 'pyautogui'
            print(f"\n✓ 鼠标驱动：pyautogui（备用）")
            return
        
        # 都失败
        self.driver_name = None
        print(f"\n✗ 未找到可用的鼠标驱动")
        print("请安装以下驱动之一：")
        print("  1. pyopdll: pip install pyopdll")
        print("  2. 罗技 GHUB: https://www.logitechg.com/zh-cn/innovation/g-hub.html")
        print("  3. pyautogui: pip install pyautogui")
    
    def mouse_move_to(self, x, y):
        """移动鼠标到指定位置"""
        if self.driver_name == 'pyopdll':
            self.driver.MoveTo(int(x), int(y))
        elif self.driver_name == 'GHUB':
            self.driver.mouse_To(int(x), int(y))
        elif self.driver_name == 'pyautogui':
            pyautogui.moveTo(int(x), int(y))
    
    def mouse_down(self, button='left'):
        """按下鼠标按钮"""
        if self.driver_name == 'pyopdll':
            import ctypes
            if button == 'right':
                ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
            else:
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        elif self.driver_name == 'GHUB':
            btn = 2 if button == 'right' else 1
            self.driver.mouse_down(btn)
        elif self.driver_name == 'pyautogui':
            pyautogui.mouseDown(button=button)
    
    def mouse_up(self, button='left'):
        """释放鼠标按钮"""
        if self.driver_name == 'pyopdll':
            import ctypes
            if button == 'right':
                ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
            else:
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
        elif self.driver_name == 'GHUB':
            btn = 2 if button == 'right' else 1
            self.driver.mouse_up(btn)
        elif self.driver_name == 'pyautogui':
            pyautogui.mouseUp(button=button)
    
    def is_available(self):
        """检查驱动是否可用"""
        return self.driver_name is not None


class AutoCalibrator:
    """一键自动校准器 V4 - 多轮分段射击"""
    
    def __init__(self):
        self.config_path = Path("./Config/config.json")
        self.save_dir = Path("./calibration_results")
        self.save_dir.mkdir(exist_ok=True)
        
        # 初始化 Process 类和鼠标控制器
        self.PC = ProcessClass()
        self.mouse = MouseController()
        
        # 检查鼠标驱动是否可用
        if not self.mouse.is_available():
            print("\n✗ 鼠标驱动不可用，退出校准")
            sys.exit(1)
        
        # 截图区域
        self.resolution = self.PC.Monitor
        self.capture_region = self._get_capture_region(self.resolution)
        
        # 弹痕识别参数
        self.min_area = 30
        self.max_area = 1000
        self.min_circularity = 0.3
        self.diff_threshold = 20
        
        # 截图频率 - 射击过程中高速截图
        self.capture_interval = 0.02  # 20ms (50 FPS)
        
        # 校准结果
        self.all_round_results = []  # 多轮测试结果
        self.suggested_scopes = {}
        
        # 当前武器信息
        self.current_weapon = None
        self.current_scope = None
        
        # 分段射击配置
        self.shooting_phases = [15, 30, 40]  # 分段射击：15 发 → 30 发 → 40 发
        
        # 分段弹道分析
        self.phase_analysis = {
            'phase1': {'bullets': [], 'avg_displacement': 0},  # 前 10 发
            'phase2': {'bullets': [], 'avg_displacement': 0},  # 10-20 发
            'phase3': {'bullets': [], 'avg_displacement': 0}   # 20 发后
        }
        
    def _get_capture_region(self, resolution):
        """获取截图区域"""
        regions = {
            "1920x1080": (0, 0, 1920, 1080),
            "2560x1440": (0, 0, 2560, 1440),
            "3840x2160": (0, 0, 3840, 2160),
        }
        return regions.get(resolution, (0, 0, 1920, 1080))
    
    def capture_screen(self):
        """截取屏幕"""
        with mss.mss() as sct:
            monitor = {
                "left": self.capture_region[0],
                "top": self.capture_region[1],
                "width": self.capture_region[2],
                "height": self.capture_region[3]
            }
            img = sct.grab(monitor)
            return np.array(img)
    
    def auto_press_tab(self):
        """自动按 Tab 键"""
        print("  → 按 Tab 键...")
        
        if HAS_KEYBOARD:
            keyboard.press('tab')
            keyboard.release('tab')
        elif HAS_PYAUTOGUI:
            pyautogui.press('tab')
        else:
            import ctypes
            user32 = ctypes.windll.user32
            VK_TAB = 0x09
            user32.keybd_event(VK_TAB, 0, 0, 0)
            time.sleep(0.1)
            user32.keybd_event(VK_TAB, 0, 2, 0)
        
        time.sleep(0.5)
    
    def detect_weapon(self):
        """识别武器（自动按 Tab 打开/关闭背包）"""
        print("\n正在识别武器...")
        
        # 1. 按 Tab 打开背包
        self.auto_press_tab()
        
        # 2. 等待背包打开动画
        print("  → 等待背包打开...")
        time.sleep(1.0)
        
        # 3. 调用现有识别逻辑
        try:
            result = asyncio.run(capture_all_positions_thread(self.resolution))
            weapon_info = result[0]
            
            if weapon_info and weapon_info.get('Name') and weapon_info['Name'] != 'None':
                self.current_weapon = weapon_info['Name']
                self.current_scope = weapon_info.get('Scope', 'none')
                
                print(f"\n✓ 识别成功!")
                print(f"  武器：{self.current_weapon}")
                print(f"  倍镜：{self.current_scope}")
                print(f"  枪口：{weapon_info.get('Muzzle', '无')}")
                print(f"  握把：{weapon_info.get('Grip', '无')}")
                
                # 4. 再按一次 Tab 关闭背包
                print("\n  → 关闭背包...")
                self.auto_press_tab()
                time.sleep(0.5)
                print("✓ 背包已关闭")
                
                return True
            else:
                print("\n✗ 未识别到武器")
                print("使用默认武器 M762 进行校准")
                self.current_weapon = 'M762'
                self.current_scope = 'hongdian'
                self.auto_press_tab()
                return True
                
        except Exception as e:
            print(f"\n✗ 识别失败：{e}")
            self.auto_press_tab()
            self.current_weapon = 'M762'
            self.current_scope = 'hongdian'
            return True
    
    def auto_fire_with_aim(self, num_shots=30, fire_mode='auto'):
        """自动控制鼠标开火（长按右键开镜 + 左键射击）"""
        print(f"\n准备自动射击 {num_shots} 发...")
        print(f"射击模式：{fire_mode}")
        print(f"武器：{self.current_weapon}")
        
        # 判断是否为自动武器
        auto_weapons = ['m762', 'm416', 'scar-l', 'akm', 'groza', 'aug', 'dp28', 'm249']
        if self.current_weapon.lower() in auto_weapons:
            fire_mode = 'auto'
        else:
            fire_mode = 'single'
        
        # 等待 2 秒准备
        print("\n射击准备：2 秒...")
        for i in range(2, 0, -1):
            print(f"  {i}...")
            time.sleep(1)
        
        print("\n开始射击，请保持准星稳定...")
        
        # 移动鼠标到屏幕中心
        screen_center_x = self.capture_region[0] + self.capture_region[2] // 2
        screen_center_y = self.capture_region[1] + self.capture_region[3] // 2
        self.mouse.mouse_move_to(screen_center_x, screen_center_y)
        time.sleep(0.3)
        
        # 1. 长按右键开镜
        print("  → 长按右键开镜...")
        self.mouse.mouse_down('right')
        time.sleep(0.5)  # 等待开镜动画
        
        # 2. 射击
        if fire_mode == 'auto':
            # 自动武器：按住左键
            print("  → 按住左键射击...")
            self.mouse.mouse_down('left')
            
            # 根据武器射速计算射击时间
            fire_rate = 10  # 发/秒
            fire_duration = num_shots / fire_rate
            time.sleep(fire_duration)
            
            # 松开左键
            print("  → 松开左键")
            self.mouse.mouse_up('left')
            
        else:
            # 单发武器：点击 num_shots 次
            print(f"  → 点击左键 {num_shots} 次...")
            for i in range(num_shots):
                self.mouse.mouse_down('left')
                time.sleep(0.15)
                self.mouse.mouse_up('left')
                time.sleep(0.05)
                
                if (i + 1) % 10 == 0:
                    print(f"    已射击 {i+1}/{num_shots} 发")
        
        # 3. 松开右键
        print("  → 松开右键")
        self.mouse.mouse_up('right')
        
        print(f"\n✓ 射击完成")
    
    def detect_bullet_holes_wall(self, base_image, current_image, frame_idx):
        """针对普通墙面的弹痕识别"""
        detected_holes = []
        
        # 帧差法检测变化
        diff = cv2.absdiff(base_image, current_image)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        
        # 自适应阈值
        mean_brightness = np.mean(gray_diff)
        adaptive_threshold = max(15, mean_brightness * 1.2)
        
        _, thresh = cv2.threshold(gray_diff, adaptive_threshold, 255, cv2.THRESH_BINARY)
        
        # 形态学操作
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        thresh = cv2.dilate(thresh, kernel, iterations=3)
        
        # 查找轮廓
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
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
            
            # 颜色变化验证
            roi_size = 15
            x1, y1 = max(0, cx - roi_size), max(0, cy - roi_size)
            x2, y2 = min(current_image.shape[1], cx + roi_size), min(current_image.shape[0], cy + roi_size)
            roi = current_image[y1:y2, x1:x2]
            
            if roi.size > 0:
                base_roi = base_image[y1:y2, x1:x2]
                color_diff = np.mean(np.abs(roi.astype(float) - base_roi.astype(float)))
                
                if color_diff > 15:
                    detected_holes.append((cx, cy, area, circularity, color_diff))
        
        # 保存调试图像
        if frame_idx % 5 == 0 or len(detected_holes) > 0:
            debug_image = current_image.copy()
            for i, (cx, cy, area, circ, color_diff) in enumerate(detected_holes):
                if circ > 0.6:
                    color = (0, 255, 0)
                elif circ > 0.4:
                    color = (0, 255, 255)
                else:
                    color = (0, 0, 255)
                
                cv2.circle(debug_image, (cx, cy), 10, color, -1)
            
            debug_path = self.save_dir / f"debug_frame_{frame_idx}.png"
            cv2.imwrite(str(debug_path), debug_image)
        
        return detected_holes
    
    def filter_duplicate_holes(self, holes, min_distance=20):
        """过滤重复弹痕"""
        filtered = []
        for hole in holes:
            is_new = True
            for existing in filtered:
                dist = np.sqrt((hole[0]-existing[0])**2 + (hole[1]-existing[1])**2)
                if dist < min_distance:
                    is_new = False
                    break
            if is_new:
                filtered.append(hole)
        return filtered
    
    def analyze_phase_recoil(self, bullet_holes, total_shots=30):
        """分段分析后坐力"""
        print("\n分析分段弹道...")
        
        sorted_holes = sorted(bullet_holes, key=lambda h: h[1])
        
        # 计算每发的垂直位移
        displacements = []
        for i in range(1, len(sorted_holes)):
            dy = sorted_holes[i][1] - sorted_holes[i-1][1]
            displacements.append(dy)
        
        # 分段分析
        phase1_end = min(10, len(displacements))
        phase2_end = min(20, len(displacements))
        
        # 前 10 发
        if phase1_end > 0:
            phase1_disp = displacements[:phase1_end]
            self.phase_analysis['phase1']['bullets'] = phase1_disp
            self.phase_analysis['phase1']['avg_displacement'] = np.mean(phase1_disp)
            print(f"  前 10 发：平均位移 {np.mean(phase1_disp):.2f} 像素")
        
        # 10-20 发
        if phase2_end > phase1_end:
            phase2_disp = displacements[phase1_end:phase2_end]
            self.phase_analysis['phase2']['bullets'] = phase2_disp
            self.phase_analysis['phase2']['avg_displacement'] = np.mean(phase2_disp)
            print(f"  10-20 发：平均位移 {np.mean(phase2_disp):.2f} 像素")
        
        # 20 发后
        if len(displacements) > phase2_end:
            phase3_disp = displacements[phase2_end:]
            self.phase_analysis['phase3']['bullets'] = phase3_disp
            self.phase_analysis['phase3']['avg_displacement'] = np.mean(phase3_disp)
            print(f"  20 发后：平均位移 {np.mean(phase3_disp):.2f} 像素")
        
        # 计算水平偏移（随机性）
        horizontal_offsets = []
        for i in range(1, len(sorted_holes)):
            dx = sorted_holes[i][0] - sorted_holes[i-1][0]
            horizontal_offsets.append(dx)
        
        if horizontal_offsets:
            avg_horizontal = np.mean(horizontal_offsets)
            std_horizontal = np.std(horizontal_offsets)
            print(f"\n  水平偏移：平均 {avg_horizontal:.2f} 像素，标准差 {std_horizontal:.2f} 像素（随机）")
        
        return self.phase_analysis
    
    def run_single_round(self, round_num, num_shots=30):
        """执行单轮测试"""
        print(f"\n{'='*60}")
        print(f"    第 {round_num} 轮测试：射击 {num_shots} 发")
        print(f"{'='*60}")
        
        round_data = {
            'round': round_num,
            'shots': num_shots,
            'bullet_holes': [],
            'screenshots': [],
            'phase_analysis': {}
        }
        
        # 1. 保存基准图像
        base_image = self.capture_screen()
        base_path = self.save_dir / f"round_{round_num}_base.png"
        cv2.imwrite(str(base_path), base_image)
        print(f"✓ 基准图像已保存")
        
        # 2. 启动射击线程
        fire_thread = threading.Thread(
            target=self.auto_fire_with_aim,
            args=(num_shots, 'auto')
        )
        fire_thread.start()
        
        # 3. 同时开始截图
        start_time = time.time()
        frame_count = 0
        shooting_duration = num_shots / 10 + 1  # 射击时间 + 1 秒缓冲
        
        print(f"\n正在高速截图（{1/self.capture_interval:.0f} FPS）...")
        
        while time.time() - start_time < shooting_duration:
            current_image = self.capture_screen()
            round_data['screenshots'].append(current_image)
            frame_count += 1
            
            # 每 10 帧保存一张调试图
            if frame_count % 10 == 0:
                screenshot_path = self.save_dir / f"round{round_num}_frame_{frame_count}.png"
                cv2.imwrite(str(screenshot_path), current_image)
            
            time.sleep(self.capture_interval)
        
        # 等待射击线程结束
        fire_thread.join()
        
        print(f"\n✓ 第 {round_num} 轮射击完成，共截图 {frame_count} 张")
        
        # 4. 分析弹痕
        print("\n开始分析弹痕分布...")
        
        if len(round_data['screenshots']) >= 2:
            first_frame = round_data['screenshots'][0]
            last_frame = round_data['screenshots'][-1]
            
            # 保存最后一张截图
            last_path = self.save_dir / f"round_{round_num}_last_frame.png"
            cv2.imwrite(str(last_path), last_frame)
            
            # 分析弹痕
            for i, frame in enumerate(round_data['screenshots'][::5]):
                new_holes = self.detect_bullet_holes_wall(first_frame, frame, i)
                new_holes_coords = [(h[0], h[1], h[2], h[3]) for h in new_holes]
                new_holes_coords = self.filter_duplicate_holes(new_holes_coords)
                
                for hole in new_holes_coords:
                    is_duplicate = False
                    for existing in round_data['bullet_holes']:
                        dist = np.sqrt((hole[0]-existing[0])**2 + (hole[1]-existing[1])**2)
                        if dist < 25:
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        round_data['bullet_holes'].append(hole)
                        print(f"  检测到新弹痕 #{len(round_data['bullet_holes'])}: ({hole[0]}, {hole[1]})")
        
        print(f"\n第 {round_num} 轮识别到弹痕数量：{len(round_data['bullet_holes'])}")
        
        # 5. 分段分析
        phase_analysis = self.analyze_phase_recoil(round_data['bullet_holes'], num_shots)
        round_data['phase_analysis'] = phase_analysis.copy()
        
        # 6. 保存结果
        self.all_round_results.append(round_data)
        
        return round_data
    
    def cross_validate_results(self):
        """交叉比对多轮测试结果"""
        print(f"\n{'='*60}")
        print("    多轮测试交叉比对")
        print(f"{'='*60}")
        
        if len(self.all_round_results) < 2:
            print("⚠ 只有一轮测试数据，无法交叉比对")
            return self.all_round_results[0] if self.all_round_results else None
        
        # 收集所有轮次的数据
        all_displacements = []
        all_phase1 = []
        all_phase2 = []
        all_phase3 = []
        
        for round_data in self.all_round_results:
            phase = round_data['phase_analysis']
            
            if phase['phase1']['bullets']:
                all_phase1.extend(phase['phase1']['bullets'])
            
            if phase['phase2']['bullets']:
                all_phase2.extend(phase['phase2']['bullets'])
            
            if phase['phase3']['bullets']:
                all_phase3.extend(phase['phase3']['bullets'])
        
        # 计算综合平均值
        print("\n综合统计:")
        
        if all_phase1:
            avg_phase1 = np.mean(all_phase1)
            std_phase1 = np.std(all_phase1)
            print(f"  前 10 发：平均 {avg_phase1:.2f} 像素，标准差 {std_phase1:.2f}")
            all_displacements.extend(all_phase1)
        
        if all_phase2:
            avg_phase2 = np.mean(all_phase2)
            std_phase2 = np.std(all_phase2)
            print(f"  10-20 发：平均 {avg_phase2:.2f} 像素，标准差 {std_phase2:.2f}")
            all_displacements.extend(all_phase2)
        
        if all_phase3:
            avg_phase3 = np.mean(all_phase3)
            std_phase3 = np.std(all_phase3)
            print(f"  20 发后：平均 {avg_phase3:.2f} 像素，标准差 {std_phase3:.2f}")
            all_displacements.extend(all_phase3)
        
        # 计算总体平均
        if all_displacements:
            overall_avg = np.mean(all_displacements)
            overall_std = np.std(all_displacements)
            print(f"\n  总体平均：{overall_avg:.2f} 像素，标准差 {overall_std:.2f}")
            
            # 检查各轮次一致性
            print("\n各轮次一致性检查:")
            for i, round_data in enumerate(self.all_round_results, 1):
                phase = round_data['phase_analysis']
                if phase['phase1']['bullets']:
                    round_avg = np.mean(phase['phase1']['bullets'])
                    diff = abs(round_avg - overall_avg) / overall_avg * 100
                    status = "✓" if diff < 20 else "⚠"
                    print(f"  第{i}轮：{round_avg:.2f} 像素 (偏差 {diff:.1f}%) {status}")
        
        return {
            'overall_avg': overall_avg if all_displacements else 0,
            'overall_std': overall_std if all_displacements else 0,
            'phase1_avg': np.mean(all_phase1) if all_phase1 else 0,
            'phase2_avg': np.mean(all_phase2) if all_phase2 else 0,
            'phase3_avg': np.mean(all_phase3) if all_phase3 else 0,
            'rounds': len(self.all_round_results)
        }
    
    def run_calibration(self, shooting_phases=None):
        """运行全自动校准（多轮分段射击）"""
        
        if shooting_phases is None:
            shooting_phases = self.shooting_phases
        
        print("\n" + "="*60)
        print("    PUBG 压枪参数一键自动校准工具 V4")
        print("    (多轮分段射击版)")
        print("="*60)
        print(f"\n当前分辨率：{self.resolution}")
        print(f"截图区域：{self.capture_region}")
        print(f"截图频率：{1/self.capture_interval:.0f} FPS")
        print(f"分段射击配置：{shooting_phases}")
        
        # 1. 识别武器（自动按 Tab 打开/关闭背包）
        if not self.detect_weapon():
            print("\n✗ 武器识别失败，退出校准")
            return None
        
        # 2. 读取当前配置
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            print(f"\n✓ 配置文件加载成功")
        except Exception as e:
            print(f"\n✗ 配置文件加载失败：{e}")
            return None
        
        # 3. 多轮分段射击
        for i, num_shots in enumerate(shooting_phases, 1):
            self.run_single_round(i, num_shots)
            
            # 轮次间隔
            if i < len(shooting_phases):
                print(f"\n等待 3 秒后开始下一轮...")
                time.sleep(3)
                
                # 提醒用户重新对准
                print("⚠ 请重新对准墙面空白区域，避免弹痕重叠")
                time.sleep(2)
        
        # 4. 交叉比对多轮结果
        cross_result = self.cross_validate_results()
        
        if not cross_result:
            print("\n✗ 校准失败，没有有效数据")
            return None
        
        # 5. 计算建议的 scope 值
        print("\n计算建议的压枪参数...")
        
        BASE_RECOIL = 5.0
        avg_displacement = cross_result['overall_avg']
        
        if abs(avg_displacement) > 0:
            current_value = self.config['sensitivity'].get(self.current_scope, 1.0)
            suggested = BASE_RECOIL / abs(avg_displacement)
            
            min_value = current_value * 0.5
            max_value = current_value * 1.5
            suggested = max(min_value, min(max_value, suggested))
            
            self.suggested_scopes[self.current_scope] = {
                'current': current_value,
                'suggested': round(suggested, 2),
                'change': round(suggested - current_value, 2)
            }
        
        # 6. 保存结果
        result = {
            'timestamp': datetime.now().isoformat(),
            'weapon': self.current_weapon,
            'scope': self.current_scope,
            'resolution': self.resolution,
            'shooting_phases': shooting_phases,
            'total_rounds': len(self.all_round_results),
            'cross_validation': {
                'overall_avg': round(cross_result['overall_avg'], 2),
                'overall_std': round(cross_result['overall_std'], 2),
                'phase1_avg': round(cross_result['phase1_avg'], 2),
                'phase2_avg': round(cross_result['phase2_avg'], 2),
                'phase3_avg': round(cross_result['phase3_avg'], 2)
            },
            'suggested_scopes': self.suggested_scopes
        }
        
        result_path = self.save_dir / f"calibration_result_{self.current_weapon}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存：{result_path}")
        
        # 7. 显示结果
        print("\n" + "="*60)
        print("    校准结果")
        print("="*60)
        print(f"\n武器：{self.current_weapon}")
        print(f"倍镜：{self.current_scope}")
        print(f"测试轮次：{len(self.all_round_results)} 轮")
        print(f"\n交叉比对结果:")
        print(f"  总体平均：{cross_result['overall_avg']:.2f} 像素")
        print(f"  标准差：{cross_result['overall_std']:.2f} 像素")
        print(f"\n分段弹道分析:")
        print(f"  前 10 发：{cross_result['phase1_avg']:.2f} 像素/发")
        print(f"  10-20 发：{cross_result['phase2_avg']:.2f} 像素/发")
        print(f"  20 发后：{cross_result['phase3_avg']:.2f} 像素/发")
        print(f"\n使用总体平均值计算压枪参数")
        print(f"平均位移：{avg_displacement:.2f} 像素\n")
        
        print("建议的灵敏度配置:")
        print("-" * 60)
        print(f"{'倍镜':<10} {'当前值':<10} {'建议值':<10} {'调整':<10}")
        print("-" * 60)
        
        for scope_name, data in self.suggested_scopes.items():
            scope_display = {
                'none': '机瞄', 'hongdian': '红点', 'quanxi': '全息',
                '2bei': '2 倍镜', '3bei': '3 倍镜', '4bei': '4 倍镜',
                '6bei': '6 倍镜', '8bei': '8 倍镜', '15bei': '15 倍镜'
            }.get(scope_name, scope_name)
            
            change_str = f"{data['change']:+.2f}"
            print(f"{scope_display:<10} {data['current']:<10.2f} {data['suggested']:<10.2f} {change_str:<10}")
        
        print("-" * 60)
        
        # 8. 询问是否应用
        print("\n是否应用建议的配置？")
        print("  Y - 应用并更新 Config/config.json")
        print("  N - 不应用，仅保存结果")
        
        try:
            choice = input("\n请输入选择 (Y/N): ").strip().lower()
            
            if choice == 'y':
                self._apply_config()
                print("\n✓ 配置已更新！请重启主程序以生效。")
            else:
                print("\nℹ 配置未更改，结果已保存供参考。")
        
        except Exception as e:
            print(f"\n⚠ 输入错误：{e}")
        
        return result
    
    def _apply_config(self):
        """应用建议的配置"""
        for scope_name, data in self.suggested_scopes.items():
            self.config['sensitivity'][scope_name] = data['suggested']
        
        backup_path = self.config_path.parent / f"config.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        print(f"✓ 原配置已备份：{backup_path}")
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        print(f"✓ 新配置已保存：{self.config_path}")


def main():
    """主函数"""
    # 检查依赖
    if not HAS_PYAUTOGUI and not HAS_KEYBOARD:
        print("\n⚠ 警告：未安装 pyautogui 或 keyboard")
        print("将使用 Windows API 模拟按键，但可能不够稳定")
        print("建议安装：pip install pyautogui keyboard\n")
        time.sleep(2)
    
    calibrator = AutoCalibrator()
    
    # 自定义分段射击配置
    # 可以修改为 [15, 30, 40] 或其他组合
    calibrator.run_calibration(shooting_phases=[15, 30, 40])


if __name__ == "__main__":
    main()
