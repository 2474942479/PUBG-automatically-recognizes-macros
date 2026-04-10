#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 视频校准模块 (v2 — 透明化重构)
═══════════════════════════════════════
录屏 → 自动检测弹孔 → 标注预览图 → 加载到画布手动审核 → 计算参数

核心改进 (vs v1):
  1. 录屏自动保存为 .avi，可回放
  2. 检测结果生成标注图 (编号 + 轨迹线)
  3. 加载到 BulletCanvas 供手动调整
  4. initial 模式: 帧差分保留时序
  5. refine 模式: 最后一帧静态检测 (BulletDetector)，不再用帧差分
"""

import cv2
import json
import logging
import mss
import numpy as np
import os
import threading
import time
from pathlib import Path
from datetime import datetime

log = logging.getLogger("video_calibrator")

try:
    from calibration.bullet_analysis import (
        _GUN_META, _get_fire_interval, _find_gun_data_dir, BulletDetector,
    )
except ImportError:
    try:
        from bullet_analysis import (
            _GUN_META, _get_fire_interval, _find_gun_data_dir, BulletDetector,
        )
    except ImportError:
        _GUN_META = {}
        BulletDetector = None
        def _get_fire_interval(n): return None
        def _find_gun_data_dir(): return "./_internal/GunData"


# ═══════════════════════════════════════════
# 录屏器
# ═══════════════════════════════════════════

class ScreenRecorder:
    """高速屏幕捕获，支持 F6/F7 热键控制 + 视频保存。"""

    def __init__(self, capture_region=None, target_fps=60):
        self.capture_region = capture_region
        self.target_fps = target_fps
        self.frames = []
        self._recording = False
        self._thread = None
        self._hotkey_listener = None
        self.actual_region = None

    @property
    def recording(self):
        return self._recording

    @property
    def frame_count(self):
        return len(self.frames)

    def _auto_region(self):
        with mss.mss() as sct:
            mon = sct.monitors[1]
            w, h = mon["width"], mon["height"]
            cw, ch = int(w * 0.5), int(h * 0.65)
            return {
                "left": mon["left"] + (w - cw) // 2,
                "top": mon["top"] + int(h * 0.1),
                "width": cw, "height": ch,
            }

    def start(self):
        if self._recording:
            return
        self._recording = True
        self.frames = []
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("录制开始 (目标 %d fps)", self.target_fps)

    def stop(self):
        if not self._recording:
            return 0
        self._recording = False
        if self._thread:
            self._thread.join(timeout=5)
        n = len(self.frames)
        if n > 1:
            dur = self.frames[-1][0] - self.frames[0][0]
            log.info("录制结束: %d 帧, %.1fs, %.1f fps", n, dur, n / max(0.001, dur))
        return n

    def _loop(self):
        interval = 1.0 / self.target_fps
        if self.capture_region:
            region = {
                "left": self.capture_region[0], "top": self.capture_region[1],
                "width": self.capture_region[2], "height": self.capture_region[3],
            }
        else:
            region = self._auto_region()
        self.actual_region = region

        with mss.mss() as sct:
            while self._recording:
                t0 = time.perf_counter()
                raw = sct.grab(region)
                frame = np.array(raw)[:, :, :3].copy()
                self.frames.append((time.time(), frame))
                sleep_t = interval - (time.perf_counter() - t0)
                if sleep_t > 0:
                    time.sleep(sleep_t)

    def get_reference_frame(self):
        return self.frames[0][1].copy() if self.frames else None

    def get_last_frame(self):
        return self.frames[-1][1].copy() if self.frames else None

    def save_video(self, path=None):
        """将录制帧保存为 .avi 视频文件，返回保存路径。"""
        if len(self.frames) < 2:
            return None

        if path is None:
            out_dir = Path("calibration_results")
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(out_dir / f"recording_{ts}.avi")

        h, w = self.frames[0][1].shape[:2]
        dur = self.frames[-1][0] - self.frames[0][0]
        fps = len(self.frames) / max(0.01, dur)

        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
        for _, frame in self.frames:
            writer.write(frame)
        writer.release()
        log.info("视频已保存: %s (%d帧, %.1ffps)", path, len(self.frames), fps)
        return path

    # ── 热键 ──

    def start_hotkey_listener(self, start_key="f6", stop_key="f7",
                              on_start=None, on_stop=None):
        from pynput import keyboard as kb
        from pynput.keyboard import Key

        _map = {f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)}
        sk = _map.get(start_key.lower(), Key.f6)
        ek = _map.get(stop_key.lower(), Key.f7)

        def _on_press(key):
            try:
                if key == sk and not self._recording:
                    self.start()
                    if on_start:
                        threading.Thread(target=on_start, daemon=True).start()
                elif key == ek and self._recording:
                    self.stop()
                    if on_stop:
                        threading.Thread(target=on_stop, daemon=True).start()
            except Exception as e:
                log.error("热键错误: %s", e)

        self._hotkey_listener = kb.Listener(on_press=_on_press)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()
        log.info("热键: %s=开始录制, %s=停止录制", start_key.upper(), stop_key.upper())

    def stop_hotkey_listener(self):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None


# ═══════════════════════════════════════════
# 帧分析器 (仅用于 initial 模式的时序检测)
# ═══════════════════════════════════════════

class FrameAnalyzer:
    """逐帧差分 + 图像稳定 + 增量弹孔检测。

    适用于 initial 模式 (弹孔分散, 时序有价值)。
    不适用于 refine 模式 (弹孔重叠, 帧差分无法区分)。
    """

    def __init__(self, diff_threshold=25, stabilize=True,
                 min_area_ratio=5e-6, max_area_ratio=8e-4):
        self.diff_threshold = diff_threshold
        self.stabilize = stabilize
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio
        self.debug_frames = []

    def analyze(self, frames, fire_interval_ms=85.7, progress_cb=None):
        """分析录制帧序列，返回按时间排序的弹孔列表。

        Returns:
            [{"x": int, "y": int, "timestamp": float, "shot_num": int,
              "frame_idx": int}, ...]
        """
        if len(frames) < 5:
            return []

        self.debug_frames = []
        ref_t, ref_bgr = frames[0]
        ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
        h, w = ref_gray.shape
        pixels = h * w
        min_a = max(4, int(pixels * self.min_area_ratio))
        max_a = int(pixels * self.max_area_ratio)
        nms_r = max(8, int(min(h, w) * 0.01))

        ref_kp, ref_des = None, None
        orb = None
        if self.stabilize:
            orb = cv2.ORB_create(nfeatures=1500)
            ref_kp, ref_des = orb.detectAndCompute(ref_gray, None)

        detected = []
        known = set()

        sample_step = max(1, int(fire_interval_ms / 2 / 16.7))

        for idx in range(sample_step, len(frames), sample_step):
            if progress_cb and idx % (sample_step * 5) == 0:
                progress_cb(idx / len(frames))

            cur_t, cur_bgr = frames[idx]
            cur_gray = cv2.cvtColor(cur_bgr, cv2.COLOR_BGR2GRAY)

            aligned = cur_gray
            if self.stabilize and ref_des is not None and orb is not None:
                aligned = self._align(cur_gray, ref_gray, ref_kp, ref_des, orb)

            diff = cv2.absdiff(ref_gray, aligned)
            _, bw = cv2.threshold(diff, self.diff_threshold, 255, cv2.THRESH_BINARY)
            kern = np.ones((3, 3), np.uint8)
            bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kern, iterations=1)
            bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kern, iterations=2)

            contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)

            new_in_frame = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if not (min_a <= area <= max_a):
                    continue
                M = cv2.moments(cnt)
                if M["m00"] <= 0:
                    continue
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])

                gk = (cx // nms_r, cy // nms_r)
                is_new = all(
                    (gk[0] + dx, gk[1] + dy) not in known
                    for dx in range(-1, 2) for dy in range(-1, 2)
                )
                if is_new:
                    hole = {"x": cx, "y": cy, "timestamp": cur_t, "frame_idx": idx}
                    detected.append(hole)
                    known.add(gk)
                    new_in_frame.append(hole)

            if new_in_frame:
                self.debug_frames.append({
                    "frame_idx": idx,
                    "timestamp": cur_t,
                    "diff_image": diff.copy(),
                    "binary_image": bw.copy(),
                    "new_holes": list(new_in_frame),
                })

        detected.sort(key=lambda h: h["timestamp"])
        for i, hole in enumerate(detected):
            hole["shot_num"] = i + 1

        if progress_cb:
            progress_cb(1.0)
        log.info("帧差分检测到 %d 个弹孔 (分析了 %d 关键帧)", len(detected), len(self.debug_frames))
        return detected

    @staticmethod
    def _align(frame_gray, ref_gray, ref_kp, ref_des, orb):
        try:
            kp2, des2 = orb.detectAndCompute(frame_gray, None)
            if des2 is None or len(des2) < 6:
                return frame_gray
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = sorted(bf.match(ref_des, des2), key=lambda m: m.distance)
            good = matches[:min(80, len(matches))]
            if len(good) < 4:
                return frame_gray
            pts1 = np.float32([ref_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            pts2 = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, _ = cv2.findHomography(pts2, pts1, cv2.RANSAC, 5.0)
            if H is None:
                return frame_gray
            return cv2.warpPerspective(frame_gray, H,
                                       (ref_gray.shape[1], ref_gray.shape[0]))
        except Exception:
            return frame_gray


# ═══════════════════════════════════════════
# 标注工具
# ═══════════════════════════════════════════

def annotate_frame(frame_bgr, holes, title=""):
    """在帧图像上绘制弹孔标注 (编号 + 轨迹线 + 颜色分段)，返回标注后的副本。"""
    canvas = frame_bgr.copy()
    h, w = canvas.shape[:2]
    n = len(holes)
    if n == 0:
        return canvas

    sorted_h = sorted(holes, key=lambda x: x.get("shot_num", 0))
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.35, min(h, w) / 2000)
    thickness = max(1, int(min(h, w) / 800))
    radius = max(4, int(min(h, w) / 300))

    for i in range(len(sorted_h) - 1):
        a, b = sorted_h[i], sorted_h[i + 1]
        cv2.line(canvas, (a["x"], a["y"]), (b["x"], b["y"]),
                 (180, 180, 60), thickness, cv2.LINE_AA)

    for hole in sorted_h:
        sn = hole.get("shot_num", 0)
        frac = (sn - 1) / max(1, n - 1)
        if frac < 0.33:
            color = (0, 0, 255)
        elif frac < 0.66:
            color = (0, 165, 255)
        else:
            color = (0, 200, 0)

        cv2.circle(canvas, (hole["x"], hole["y"]), radius, color, thickness + 1,
                   cv2.LINE_AA)
        cv2.circle(canvas, (hole["x"], hole["y"]), max(2, radius // 3),
                   color, -1, cv2.LINE_AA)

        label = str(sn)
        (tw, th_), _ = cv2.getTextSize(label, font, font_scale, thickness)
        lx = hole["x"] + radius + 3
        ly = hole["y"] - radius
        cv2.putText(canvas, label, (lx, ly), font, font_scale,
                    (255, 255, 255), thickness + 1, cv2.LINE_AA)
        cv2.putText(canvas, label, (lx, ly), font, font_scale,
                    color, thickness, cv2.LINE_AA)

    info_lines = [
        f"Holes: {n}",
        f"Red=early  Orange=mid  Green=late",
    ]
    if title:
        info_lines.insert(0, title)
    for i, line in enumerate(info_lines):
        y_pos = 25 + i * int(22 * max(1, font_scale / 0.4))
        cv2.putText(canvas, line, (10, y_pos), font, font_scale * 0.8,
                    (200, 200, 200), thickness, cv2.LINE_AA)

    return canvas


# ═══════════════════════════════════════════
# 主控制器
# ═══════════════════════════════════════════

class VideoCalibrator:
    """视频校准主控器 (v2 — 透明化)

    典型工作流::

        vc = VideoCalibrator("m416", "A0B0C0")
        vc.enable_hotkeys()

        # 用户按 F6 → 射击 → F7
        video_path = vc.save_recording()       # 保存录屏
        frame, holes = vc.detect_holes("initial")  # 检测弹孔
        annotated = vc.get_annotated_frame(holes)   # 生成标注图

        # → 加载到 BulletCanvas 供手动审核调整
        # → 用户确认后用 BulletParamGenerator / IterativeCorrector 计算
    """

    def __init__(self, gun_name, acc_code="A0B0C0",
                 scope_val=1.0, posture_val=1.0,
                 capture_region=None, gun_data_dir=None):
        self.gun_name = gun_name
        self.acc_code = acc_code
        self.scope_val = scope_val
        self.posture_val = posture_val
        self.gun_data_dir = Path(gun_data_dir or _find_gun_data_dir())

        self.recorder = ScreenRecorder(capture_region=capture_region, target_fps=60)
        self.frame_analyzer = FrameAnalyzer(stabilize=True)

        meta = _GUN_META.get(gun_name.lower(), {})
        self.fire_interval = meta.get("fire_interval", 0.0857)
        self.fire_interval_ms = self.fire_interval * 1000
        self.magazine = meta.get("mag", 40)
        self.ticks_per_shot = max(1, round(self.fire_interval_ms / 9))

    # ── 录制控制 ──

    def start_recording(self):
        self.recorder.start()

    def stop_recording(self):
        return self.recorder.stop()

    def enable_hotkeys(self, on_start=None, on_stop=None):
        self.recorder.start_hotkey_listener("f6", "f7", on_start, on_stop)

    def disable_hotkeys(self):
        self.recorder.stop_hotkey_listener()

    def save_recording(self, path=None):
        return self.recorder.save_video(path)

    # ── 弹孔检测 ──

    def detect_holes(self, mode="initial", progress_cb=None):
        """检测弹孔，返回 (base_frame_bgr, holes_list)。

        mode:
            "initial" — 帧差分时序检测 (弹孔分散, 保留射击顺序)
            "refine"  — 最后一帧静态检测 (弹孔密集/重叠, 用 BulletDetector)

        holes_list 格式: [{"x", "y", "shot_num", ...}, ...]
        可直接加载到 BulletCanvas 供手动调整。
        """
        if self.recorder.frame_count < 5:
            log.warning("帧数不足 (%d)", self.recorder.frame_count)
            return None, []

        if mode == "initial":
            return self._detect_frame_diff(progress_cb)
        else:
            return self._detect_static(progress_cb)

    def _detect_frame_diff(self, progress_cb):
        """initial 模式: 帧差分时序检测。"""
        holes = self.frame_analyzer.analyze(
            self.recorder.frames, self.fire_interval_ms, progress_cb)

        last_frame = self.recorder.get_last_frame()
        if last_frame is None:
            return None, holes

        for h in holes:
            h.setdefault("area", 100)
            h.setdefault("circularity", 1.0)
            h.setdefault("color_diff", 50)

        log.info("initial 帧差分: %d 个弹孔, %d 个调试帧",
                 len(holes), len(self.frame_analyzer.debug_frames))
        return last_frame, holes

    def _detect_static(self, progress_cb):
        """refine 模式: 用 BulletDetector 在最后一帧做静态检测。

        比帧差分更适合弹孔密集/重叠的情况。
        """
        last_frame = self.recorder.get_last_frame()
        if last_frame is None:
            return None, []

        if BulletDetector is None:
            log.error("BulletDetector 不可用")
            return last_frame, []

        if progress_cb:
            progress_cb(0.1)

        detector = BulletDetector(sensitivity="high")
        holes = detector.detect_single(last_frame)

        if progress_cb:
            progress_cb(0.8)

        if holes:
            holes.sort(key=lambda h: h["y"])
            for i, h in enumerate(holes):
                h["shot_num"] = i + 1

        if progress_cb:
            progress_cb(1.0)

        log.info("refine 静态检测: %d 个弹孔", len(holes))
        return last_frame, holes

    def get_annotated_frame(self, holes, title=None):
        """生成标注图 (在最后一帧上绘制弹孔标号 + 轨迹线)。"""
        last = self.recorder.get_last_frame()
        if last is None:
            return None
        t = title or f"{self.gun_name} [{self.acc_code}]"
        return annotate_frame(last, holes, title=t)

    def save_annotated_frame(self, holes, path=None):
        """保存标注图到文件，返回路径。"""
        img = self.get_annotated_frame(holes)
        if img is None:
            return None
        if path is None:
            out_dir = Path("calibration_results")
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(out_dir / f"annotated_{self.gun_name}_{ts}.png")
        cv2.imwrite(path, img)
        log.info("标注图已保存: %s", path)
        return path

    def get_debug_frames(self):
        """获取帧差分过程中的关键帧 (仅 initial 模式有效)。

        Returns: [{"frame_idx", "diff_image", "binary_image", "new_holes"}, ...]
        """
        return self.frame_analyzer.debug_frames

    # ── GunData 交互 ──

    def load_prev_data(self):
        gp = self.gun_data_dir / f"{self.gun_name}.json"
        if not gp.exists():
            return None
        try:
            with open(gp, encoding="utf-8") as f:
                gd = json.load(f)
            if gd.get("version") != 2:
                return None
            return gd.get("recoil", {}).get(self.acc_code, {}).get("y")
        except Exception:
            return None

    def write_to_gundata(self, y_array, x_array=None, backup=True):
        """直接将 per-shot 数组写入 GunData v2 JSON。"""
        gp = self.gun_data_dir / f"{self.gun_name}.json"
        if not gp.exists():
            log.error("文件不存在: %s", gp)
            return False

        with open(gp, encoding="utf-8") as f:
            gd = json.load(f)
        if gd.get("version") != 2:
            log.error("非 v2 格式")
            return False

        if backup:
            bak = gp.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
            with open(bak, "w", encoding="utf-8") as f:
                json.dump(gd, f, ensure_ascii=False, indent=4)

        if x_array is None:
            x_array = [0.0] * len(y_array)

        gd.setdefault("recoil", {})[self.acc_code] = {
            "y": y_array, "x": x_array,
        }
        with open(gp, "w", encoding="utf-8") as f:
            json.dump(gd, f, ensure_ascii=False, indent=4)

        log.info("写入 %s [%s]: %d 发", self.gun_name, self.acc_code, len(y_array))
        return True


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="PUBG 视频校准工具 (v2)")
    parser.add_argument("gun", help="枪械名 (m416, akm, ...)")
    parser.add_argument("--acc", default="A0B0C0", help="配件码")
    parser.add_argument("--scope", type=float, default=1.0, help="倍镜灵敏度")
    parser.add_argument("--posture", type=float, default=1.0, help="姿态系数")
    parser.add_argument("--mode", choices=["initial", "refine"], default="initial")
    parser.add_argument("--region", help="捕获区域 left,top,width,height")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")

    region = tuple(int(x) for x in args.region.split(",")) if args.region else None
    vc = VideoCalibrator(args.gun, args.acc, args.scope, args.posture,
                         capture_region=region)

    print(f"\n{'='*44}")
    print(f"  PUBG 视频校准 v2 (透明化)")
    print(f"  枪械: {args.gun} [{args.acc}]")
    print(f"  模式: {'初始生成 (帧差分)' if args.mode == 'initial' else '迭代修正 (静态检测)'}")
    print(f"{'='*44}")
    print(f"\n  按 F6 开始录制 → 对墙射击 → 按 F7 停止")
    print(f"  Ctrl+C 退出\n")

    done = threading.Event()

    def on_start():
        print("  [录制中] 射击完毕后按 F7 ...")

    def on_stop():
        n = vc.recorder.frame_count
        print(f"\n  录制结束: {n} 帧")
        if n < 10:
            print("  帧数不足, 请重试")
            return

        video_path = vc.save_recording()
        print(f"  录屏已保存: {video_path}")

        print("  分析中 ...")
        frame, holes = vc.detect_holes(
            args.mode,
            lambda p: print(f"\r  进度: {p*100:.0f}%", end="", flush=True))
        print()

        if not holes:
            print("  未检测到弹孔")
            done.set()
            return

        print(f"  检测到 {len(holes)} 个弹孔:")
        for h in holes:
            print(f"    #{h['shot_num']:2d}  ({h['x']:4d}, {h['y']:4d})")

        ann_path = vc.save_annotated_frame(holes)
        print(f"  标注图已保存: {ann_path}")
        print(f"\n  请在 GUI 中打开标注图确认弹孔位置，手动调整后再计算参数")

        done.set()

    vc.enable_hotkeys(on_start, on_stop)

    try:
        while not done.wait(timeout=1):
            pass
    except KeyboardInterrupt:
        print("\n  已退出")
    finally:
        vc.disable_hotkeys()
        if vc.recorder.recording:
            vc.recorder.stop()


if __name__ == "__main__":
    main()
