#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 压枪校准工具 - 准星追踪 & 录像分析版

方案1：实时准星追踪 —— 边打边看结果
方案2：录像离线分析 —— 打完再看结果
两种方案交叉对比，互相验证

依赖：mss, opencv-python, numpy, keyboard
"""

import cv2
import numpy as np
import mss
import time
import json
import sys
import os
from pathlib import Path
from datetime import datetime

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

# 屏幕中心 ROI 区域（开镜后准星在中心，跟踪周围画面特征）
# 4K 分辨率下截取准星周围 400x400 的区域
ROI_SIZES = {
    "3840x2160": (1720, 880, 400, 400),   # x, y, w, h
    "2560x1440": (1080, 520, 400, 400),
    "1920x1080": (760, 340, 400, 400),
}


class RecoilLogger:
    """日志记录器——所有分析结果实时写文件，你随时能看"""
    
    def __init__(self, save_dir):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = self.save_dir / f"calibrate_{self.timestamp}.log"
    
    def log(self, msg):
        line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}"
        print(line)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    
    def save_image(self, name, img):
        """保存分析截图"""
        path = self.save_dir / f"{self.timestamp}_{name}.png"
        cv2.imwrite(str(path), img)
        self.log(f"  图片已保存: {path.name}")
        return path
    
    def save_trajectory(self, name, data):
        """保存弹道数据"""
        path = self.save_dir / f"{self.timestamp}_{name}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.log(f"  数据已保存: {path.name}")


class RecoilAnalyzer:
    """压枪校准分析器"""
    
    def __init__(self, resolution="3840x2160"):
        self.resolution = resolution
        self.roi = ROI_SIZES.get(resolution, ROI_SIZES["1920x1080"])
        self.logger = None
        self.frames = []
        self.fps = 60
        self.config_path = Path("./Config/config.json")
        self.gun_data_dir = Path("./_internal/GunData")
    
    def capture_frame(self):
        """截取屏幕 ROI"""
        x, y, w, h = self.roi
        with mss.mss() as sct:
            monitor = {"left": x, "top": y, "width": w, "height": h}
            img = sct.grab(monitor)
        return np.array(img)
    
    def record_to_ram(self, duration=3.0):
        """固定时长录制——按 1 后开始，录完自动停"""
        self.logger.log(f"\n{'='*50}")
        self.logger.log(f"开始录制：{duration} 秒，FPS={self.fps}")
        self.logger.log(f"现在开镜 + 开火，打完停手")
        self.logger.log(f"{'='*50}")
        
        self.frames = []
        interval = 1.0 / self.fps
        start = time.time()
        
        while time.time() - start < duration:
            frame = self.capture_frame()
            self.frames.append(frame)
            # 简单节流
            elapsed = time.time() - start
            target_frames = int(elapsed * self.fps)
            if len(self.frames) > target_frames + 1:
                time.sleep(0.001)
        
        self.logger.log(f"录制完成：共 {len(self.frames)} 帧，实际 {time.time()-start:.2f} 秒")
        return self.frames
    
    def detect_shots(self, frames):
        """
        通过枪口闪光检测实际射出子弹数
        原理：开火瞬间画面整体亮度会突增
        """
        if len(frames) < 3:
            return []
        
        # 计算每帧亮度
        brightness = []
        for i, frame in enumerate(frames):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            avg_brightness = np.mean(gray)
            brightness.append(avg_brightness)
        
        brightness = np.array(brightness)
        
        # 计算帧间亮度变化
        diff = np.diff(brightness)
        
        # 找亮度突增的帧（开火瞬间）
        threshold = np.std(diff) * 2.0
        if threshold < 5:
            threshold = 5  # 最小阈值
        
        shot_frames = []
        for i in range(1, len(diff)):
            if diff[i] > threshold:
                # 检查是否已经记录过（100ms 内只算一次）
                min_gap = max(3, self.fps // 20)  # 至少间隔 50ms
                if not shot_frames or (i - shot_frames[-1]) > min_gap:
                    shot_frames.append(i)
        
        return shot_frames
    
    def track_recoil_optical_flow(self, frames, shot_frames):
        """
        用 Lucas-Kanade 光流法追踪准星位移
        原理：跟踪墙面上的特征点相对于第一帧的移动量
        """
        if len(frames) < 2:
            return np.zeros(len(frames))
        
        first_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        
        # 找特征点
        feature_params = dict(
            maxCorners=200,
            qualityLevel=0.01,
            minDistance=7,
            blockSize=7
        )
        p0 = cv2.goodFeaturesToTrack(first_gray, mask=None, **feature_params)
        
        if p0 is None or len(p0) < 10:
            self.logger.log("⚠ 特征点太少，降低阈值重试...")
            feature_params['qualityLevel'] = 0.005
            p0 = cv2.goodFeaturesToTrack(first_gray, mask=None, **feature_params)
        
        if p0 is None or len(p0) < 5:
            self.logger.log("✗ 无法找到足够特征点，可能画面太暗")
            return np.zeros(len(frames))
        
        # Lucas-Kanade 光流参数
        lk_params = dict(
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)
        )
        
        # 追踪
        old_gray = first_gray.copy()
        p0_copy = p0.copy()
        y_offsets = np.zeros(len(frames))
        
        for i in range(1, len(frames)):
            frame_gray = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            
            p1, st, err = cv2.calcOpticalFlowPyrLK(
                old_gray, frame_gray, p0_copy, None, **lk_params
            )
            
            if p1 is not None:
                good_old = p0_copy[st == 1]
                good_new = p1[st == 1]
                
                if len(good_old) > 3 and len(good_new) > 3:
                    # 平均 Y 偏移
                    y_offset = np.mean(good_new[:, 1] - good_old[:, 1])
                    y_offsets[i] = y_offset
                
                # 更新特征点
                p0_copy = good_new.reshape(-1, 1, 2)
            
            old_gray = frame_gray.copy()
            
            # 如果特征点太少，重新找
            if len(p0_copy) < 10:
                p0_new = cv2.goodFeaturesToTrack(old_gray, mask=None, **feature_params)
                if p0_new is not None:
                    p0_copy = np.vstack([p0_copy, p0_new])
        
        # 平滑处理（3 帧滑动平均）
        kernel = np.ones(3) / 3
        y_offsets = np.convolve(y_offsets, kernel, mode='same')
        
        return y_offsets
    
    def extract_per_shot_displacement(self, y_offsets, shot_frames):
        """
        从每发子弹的位移曲线中提取：
        - 每两发子弹之间的实际间距
        - 每发子弹的绝对位移
        """
        if not shot_frames or len(shot_frames) < 2:
            return {'shots': len(shot_frames), 'displacements': [], 'cumulative': []}
        
        displacements = []
        cumulative = []
        
        for i in range(1, len(shot_frames)):
            # 这颗子弹射出瞬间的 Y 偏移
            y_at_shot = y_offsets[shot_frames[i]]
            # 上一颗子弹射出瞬间的 Y 偏移
            y_at_prev = y_offsets[shot_frames[i-1]]
            
            # 实际间距
            dy = y_at_shot - y_at_prev
            displacements.append(dy)
            cumulative.append(y_at_shot)
        
        return {
            'shots': len(shot_frames),
            'displacements': [round(float(d), 2) for d in displacements],
            'cumulative': [round(float(c), 2) for c in cumulative]
        }
    
    def load_gun_data(self, gun_name, scope_name):
        """加载现有弹道 JSON"""
        if gun_name.lower() == 'none' or gun_name is None:
            self.logger.log("⚠ 未指定枪械名称")
            return None
        
        gun_path = self.gun_data_dir / f"{gun_name.lower()}.json"
        if not gun_path.exists():
            self.logger.log(f"⚠ 找不到 {gun_path}")
            return None
        
        with open(gun_path, 'r', encoding='utf-8') as f:
            gun_data = json.load(f)
        
        # 获取当前配件码（简化：先用无配件数据）
        # 完整实现需要从识别结果构建配件码
        key = "A0B0C0"  # 默认无枪口无握把无枪托
        ballistic = gun_data.get(key, [])
        
        # 获取倍镜数据
        scope_data = None
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            sensitivity = config.get('sensitivity', {})
            scope_value = sensitivity.get(scope_name.lower(), 1.0)
            scope_data = {'name': scope_name, 'value': scope_value}
        except:
            scope_data = {'name': scope_name, 'value': 1.0}
        
        return {
            'ballistic': ballistic,
            'scope': scope_data,
            'posture': gun_data.get('none', 1)
        }
    
    def generate_report(self, actual_data, json_data, mode_name):
        """生成分析报告"""
        self.logger.log(f"\n{'='*60}")
        self.logger.log(f"  {mode_name} 分析结果")
        self.logger.log(f"{'='*60}")
        
        if actual_data['shots'] < 2:
            self.logger.log("✗ 弹数太少，无法分析")
            return None
        
        displacements = actual_data['displacements']
        
        self.logger.log(f"\n实际射出：{actual_data['shots']} 发")
        self.logger.log(f"每发间距（像素）: {displacements[:20]}")
        
        cumulative = actual_data['cumulative']
        self.logger.log(f"累计位移（像素）: {cumulative[:20]}")
        
        # 平均间距
        avg_disp = np.mean(np.abs(displacements[:10]))  # 前 10 发最准
        self.logger.log(f"\n前 10 发平均间距：{avg_disp:.2f} 像素")
        
        # 与 JSON 对比
        if json_data and json_data['ballistic']:
            json_ballistic = json_data['ballistic']
            # JSON 中每 3 个值为一组：[下移Y, 停, 下移Y, ...]，实际有效值每隔 2 个取一个
            json_actual = [json_ballistic[i] for i in range(0, min(len(json_ballistic), len(displacements)*2), 2) if json_ballistic[i] != 0]
            
            # 但 JSON 格式实际是 [Y1, 0, Y2, 0, ...] 模式
            # 取非零值
            json_nonzero = [v for v in json_ballistic[:len(displacements)*2] if v != 0]
            
            if json_nonzero:
                json_avg = np.mean(json_nonzero[:10])
                self.logger.log(f"JSON 理论平均（前10发）: {json_avg:.2f}")
                self.logger.log(f"实际平均（前10发）: {avg_disp:.2f}")
                
                if abs(json_avg) > 0:
                    ratio = avg_disp / abs(json_avg)
                    self.logger.log(f"实际/理论 比例: {ratio:.3f}")
                    
                    if abs(ratio - 1.0) > 0.15:
                        current_scope = json_data['scope']['value']
                        suggested_scope = round(current_scope * ratio, 2)
                        self.logger.log(f"\n当前倍镜系数: {current_scope}")
                        self.logger.log(f"建议倍镜系数: {suggested_scope} (调整 {abs(suggested_scope-current_scope):.2f})")
                        
                        return {
                            'mode': mode_name,
                            'shots': actual_data['shots'],
                            'avg_displacement': round(float(avg_disp), 2),
                            'json_avg': round(float(json_avg), 2),
                            'ratio': round(float(ratio), 3),
                            'current_scope': current_scope,
                            'suggested_scope': suggested_scope
                        }
        
        return None
    
    def generate_trajectory_image(self, frames, y_offsets, shot_frames, mode_name):
        """生成弹道曲线图"""
        if len(frames) < 2:
            return
        
        height = 600
        width = 1200
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # 背景
        img[:] = (30, 30, 30)
        
        # Y 偏移曲线
        max_offset = max(abs(np.max(y_offsets)), 10)
        scale = (height // 2 - 50) / max_offset
        mid_y = height // 2
        
        for i in range(1, len(y_offsets)):
            y1 = int(mid_y - y_offsets[i-1] * scale)
            y2 = int(mid_y - y_offsets[i] * scale)
            x1 = int((i-1) / (len(y_offsets)-1) * (width - 100)) + 50
            x2 = int(i / (len(y_offsets)-1) * (width - 100)) + 50
            
            cv2.line(img, (x1, y1), (x2, y2), (0, 255, 255), 2)
        
        # 中线
        cv2.line(img, (0, mid_y), (width, mid_y), (100, 100, 100), 1)
        
        # 开火标记
        for sf in shot_frames:
            if sf < len(y_offsets):
                x = int(sf / (len(y_offsets)-1) * (width - 100)) + 50
                cv2.line(img, (x, 30), (x, height-30), (0, 0, 255), 1)
        
        # 标题
        cv2.putText(img, f"{mode_name} - Recoil Trajectory", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        self.logger.save_image(f"trajectory_{mode_name}", img)
    
    def generate_frame_overlay(self, frame, y_offsets, shot_frames, current_frame_idx):
        """在单帧上叠加分析信息"""
        overlay = frame.copy()
        h, w = overlay.shape[:2]
        
        # 画十字准线
        cv2.line(overlay, (w//2, 0), (w//2, h), (0, 0, 255), 1)
        cv2.line(overlay, (0, h//2), (w, h//2), (0, 0, 255), 1)
        
        # 当前偏移
        offset = y_offsets[current_frame_idx] if current_frame_idx < len(y_offsets) else 0
        cv2.putText(overlay, f"Y Offset: {offset:.1f}px", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(overlay, f"Frame: {current_frame_idx}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(overlay, f"Shots: {len(shot_frames)}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        return overlay
    
    def run_realtime(self):
        """
        方案1：实时准星追踪
        用户按 1 开始 → 开火 → 按 2 停止
        """
        self.logger = RecoilLogger("./calibration_results")
        self.logger.log("\n" + "="*60)
        self.logger.log("  方案1：实时准星追踪")
        self.logger.log("  1. 按 1 开始录制")
        self.logger.log("  2. 开镜 + 开火（10-15 发）")
        self.logger.log("  3. 按 2 停止录制")
        self.logger.log("  4. 自动分析")
        self.logger.log("="*60)
        
        # 等用户按 1
        self.logger.log("\n等待按 1 开始...")
        if HAS_KEYBOARD:
            keyboard.wait('1')
        else:
            input("按回车开始...")
        
        # 录制
        frames = self.record_to_ram(duration=5.0)  # 默认 5 秒
        
        # 等用户按 2
        self.logger.log("\n录制中... 按 2 停止")
        if HAS_KEYBOARD:
            keyboard.wait('2')
        
        self.logger.log("停止录制，开始分析...")
        
        return self.analyze(frames, "Mode1_Realtime")
    
    def run_offline(self):
        """
        方案2：录像离线分析
        录制固定时长（比如 5 秒），录完立即分析
        """
        self.logger = RecoilLogger("./calibration_results")
        self.logger.log("\n" + "="*60)
        self.logger.log("  方案2：录像离线分析")
        self.logger.log("  1. 按 1 开始录制")
        self.logger.log("  2. 开镜 + 开火（建议 10-15 发）")
        self.logger.log("  3. 录制自动停止，开始分析")
        self.logger.log("="*60)
        
        # 等用户按 1
        self.logger.log("\n等待按 1 开始...")
        if HAS_KEYBOARD:
            keyboard.wait('1')
        else:
            input("按回车开始...")
        
        # 固定时长录制
        frames = self.record_to_ram(duration=5.0)
        
        return self.analyze(frames, "Mode2_Offline")
    
    def analyze(self, frames, mode_name):
        """核心分析流程——两种方案共用"""
        if len(frames) < 10:
            self.logger.log("✗ 录制帧数太少")
            return None
        
        self.logger.log(f"\n开始分析 {len(frames)} 帧...")
        
        # 1. 检测实际射出子弹数
        shot_frames = self.detect_shots(frames)
        self.logger.log(f"\n检测到开火事件：{len(shot_frames)} 次")
        for i, sf in enumerate(shot_frames):
            self.logger.log(f"  第 {i+1} 发：第 {sf} 帧")
        
        # 2. 光流追踪准星位移
        self.logger.log("\n追踪准星位移（光流法）...")
        y_offsets = self.track_recoil_optical_flow(frames, shot_frames)
        
        # 3. 生成弹道曲线图
        self.generate_trajectory_image(frames, y_offsets, shot_frames, mode_name)
        
        # 4. 保存关键帧
        # 保存第一帧（基线）
        self.logger.save_image(f"{mode_name}_frame0", frames[0])
        # 保存最后一帧
        self.logger.save_image(f"{mode_name}_frame_last", frames[-1])
        
        # 如果有开火事件，保存闪光帧
        for i, sf in enumerate(shot_frames[:5]):
            if sf < len(frames):
                overlay = self.generate_frame_overlay(frames[sf], y_offsets, shot_frames, sf)
                self.logger.save_image(f"{mode_name}_shot{i+1}", overlay)
        
        # 5. 提取每发子弹的间距
        actual_data = self.extract_per_shot_displacement(y_offsets, shot_frames)
        
        # 保存原始数据
        self.logger.save_trajectory(f"{mode_name}_data", {
            'mode': mode_name,
            'resolution': self.resolution,
            'total_frames': len(frames),
            'shot_frames': shot_frames,
            'y_offsets': [round(float(y), 2) for y in y_offsets.tolist()],
            'actual_data': actual_data
        })
        
        # 6. 加载 JSON 弹道做对比
        # 默认用 M762 的无配件+红点数据
        # 实际应该从识别结果获取
        json_data = self.load_gun_data('m762', 'hongdian')
        
        # 7. 生成报告
        report = self.generate_report(actual_data, json_data, mode_name)
        
        return report


def cross_compare(report1, report2):
    """交叉对比两种方案的结果"""
    if not report1 or not report2:
        print("\n✗ 至少有一种方案没有结果，无法交叉对比")
        return
    
    print(f"\n{'='*60}")
    print("  交叉对比结果")
    print(f"{'='*60}")
    
    print(f"\n{'指标':<20} {'方案1':<15} {'方案2':<15} {'差异'}")
    print(f"{'-'*60}")
    
    for key in ['shots', 'avg_displacement', 'ratio', 'suggested_scope']:
        v1 = report1.get(key, 'N/A')
        v2 = report2.get(key, 'N/A')
        
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            diff = abs(v1 - v2)
            if isinstance(v1, float):
                diff_str = f"{diff:.3f}" if diff < 1 else f"{diff:.1f}"
            else:
                diff_str = str(diff)
        else:
            diff_str = str(v1 != v2)
        
        print(f"{key:<20} {str(v1):<15} {str(v2):<15} {diff_str}")
    
    # 一致性判断
    r1 = report1.get('ratio', 1.0)
    r2 = report2.get('ratio', 1.0)
    ratio_diff = abs(r1 - r2)
    
    if ratio_diff < 0.05:
        print(f"\n✅ 两种方案高度一致（差异 {ratio_diff:.1%}）")
        suggested = (report1['suggested_scope'] + report2['suggested_scope']) / 2
        print(f"   综合建议倍镜系数: {suggested:.2f}")
    elif ratio_diff < 0.15:
        print(f"\n⚠ 两种方案基本一致（差异 {ratio_diff:.1%}）")
        suggested = (report1['suggested_scope'] + report2['suggested_scope']) / 2
        print(f"   综合建议倍镜系数: {suggested:.2f}")
    else:
        print(f"\n❌ 两种方案差异较大（差异 {ratio_diff:.1%}）")
        print(f"   建议重新测试或检查录制质量")


def main():
    print("""
    PUBG 压枪校准工具 - 双方案交叉对比
    ═══════════════════════════════════
    
    选项:
      1 - 方案1：实时准星追踪（边打边看）
      2 - 方案2：录像离线分析（打完再看）
      3 - 双方案都跑，交叉对比结果
    """)
    
    choice = input("选择模式 (1/2/3): ").strip()
    
    analyzer = RecoilAnalyzer(resolution="3840x2160")
    
    if choice == '1':
        report1 = analyzer.run_realtime()
        if report1:
            print(f"\n最终建议: 倍镜系数调整为 {report1['suggested_scope']}")
    
    elif choice == '2':
        report2 = analyzer.run_offline()
        if report2:
            print(f"\n最终建议: 倍镜系数调整为 {report2['suggested_scope']}")
    
    elif choice == '3':
        print("\n" + "="*60)
        print("  方案1：实时准星追踪")
        print("="*60)
        analyzer.logger = RecoilLogger("./calibration_results")
        analyzer.fps = 60
        
        analyzer.logger.log("\n按 1 开始方案1录制...")
        if HAS_KEYBOARD:
            keyboard.wait('1')
        
        frames1 = analyzer.record_to_ram(duration=5.0)
        
        if HAS_KEYBOARD:
            keyboard.wait('2')
        
        report1 = analyzer.analyze(frames1, "Mode1_Realtime")
        
        # 等用户准备下一轮
        print(f"\n方案1完成。准备方案2...")
        print("换一处墙面空白位置，重新开镜")
        
        if HAS_KEYBOARD:
            print("准备好后按 1 开始方案2...")
            keyboard.wait('1')
        else:
            input("按回车开始方案2...")
        
        print("\n" + "="*60)
        print("  方案2：录像离线分析")
        print("="*60)
        
        frames2 = analyzer.record_to_ram(duration=5.0)
        
        report2 = analyzer.analyze(frames2, "Mode2_Offline")
        
        # 交叉对比
        if report1 and report2:
            cross_compare(report1, report2)
    
    else:
        print("无效的选项")


if __name__ == "__main__":
    main()
