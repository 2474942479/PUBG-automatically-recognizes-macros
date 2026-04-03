#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 压枪参数一键自动校准工具
refactor 分支专用版本 - 普通墙面版
支持多种鼠标驱动：GHUB / pyopdll / pynput

使用方法：
1. 打开 PUBG，进入训练场
2. 拿起任意武器，装上倍镜
3. 对准一面普通墙壁（不需要靶墙）
4. 运行此脚本
5. 按 Tab 键打开背包（自动识别武器）
6. 关闭背包，脚本会自动开火射击 30 发
7. 脚本自动分析、更新配置

注意：此脚本需要 Windows 系统
依赖：mss, opencv-python, numpy, pillow
鼠标驱动：GHUB 或 pyopdll 或 pynput（三选一）
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

# 尝试导入多种鼠标驱动
class MouseController:
    """通用鼠标控制器（支持多种驱动）"""
    
    def __init__(self):
        self.driver_name = None
        self.driver = None
        self._init_driver()
    
    def _init_driver(self):
        """尝试初始化多种驱动"""
        
        # 尝试 1: GHUB
        try:
            from GHUB import ghub_device
            self.driver = ghub_device()
            if self.driver.gm_ok:
                self.driver_name = 'GHUB'
                print(f"\n✓ 鼠标驱动：罗技 GHUB")
                return
        except Exception as e:
            pass
        
        # 尝试 2: pyopdll
        try:
            from pyopdll import OP
            self.driver = OP()
            self.driver_name = 'pyopdll'
            print(f"\n✓ 鼠标驱动：pyopdll")
            return
        except Exception as e:
            pass
        
        # 尝试 3: pynput（备用）
        try:
            from pynput.mouse import Controller as MouseController
            self.driver = MouseController()
            self.driver_name = 'pynput'
            print(f"\n✓ 鼠标驱动：pynput（功能受限）")
            return
        except Exception as e:
            pass
        
        # 都失败
        self.driver_name = None
        print(f"\n✗ 未找到可用的鼠标驱动")
        print("请安装以下驱动之一：")
        print("  1. 罗技 GHUB: https://www.logitechg.com/zh-cn/innovation/g-hub.html")
        print("  2. pyopdll: pip install pyopdll")
        print("  3. pynput: pip install pynput")
    
    def mouse_move_to(self, x, y):
        """移动鼠标到指定位置"""
        if self.driver_name == 'GHUB':
            self.driver.mouse_To(int(x), int(y))
        elif self.driver_name == 'pyopdll':
            # pyopdll API: MoveTo(x, y)
            self.driver.MoveTo(int(x), int(y))
        elif self.driver_name == 'pynput':
            from pynput.mouse import Button
            # pynput 只能相对移动，无法绝对定位
            print("⚠ pynput 不支持绝对定位，跳过鼠标移动")
    
    def mouse_down(self, button=1):
        """按下鼠标按钮"""
        if self.driver_name == 'GHUB':
            self.driver.mouse_down(int(button))
        elif self.driver_name == 'pyopdll':
            # pyopdll API: 使用 keyboard 模拟鼠标点击
            # pyopdll 主要用于键盘，鼠标需要其他方式
            # 尝试使用 ctypes 调用 Windows API
            import ctypes
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
        elif self.driver_name == 'pynput':
            from pynput.mouse import Button
            self.driver.press(Button.left)
    
    def mouse_up(self, button=1):
        """释放鼠标按钮"""
        if self.driver_name == 'GHUB':
            self.driver.mouse_up(int(button))
        elif self.driver_name == 'pyopdll':
            # pyopdll API: 使用 ctypes 调用 Windows API
            import ctypes
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
        elif self.driver_name == 'pynput':
            from pynput.mouse import Button
            self.driver.release(Button.left)
    
    def is_available(self):
        """检查驱动是否可用"""
        return self.driver_name is not None


class AutoCalibrator:
    """一键自动校准器（普通墙面版）"""
    
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
        
        # 弹痕识别参数（针对普通墙面优化）
        self.min_area = 30       # 最小弹痕面积（墙面破损通常比弹孔大）
        self.max_area = 1000     # 最大弹痕面积
        self.min_circularity = 0.3  # 圆形度要求降低（墙面破损不规则）
        self.diff_threshold = 20    # 帧差阈值降低
        
        # 截图频率（根据射击速度调整）
        self.capture_interval = 0.03  # 30ms 一帧（约 33 FPS）
        
        # 校准结果
        self.bullet_holes = []
        self.vertical_displacements = []
        self.suggested_scopes = {}
        
        # 当前武器信息
        self.current_weapon = None
        self.current_scope = None
        
    def _get_capture_region(self, resolution):
        """
        获取截图区域
        建议：让用户手动调整为准星周围的区域
        """
        # 默认全屏，用户可以根据需要修改
        # 格式：(left, top, width, height)
        regions = {
            "1920x1080": (0, 0, 1920, 1080),
            "2560x1440": (0, 0, 2560, 1440),
            "3840x2160": (0, 0, 3840, 2160),
        }
        
        # 如果用户想只截取准星周围区域，可以修改这里
        # 例如只截取屏幕中央 800x600 区域：
        # return (resolution_width//2 - 400, resolution_height//2 - 300, 800, 600)
        
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
    
    def detect_weapon(self):
        """使用现有 recognition.py 识别武器"""
        print("\n正在识别武器...")
        print("提示：请按 Tab 键打开背包")
        
        time.sleep(2)
        
        try:
            result = asyncio.run(capture_all_positions_thread(self.resolution))
            weapon_info = result[0]
            
            if weapon_info and weapon_info.get('Name') and weapon_info['Name'] != 'None':
                self.current_weapon = weapon_info['Name']
                self.current_scope = weapon_info.get('Scope', 'none')
                
                print(f"\n✓ 识别成功!")
                print(f"  武器：{self.current_weapon}")
                print(f"  倍镜：{self.current_scope}")
                
                return True
            else:
                print("\n✗ 未识别到武器")
                print("使用默认武器 M762 进行校准")
                self.current_weapon = 'M762'
                self.current_scope = 'hongdian'
                return True
                
        except Exception as e:
            print(f"\n✗ 识别失败：{e}")
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
            self.mouse.mouse_down(1)  # 1=左键
            
            # 根据武器射速计算射击时间
            # M762 约 10 发/秒，M416 约 12 发/秒
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
                time.sleep(0.15)  # 单发间隔
                self.mouse.mouse_up(1)
                time.sleep(0.05)
                
                if (i + 1) % 10 == 0:
                    print(f"    已射击 {i+1}/{num_shots} 发")
        
        print(f"\n✓ 射击完成")
    
    def detect_bullet_holes_wall(self, base_image, current_image, frame_idx):
        """
        针对普通墙面的弹痕识别
        
        普通墙面特点：
        - 没有明显的黑色弹孔
        - 弹痕是墙面破损/灰尘
        - 颜色变化较小
        - 形状不规则
        """
        detected_holes = []
        
        # ========== 方法 1: 帧差法检测变化 ==========
        diff = cv2.absdiff(base_image, current_image)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        
        # 自适应阈值（根据图像亮度调整）
        mean_brightness = np.mean(gray_diff)
        # 墙面变化较小，降低阈值
        adaptive_threshold = max(15, mean_brightness * 1.2)
        
        _, thresh = cv2.threshold(gray_diff, adaptive_threshold, 255, cv2.THRESH_BINARY)
        
        # 形态学操作（扩大检测区域）
        kernel = np.ones((5, 5), np.uint8)  # 更大的核
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        thresh = cv2.dilate(thresh, kernel, iterations=3)  # 更多膨胀
        
        # 查找轮廓
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            
            # 面积过滤（墙面破损通常比弹孔大）
            if not (self.min_area < area < self.max_area):
                continue
            
            # 圆形度检测（降低要求，墙面破损不规则）
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue
            
            circularity = 4 * np.pi * (area / (perimeter * perimeter))
            if circularity < self.min_circularity:
                continue
            
            # 获取中心点
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            
            # ========== 方法 2: 颜色变化验证 ==========
            # 墙面弹痕通常是浅色破损或深色灰尘
            roi_size = 15  # 更大的 ROI
            x1, y1 = max(0, cx - roi_size), max(0, cy - roi_size)
            x2, y2 = min(current_image.shape[1], cx + roi_size), min(current_image.shape[0], cy + roi_size)
            roi = current_image[y1:y2, x1:x2]
            
            if roi.size > 0:
                # 计算与基准图像的色差
                base_roi = base_image[y1:y2, x1:x2]
                color_diff = np.mean(np.abs(roi.astype(float) - base_roi.astype(float)))
                
                # 色差验证（墙面变化较小）
                if color_diff > 15:  # 有明显变化
                    detected_holes.append((cx, cy, area, circularity, color_diff))
        
        # ========== 保存调试图像 ==========
        if frame_idx % 5 == 0 or len(detected_holes) > 0:
            debug_image = current_image.copy()
            
            # 绘制检测到的弹痕
            for i, (cx, cy, area, circ, color_diff) in enumerate(detected_holes):
                # 根据圆形度着色
                if circ > 0.6:
                    color = (0, 255, 0)  # 绿色：高圆形度
                elif circ > 0.4:
                    color = (0, 255, 255)  # 黄色：中等圆形度
                else:
                    color = (0, 0, 255)  # 红色：低圆形度（可能误检）
                
                cv2.circle(debug_image, (cx, cy), 10, color, -1)
                cv2.putText(debug_image, f"#{i+1}", (cx-15, cy-15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
            
            # 保存调试图
            debug_path = self.save_dir / f"debug_frame_{frame_idx}.png"
            cv2.imwrite(str(debug_path), debug_image)
            
            # 保存阈值处理后的图像
            thresh_path = self.save_dir / f"thresh_frame_{frame_idx}.png"
            cv2.imwrite(str(thresh_path), thresh)
        
        return detected_holes
    
    def filter_duplicate_holes(self, holes, min_distance=20):
        """
        过滤重复弹痕（同一位置多次检测）
        墙面弹痕可能连续多帧都被检测到
        """
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
        print("    (普通墙面版)")
        print("="*60)
        print(f"\n当前分辨率：{self.resolution}")
        print(f"截图区域：{self.capture_region}")
        print(f"截图频率：{1/self.capture_interval:.0f} FPS")
        print(f"弹痕识别：普通墙面模式")
        
        # 1. 识别武器
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
        
        # 3. 射击前截图（基准图像）
        print("\n准备截图区域...")
        print("提示：请确保准星对准墙面，墙面上没有弹痕")
        time.sleep(2)
        
        # 4. 自动射击
        self.auto_fire(num_shots=num_shots)
        
        # 5. 等待 0.5 秒开始捕获（让烟雾散去）
        print("\n等待 0.5 秒后开始捕获弹痕...")
        time.sleep(0.5)
        
        # 6. 开始捕获
        print("\n开始捕获弹痕...")
        print(f"提示：截图间隔 {self.capture_interval*1000:.0f}ms，射击速度快的武器可能需要更短间隔")
        
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
            
            # 检测新弹痕
            new_holes = self.detect_bullet_holes_wall(base_image, current_image, frame_count)
            
            # 提取坐标（去掉 color_diff）
            new_holes_coords = [(h[0], h[1], h[2], h[3]) for h in new_holes]
            new_holes_coords = self.filter_duplicate_holes(new_holes_coords)
            
            for hole in new_holes_coords:
                is_duplicate = False
                for existing in self.bullet_holes:
                    dist = np.sqrt((hole[0]-existing[0])**2 + (hole[1]-existing[1])**2)
                    if dist < 25:  # 墙面弹痕判断更宽松
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    self.bullet_holes.append(hole)
                    print(f"  [帧{frame_count}] 检测到新弹痕 #{len(self.bullet_holes)}: ({hole[0]}, {hole[1]}), 面积={hole[2]:.0f}")
            
            # 如果检测到足够弹痕，提前结束
            if len(self.bullet_holes) >= num_shots * 0.8:
                print(f"\n✓ 已检测到足够的弹痕 ({len(self.bullet_holes)}/{num_shots})")
                break
            
            # 更新基准图像（墙面检测需要持续更新）
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
            print("  4. 减少截图间隔（当前 30ms）")
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
        print(f"  最大位移：{np.max(self.vertical_displacements):.2f} 像素")
        print(f"  最小位移：{np.min(self.vertical_displacements):.2f} 像素")
        
        # 8. 计算建议的 scope 值
        print("\n计算建议的压枪参数...")
        
        BASE_RECOIL = 5.0
        
        if abs(avg_displacement) > 0:
            current_value = self.config['sensitivity'].get(self.current_scope, 1.0)
            suggested = BASE_RECOIL / abs(avg_displacement)
            
            # 限制调整幅度
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
        
        # 备份原配置
        backup_path = self.config_path.parent / f"config.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        print(f"✓ 原配置已备份：{backup_path}")
        
        # 写入新配置
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
        print(f"✓ 新配置已保存：{self.config_path}")


def main():
    """主函数"""
    calibrator = AutoCalibrator()
    calibrator.run_calibration(num_shots=30)


if __name__ == "__main__":
    main()
