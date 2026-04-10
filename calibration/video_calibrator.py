#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 视频校准模块 (v3 — YOLO + 视频加载)
═══════════════════════════════════════════
支持三种检测后端:
  1. YOLO 模型 (推荐, 需训练)  — 高精度, 抗纹理干扰
  2. 帧差分时序              — 保留射击顺序, 需干净墙面
  3. 传统静态 (BulletDetector) — 兜底

支持两种输入:
  - 实时录屏 (F6/F7)
  - 加载已有视频文件 (.avi/.mp4)
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
# YOLO 弹孔检测器
# ═══════════════════════════════════════════

class YOLOHoleDetector:
    """YOLOv8/v11 弹孔检测器。

    需要提供训练好的 .pt 模型文件。
    训练方法见 tools/train_yolo_guide.md

    用法::

        detector = YOLOHoleDetector("models/bullet_hole_best.pt")
        holes = detector.detect(image_bgr)
    """

    _INSTANCE = None
    _INSTANCE_PATH = None

    def __init__(self, model_path):
        self.model_path = str(model_path)
        self.model = None
        self.available = False
        self._load()

    def _load(self):
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            self.available = True
            log.info("YOLO 模型已加载: %s", self.model_path)
        except ImportError:
            log.warning("ultralytics 未安装, 运行: pip install ultralytics")
        except Exception as e:
            log.error("YOLO 模型加载失败: %s", e)

    @classmethod
    def get_or_create(cls, model_path):
        """缓存单例，避免重复加载同一模型。"""
        p = str(model_path)
        if cls._INSTANCE is None or cls._INSTANCE_PATH != p:
            cls._INSTANCE = cls(p)
            cls._INSTANCE_PATH = p
        return cls._INSTANCE

    def detect(self, image, conf=0.25):
        """检测弹孔，返回 holes 列表。

        Returns:
            [{"x", "y", "shot_num", "confidence", "bbox", "area", ...}, ...]
        """
        if not self.available or self.model is None:
            return []

        results = self.model(image, conf=conf, verbose=False)
        holes = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                w, h = int(x2 - x1), int(y2 - y1)
                holes.append({
                    "x": cx, "y": cy,
                    "area": w * h,
                    "confidence": round(float(box.conf[0]), 3),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "circularity": 1.0,
                    "color_diff": 50,
                })
        holes.sort(key=lambda h: h["y"])
        for i, h in enumerate(holes):
            h["shot_num"] = i + 1
        return holes

    def detect_video_temporal(self, frames, fire_interval_ms=85.7,
                              conf=0.25, progress_cb=None):
        """逐帧 YOLO 检测 + 时序增量跟踪，保留射击顺序。

        与帧差分不同: YOLO 在每帧独立识别弹孔，通过与已知集合比对发现新弹孔。
        不需要干净墙面，不需要图像稳定。
        """
        if not self.available or len(frames) < 2:
            return []

        detected = []
        known_positions = []
        nms_dist = 15

        sample_step = max(1, int(fire_interval_ms / 2 / 16.7))

        for idx in range(0, len(frames), sample_step):
            if progress_cb and idx % (sample_step * 5) == 0:
                progress_cb(idx / len(frames))

            cur_t, cur_bgr = frames[idx]
            frame_holes = self.detect(cur_bgr, conf=conf)

            for fh in frame_holes:
                is_new = True
                for kx, ky in known_positions:
                    if abs(fh["x"] - kx) < nms_dist and abs(fh["y"] - ky) < nms_dist:
                        is_new = False
                        break
                if is_new:
                    fh["timestamp"] = cur_t
                    fh["frame_idx"] = idx
                    detected.append(fh)
                    known_positions.append((fh["x"], fh["y"]))

        detected.sort(key=lambda h: h.get("timestamp", 0))
        for i, h in enumerate(detected):
            h["shot_num"] = i + 1

        if progress_cb:
            progress_cb(1.0)

        log.info("YOLO 时序检测: %d 个弹孔", len(detected))
        return detected


def find_yolo_model():
    """在常见路径查找训练好的 YOLO 弹孔模型。"""
    candidates = [
        Path("models/bullet_hole_best.pt"),
        Path("models/best.pt"),
        Path("calibration/models/best.pt"),
        Path(__file__).resolve().parent / "models" / "best.pt",
        Path(__file__).resolve().parent.parent / "models" / "bullet_hole_best.pt",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


# ═══════════════════════════════════════════
# 录屏器
# ═══════════════════════════════════════════

class ScreenRecorder:
    """高速屏幕捕获 + 视频文件加载，支持 F6/F7 热键。"""

    def __init__(self, capture_region=None, target_fps=60):
        self.capture_region = capture_region
        self.target_fps = target_fps
        self.frames = []
        self._recording = False
        self._thread = None
        self._hotkey_listener = None
        self.actual_region = None
        self.source_path = None

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

    # ── 实时录制 ──

    def start(self):
        if self._recording:
            return
        self._recording = True
        self.frames = []
        self.source_path = None
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

    # ── 视频文件加载 ──

    def load_video(self, path):
        """从视频文件加载帧序列，替代实时录制。

        Returns: 加载的帧数
        """
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            log.error("无法打开视频: %s", path)
            return 0

        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        self.frames = []
        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            t = idx / fps
            self.frames.append((t, frame))
            idx += 1
        cap.release()

        self.source_path = str(path)
        log.info("视频加载: %s (%d 帧, %.1f fps)", path, len(self.frames), fps)
        return len(self.frames)

    # ── 帧访问 ──

    def get_reference_frame(self):
        return self.frames[0][1].copy() if self.frames else None

    def get_last_frame(self):
        return self.frames[-1][1].copy() if self.frames else None

    def get_frame_at(self, index):
        if 0 <= index < len(self.frames):
            return self.frames[index][1].copy()
        return None

    # ── 保存 ──

    def save_video(self, path=None):
        if len(self.frames) < 2:
            return None
        if path is None:
            out_dir = Path("calibration_results")
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(out_dir / f"recording_{ts}.avi")

        h, w = self.frames[0][1].shape[:2]
        dur = self.frames[-1][0] - self.frames[0][0]
        fps = len(self.frames) / max(0.01, dur) if dur > 0 else 30

        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
        for _, frame in self.frames:
            writer.write(frame)
        writer.release()
        log.info("视频保存: %s (%d帧, %.1ffps)", path, len(self.frames), fps)
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
        log.info("热键: %s=开始, %s=停止", start_key.upper(), stop_key.upper())

    def stop_hotkey_listener(self):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None


# ═══════════════════════════════════════════
# 帧分析器 (传统帧差分, 仅限干净墙面)
# ═══════════════════════════════════════════

class FrameAnalyzer:
    """逐帧差分 + 图像稳定 + 增量弹孔检测 (传统 CV)。"""

    def __init__(self, diff_threshold=25, stabilize=True,
                 min_area_ratio=5e-6, max_area_ratio=8e-4):
        self.diff_threshold = diff_threshold
        self.stabilize = stabilize
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio
        self.debug_frames = []

    def analyze(self, frames, fire_interval_ms=85.7, progress_cb=None):
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

        ref_kp, ref_des, orb = None, None, None
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
                    "frame_idx": idx, "timestamp": cur_t,
                    "diff_image": diff.copy(), "binary_image": bw.copy(),
                    "new_holes": list(new_in_frame),
                })

        detected.sort(key=lambda h: h["timestamp"])
        for i, hole in enumerate(detected):
            hole["shot_num"] = i + 1

        if progress_cb:
            progress_cb(1.0)
        log.info("帧差分: %d 个弹孔", len(detected))
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
    """在帧上绘制弹孔标注 (编号 + 轨迹线 + confidence + bbox)。"""
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

        bbox = hole.get("bbox")
        if bbox:
            cv2.rectangle(canvas, (bbox[0], bbox[1]), (bbox[2], bbox[3]),
                          color, thickness, cv2.LINE_AA)
        else:
            cv2.circle(canvas, (hole["x"], hole["y"]), radius, color,
                       thickness + 1, cv2.LINE_AA)

        cv2.circle(canvas, (hole["x"], hole["y"]), max(2, radius // 3),
                   color, -1, cv2.LINE_AA)

        conf = hole.get("confidence")
        label = f"{sn}" if conf is None else f"{sn} ({conf:.0%})"
        lx = hole["x"] + radius + 3
        ly = hole["y"] - radius
        cv2.putText(canvas, label, (lx, ly), font, font_scale,
                    (255, 255, 255), thickness + 1, cv2.LINE_AA)
        cv2.putText(canvas, label, (lx, ly), font, font_scale,
                    color, thickness, cv2.LINE_AA)

    info_lines = [f"Holes: {n}", "Red=early  Orange=mid  Green=late"]
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
    """视频校准主控器 (v3)

    支持三种检测后端 + 两种输入源::

        vc = VideoCalibrator("m416")

        # 输入方式 1: 实时录屏
        vc.start_recording()
        # ... 射击 ...
        vc.stop_recording()

        # 输入方式 2: 加载视频文件
        vc.load_video("recording.avi")

        # 检测弹孔 (三种后端)
        frame, holes = vc.detect_holes("yolo")       # YOLO 模型
        frame, holes = vc.detect_holes("yolo_temporal")  # YOLO + 时序
        frame, holes = vc.detect_holes("frame_diff")  # 传统帧差分
        frame, holes = vc.detect_holes("static")      # 传统静态

        # 标注 → 加载到画布 → 手动确认
    """

    BACKENDS = ("yolo", "yolo_temporal", "frame_diff", "static")

    def __init__(self, gun_name, acc_code="A0B0C0",
                 scope_val=1.0, posture_val=1.0,
                 capture_region=None, gun_data_dir=None,
                 yolo_model_path=None):
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

        self._yolo = None
        yp = yolo_model_path or find_yolo_model()
        if yp:
            self._yolo = YOLOHoleDetector.get_or_create(yp)

    @property
    def yolo_available(self):
        return self._yolo is not None and self._yolo.available

    def set_yolo_model(self, model_path):
        self._yolo = YOLOHoleDetector.get_or_create(model_path)

    # ── 输入 ──

    def start_recording(self):
        self.recorder.start()

    def stop_recording(self):
        return self.recorder.stop()

    def load_video(self, path):
        """从视频文件加载帧 (替代实时录屏)。"""
        return self.recorder.load_video(path)

    def enable_hotkeys(self, on_start=None, on_stop=None):
        self.recorder.start_hotkey_listener("f6", "f7", on_start, on_stop)

    def disable_hotkeys(self):
        self.recorder.stop_hotkey_listener()

    def save_recording(self, path=None):
        return self.recorder.save_video(path)

    # ── 弹孔检测 (多后端) ──

    def detect_holes(self, backend="yolo", progress_cb=None):
        """检测弹孔，返回 (base_frame_bgr, holes_list)。

        backend:
            "yolo"          — YOLO 在最后一帧检测 (推荐, 最高精度)
            "yolo_temporal"  — YOLO 逐帧扫描 + 时序追踪 (保留射击顺序)
            "frame_diff"    — 传统帧差分 (需干净墙面)
            "static"        — 传统 BulletDetector 静态检测
        """
        if self.recorder.frame_count < 2:
            log.warning("帧数不足 (%d)", self.recorder.frame_count)
            return None, []

        if backend == "yolo":
            return self._detect_yolo_static(progress_cb)
        elif backend == "yolo_temporal":
            return self._detect_yolo_temporal(progress_cb)
        elif backend == "frame_diff":
            return self._detect_frame_diff(progress_cb)
        elif backend == "static":
            return self._detect_traditional_static(progress_cb)
        else:
            log.error("未知后端: %s", backend)
            return None, []

    def _detect_yolo_static(self, progress_cb):
        """YOLO 在最后一帧做静态检测。"""
        last = self.recorder.get_last_frame()
        if last is None:
            return None, []
        if not self.yolo_available:
            log.warning("YOLO 不可用，回退到传统静态检测")
            return self._detect_traditional_static(progress_cb)

        if progress_cb:
            progress_cb(0.1)
        holes = self._yolo.detect(last)
        if progress_cb:
            progress_cb(1.0)
        log.info("YOLO 静态: %d 个弹孔", len(holes))
        return last, holes

    def _detect_yolo_temporal(self, progress_cb):
        """YOLO 逐帧检测 + 时序追踪。"""
        if not self.yolo_available:
            log.warning("YOLO 不可用，回退到帧差分")
            return self._detect_frame_diff(progress_cb)

        holes = self._yolo.detect_video_temporal(
            self.recorder.frames, self.fire_interval_ms,
            progress_cb=progress_cb)
        last = self.recorder.get_last_frame()
        log.info("YOLO 时序: %d 个弹孔", len(holes))
        return last, holes

    def _detect_frame_diff(self, progress_cb):
        """传统帧差分时序检测。"""
        holes = self.frame_analyzer.analyze(
            self.recorder.frames, self.fire_interval_ms, progress_cb)
        last = self.recorder.get_last_frame()
        for h in holes:
            h.setdefault("area", 100)
            h.setdefault("circularity", 1.0)
            h.setdefault("color_diff", 50)
        return last, holes

    def _detect_traditional_static(self, progress_cb):
        """传统 BulletDetector 最后一帧静态检测。"""
        last = self.recorder.get_last_frame()
        if last is None:
            return None, []
        if BulletDetector is None:
            log.error("BulletDetector 不可用")
            return last, []
        if progress_cb:
            progress_cb(0.1)
        detector = BulletDetector(sensitivity="high")
        holes = detector.detect_single(last)
        if holes:
            holes.sort(key=lambda h: h["y"])
            for i, h in enumerate(holes):
                h["shot_num"] = i + 1
        if progress_cb:
            progress_cb(1.0)
        return last, holes

    # ── 标注 ──

    def get_annotated_frame(self, holes, title=None):
        last = self.recorder.get_last_frame()
        if last is None:
            return None
        t = title or f"{self.gun_name} [{self.acc_code}]"
        return annotate_frame(last, holes, title=t)

    def save_annotated_frame(self, holes, path=None):
        img = self.get_annotated_frame(holes)
        if img is None:
            return None
        if path is None:
            out_dir = Path("calibration_results")
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(out_dir / f"annotated_{self.gun_name}_{ts}.png")
        cv2.imwrite(path, img)
        log.info("标注图: %s", path)
        return path

    def get_debug_frames(self):
        return self.frame_analyzer.debug_frames

    # ── GunData ──

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
        gp = self.gun_data_dir / f"{self.gun_name}.json"
        if not gp.exists():
            return False
        with open(gp, encoding="utf-8") as f:
            gd = json.load(f)
        if gd.get("version") != 2:
            return False
        if backup:
            bak = gp.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
            with open(bak, "w", encoding="utf-8") as f:
                json.dump(gd, f, ensure_ascii=False, indent=4)
        if x_array is None:
            x_array = [0.0] * len(y_array)
        gd.setdefault("recoil", {})[self.acc_code] = {"y": y_array, "x": x_array}
        with open(gp, "w", encoding="utf-8") as f:
            json.dump(gd, f, ensure_ascii=False, indent=4)
        log.info("写入 %s [%s]: %d 发", self.gun_name, self.acc_code, len(y_array))
        return True


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="PUBG 视频校准 v3 (YOLO)")
    parser.add_argument("gun", help="枪械名")
    parser.add_argument("--acc", default="A0B0C0")
    parser.add_argument("--backend", choices=VideoCalibrator.BACKENDS,
                        default="yolo", help="检测后端")
    parser.add_argument("--video", help="加载视频文件 (替代实时录屏)")
    parser.add_argument("--model", help="YOLO 模型路径 (.pt)")
    parser.add_argument("--scope", type=float, default=1.0)
    parser.add_argument("--posture", type=float, default=1.0)
    parser.add_argument("--region", help="捕获区域 left,top,w,h")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")

    region = tuple(int(x) for x in args.region.split(",")) if args.region else None
    vc = VideoCalibrator(args.gun, args.acc, args.scope, args.posture,
                         capture_region=region, yolo_model_path=args.model)

    print(f"\n{'='*48}")
    print(f"  PUBG 视频校准 v3")
    print(f"  枪械: {args.gun} [{args.acc}]")
    print(f"  后端: {args.backend}")
    print(f"  YOLO: {'可用' if vc.yolo_available else '不可用 (需要模型文件)'}")
    print(f"{'='*48}")

    if args.video:
        n = vc.load_video(args.video)
        print(f"\n  已加载视频: {args.video} ({n} 帧)")
        if n < 2:
            print("  帧数不足"); return

        frame, holes = vc.detect_holes(args.backend)
        if not holes:
            print("  未检测到弹孔"); return

        print(f"  检测到 {len(holes)} 个弹孔:")
        for h in holes:
            conf = f" conf={h['confidence']:.0%}" if "confidence" in h else ""
            print(f"    #{h['shot_num']:2d}  ({h['x']:4d}, {h['y']:4d}){conf}")

        ann_path = vc.save_annotated_frame(holes)
        print(f"  标注图: {ann_path}")
        return

    print(f"\n  按 F6 开始录制 → 对墙射击 → 按 F7 停止")
    print(f"  Ctrl+C 退出\n")

    done = threading.Event()

    def on_start():
        print("  [录制中] 射击完毕后按 F7 ...")

    def on_stop():
        n = vc.recorder.frame_count
        print(f"\n  录制: {n} 帧")
        if n < 10:
            print("  帧数不足"); return

        vp = vc.save_recording()
        print(f"  视频: {vp}")

        frame, holes = vc.detect_holes(args.backend)
        if not holes:
            print("  未检测到弹孔"); done.set(); return

        print(f"  {len(holes)} 个弹孔:")
        for h in holes:
            conf = f" conf={h['confidence']:.0%}" if "confidence" in h else ""
            print(f"    #{h['shot_num']:2d}  ({h['x']:4d}, {h['y']:4d}){conf}")

        ann = vc.save_annotated_frame(holes)
        print(f"  标注图: {ann}")
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
