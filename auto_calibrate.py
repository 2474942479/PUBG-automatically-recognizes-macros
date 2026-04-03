#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 压枪参数一键自动校准工具
refactor 分支专用版本 - 完全自动化版

功能：
1. 自动按 Tab 打开背包
2. 自动识别武器和配件
3. 自动关闭背包
4. 自动开枪射击 30 发
5. 自动分析弹痕
6. 自动更新配置

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
from pathlib import Path
from datetime import datetime

# 导入现有模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recognition import capture_all_positions_thread
from Process import ProcessClass

# 尝试导入键盘鼠标控制
try:
    import pyautogui
    pyautogui.FAILSAFE = False  # 禁用故障保护
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
    """通用鼠标控制器（支持多种驱动）"""
    
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
    
    def mouse_down(self, button=1):
        """按下鼠标按钮"""
        if self.driver_name == 'pyopdll':
            import ctypes
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
        elif self.driver_name == 'GHUB':
            self.driver.mouse_down(int(button))
        elif self.driver_name == 'pyautogui':
            pyautogui.mouseDown(button='left')
    
    def mouse_up(self, button=1):
        """释放鼠标按钮"""
        if self.driver_name == 'pyopdll':
            import ctypes
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
        elif self.driver_name == 'GHUB':
            self.driver.mouse_up(int(button))
        elif self.driver_name == 'pyautogui':
            pyautogui.mouseUp(button='left')
    
    def is_available(self):
        """检查驱动是否可用"""
        return self.driver_name is not None


class AutoCalibrator:
    """一键自动校准器（完全自动化版）"""
    
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
        
        # 截图区域（默认全屏，用户可以调整）
        self.resolution = self.PC.Monitor
        self.capture_region = self._get_capture_region(self.resolution)
        
        # 弹痕识别参数
        self.min_area = 30
        self.max_area = 1000
        self.min_circularity = 0.3
        self.diff_threshold = 20
        
        # 截图频率
        self.capture_interval = 0.03  # 30ms
        
        # 校准结果
        self.bullet_holes = []
        self.vertical_displacements = []
        self.suggested_scopes = {}
        
        # 当前武器信息
        self.current_weapon = None
        self.current_scope = None
        
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
        """
        自动按 Tab 键打开背包
        """
        print("\n正在打开背包...")
        
        if HAS_KEYBOARD:
            # 使用 keyboard 库
            keyboard.press('tab')
            keyboard.release('tab')
            print("✓ 已按 Tab 键（keyboard 库）")
        elif HAS_PYAUTOGUI:
            # 使用 pyautogui
            pyautogui.press('tab')
            print("✓ 已按 Tab 键（pyautogui）")
        else:
            # 使用 ctypes 模拟按键
            import ctypes
            user32 = ctypes.windll.user32
            VK_TAB = 0x09
            user32.keybd_event(VK_TAB, 0, 0, 0)  # 按下
            time.sleep(0.1)
            user32.keybd_event(VK_TAB, 0, 2, 0)  # 释放
            print("✓ 已按 Tab 键（Windows API）")
        
        # 等待背包打开
        time.sleep(1.5)
    
    def auto_close_bag(self):
        """
        自动按 Tab 键关闭背包
        """
        print("\n关闭背包...")
        
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
        print("✓ 背包已关闭")
    
    def detect_weapon(self):
        """
        使用现有 recognition.py 识别武器
        """
        print("\n正在识别武器...")
        
        # 1. 自动按 Tab 打开背包
        self.auto_press_tab()
        
        # 2. 调用现有识别逻辑
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
                
                # 3. 自动关闭背包
                self.auto_close_bag()
                
                return True
            else:
                print("\n✗ 未识别到武器")
                print("使用默认武器 M762 进行校准")
                self.current_weapon = 'M762'
                self.current_scope = 'hongdian'
                self.auto_close_bag()
                return True
                
        except Exception as e:
            print(f"\n✗ 识别失败：{e}")
            self.auto_close_bag()
            self.current_weapon = 'M762'
            self.current_scope = 'hongdian'
            return True
    
    def auto_fire(self, num_shots=30, fire_mode='auto'):
        """
        自动控制鼠标开火
        
        参数:
            num_shots: 射击次数
            fire_mode: 'auto' 或 'single'
        """
        print(f"\n准备自动射击 {num_shots} 发...")
        print(f"射击模式：{fire_mode}")
        print(f"武器：{self.current_weapon}")
        
        # 判断是否为自动武器
        auto_weapons = ['m762', 'm416', 'scar-l', 'akm', 'groza', 'aug', 'dp28', 'm249']
        if self.current_weapon.lower() in auto_weapons:
            fire_mode = 'auto'
        else:
            fire_mode = 'single'
        
        # 等待 3 秒准备
        print("\n射击准备：3 秒...")
        for i in range(3, 0, -1):
            print(f"  {i}...")
            time.sleep(1)
        
        print("\n开始射击，请保持准星稳定...")
        
        # 移动鼠标到屏幕中心（确保游戏窗口激活）
        screen_center_x = self.capture_region[0] + self.capture_region[2] // 2
        screen_center_y = self.capture_region[1] + self.capture_region[3] // 2
        self.mouse.mouse_move_to(screen_center_x, screen_center_y)
        time.sleep(0.5)
        
        if fire_mode == 'auto':
            # 自动武器：按住左键
            print("  → 按住左键...")
            self.mouse.mouse_down(1)
            
            # 根据武器射速计算射击时间
            fire_rate = 10  # 发/秒
            fire_duration = num_shots / fire_rate
            time.sleep(fire_duration)
            
            # 松开左键
            print("  → 松开左键")
            self.mouse.mouse_up(1)
            
        else:
            # 单发武器：点击 num_shots 次
            print(f"  → 点击左键 {num_shots} 次...")
            for i in range(num_shots):
                self.mouse.mouse_down(1)
                time.sleep(0.15)
                self.mouse.mouse_up(1)
                time.sleep(0.05)
                
                if (i + 1) % 10 == 0:
                    print(f"    已射击 {i+1}/{num_shots} 发")
        
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
    
    def run_calibration(self, num_shots=30):
        """运行全自动校准"""
        print("\n" + "="*60)
        print("    PUBG 压枪参数一键自动校准工具")
        print("    (完全自动化版)")
        print("="*60)
        print(f"\n当前分辨率：{self.resolution}")
        print(f"截图区域：{self.capture_region}")
        print(f"截图频率：{1/self.capture_interval:.0f} FPS")
        
        # 1. 识别武器（自动按 Tab）
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
        
        # 3. 射击前准备
        print("\n准备截图区域...")
        print("提示：请确保准星对准墙面，墙面上没有弹痕")
        time.sleep(2)
        
        # 4. 自动射击
        self.auto_fire(num_shots=num_shots)
        
        # 5. 等待 0.5 秒开始捕获
        print("\n等待 0.5 秒后开始捕获弹痕...")
        time.sleep(0.5)
        
        # 6. 开始捕获
        print("\n开始捕获弹痕...")
        
        self.bullet_holes = []
        base_image = self.capture_screen()
        
        # 保存基准图像
        base_path = self.save_dir / "base_image.png"
        cv2.imwrite(str(base_path), base_image)
        print(f"✓ 基准图像已保存：{base_path}")
        
        start_time = time.time()
        frame_count = 0
        
        # 捕获循环（持续 10 秒）
        while time.time() - start_time < 10:
            current_image = self.capture_screen()
            frame_count += 1
            
            new_holes = self.detect_bullet_holes_wall(base_image, current_image, frame_count)
            new_holes_coords = [(h[0], h[1], h[2], h[3]) for h in new_holes]
            new_holes_coords = self.filter_duplicate_holes(new_holes_coords)
            
            for hole in new_holes_coords:
                is_duplicate = False
                for existing in self.bullet_holes:
                    dist = np.sqrt((hole[0]-existing[0])**2 + (hole[1]-existing[1])**2)
                    if dist < 25:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    self.bullet_holes.append(hole)
                    print(f"  [帧{frame_count}] 检测到新弹痕 #{len(self.bullet_holes)}: ({hole[0]}, {hole[1]})")
            
            if len(self.bullet_holes) >= num_shots * 0.8:
                print(f"\n✓ 已检测到足够的弹痕 ({len(self.bullet_holes)}/{num_shots})")
                break
            
            base_image = current_image
            time.sleep(self.capture_interval)
        
        elapsed_time = time.time() - start_time
        print(f"\n捕获完成：{frame_count} 帧，{elapsed_time:.1f} 秒")
        print(f"识别到弹痕数量：{len(self.bullet_holes)}")
        
        # 7. 分析弹痕分布
        if len(self.bullet_holes) < 5:
            print("\n✗ 识别到的弹痕太少，校准失败")
            print("建议:")
            print("  1. 选择颜色单一的墙面（灰色/白色最佳）")
            print("  2. 调整截图区域，只包含准星周围")
            print("  3. 增加射击次数")
            return None
        
        print("\n分析弹痕分布...")
        sorted_holes = sorted(self.bullet_holes, key=lambda h: h[1])
        
        self.vertical_displacements = []
        for i in range(1, len(sorted_holes)):
            dy = sorted_holes[i][1] - sorted_holes[i-1][1]
            self.vertical_displacements.append(dy)
        
        avg_displacement = np.mean(self.vertical_displacements)
        std_displacement = np.std(self.vertical_displacements)
        
        print(f"\n弹痕统计:")
        print(f"  平均垂直位移：{avg_displacement:.2f} 像素")
        print(f"  标准差：{std_displacement:.2f} 像素")
        
        # 8. 计算建议的 scope 值
        print("\n计算建议的压枪参数...")
        
        BASE_RECOIL = 5.0
        
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
        
        # 9. 保存结果
        result = {
            'timestamp': datetime.now().isoformat(),
            'weapon': self.current_weapon,
            'scope': self.current_scope,
            'resolution': self.resolution,
            'bullet_count': len(self.bullet_holes),
            'avg_displacement': round(avg_displacement, 2),
            'std_displacement': round(std_displacement, 2),
            'suggested_scopes': self.suggested_scopes
        }
        
        result_path = self.save_dir / f"calibration_result_{self.current_weapon}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存：{result_path}")
        
        # 10. 显示结果
        print("\n" + "="*60)
        print("    校准结果")
        print("="*60)
        print(f"\n武器：{self.current_weapon}")
        print(f"倍镜：{self.current_scope}")
        print(f"识别弹痕：{len(self.bullet_holes)} 个")
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
        
        # 11. 询问是否应用
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
    calibrator.run_calibration(num_shots=30)


if __name__ == "__main__":
    main()
