#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 视频校准模块
═══════════════════════════
录屏 + 逐帧差分自动检测弹孔 + 直接输出 per-shot v2 格式

流程:
    F6 开始录制 → 对墙射击 → F7 停止
    工具自动检测弹孔时序 → 输出 per-shot 补偿值
    一键写入 GunData v2 JSON

两种模式:
    initial  — 无宏，从弹痕反推初始补偿值
    refine   — 有宏，从残差弹痕迭代修正已有参数
"""

import cv2
import json
import logging
import mss
import numpy as np
import threading
import time
from pathlib import Path
from datetime import datetime

log = logging.getLogger("video_calibrator")

try:
    from calibration.bullet_analysis import (
        _GUN_META, _get_fire_interval, _find_gun_data_dir,
    )
except ImportError:
    try:
        from bullet_analysis import (
            _GUN_META, _get_fire_interval, _find_gun_data_dir,
        )
    except ImportError:
        _GUN_META = {}
        def _get_fire_interval(n): return None
        def _find_gun_data_dir(): return "./_internal/GunData"


# ═══════════════════════════════════════════
# 录屏器
# ═══════════════════════════════════════════

class ScreenRecorder:
    """高速屏幕捕获，支持 F6/F7 热键控制。"""

    def __init__(self, capture_region=None, target_fps=60):
        """
        :param capture_region: (left, top, width, height) 或 None 自动取屏幕中央
        :param target_fps: 目标帧率
        """
        self.capture_region = capture_region
        self.target_fps = target_fps
        self.frames = []
        self._recording = False
        self._thread = None
        self._hotkey_listener = None

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
        region = (
            {"left": self.capture_region[0], "top": self.capture_region[1],
             "width": self.capture_region[2], "height": self.capture_region[3]}
            if self.capture_region else self._auto_region()
        )
        with mss.mss() as sct:
            while self._recording:
                t0 = time.perf_counter()
                raw = sct.grab(region)
                frame = np.array(raw)[:, :, :3].copy()
                self.frames.append((time.time(), frame))
                sleep_t = interval - (time.perf_counter() - t0)
                if sleep_t > 0:
                    time.sleep(sleep_t)

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
# 帧分析器
# ═══════════════════════════════════════════

class FrameAnalyzer:
    """逐帧差分 + 图像稳定 + 增量弹孔检测。"""

    def __init__(self, diff_threshold=25, stabilize=True,
                 min_area_ratio=5e-6, max_area_ratio=8e-4):
        self.diff_threshold = diff_threshold
        self.stabilize = stabilize
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio

    def analyze(self, frames, fire_interval_ms=85.7, progress_cb=None):
        """分析录制帧序列，返回按时间排序的弹孔列表。

        Returns:
            [{"x": int, "y": int, "timestamp": float, "shot_num": int}, ...]
        """
        if len(frames) < 5:
            return []

        ref_t, ref_bgr = frames[0]
        ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
        h, w = ref_gray.shape
        pixels = h * w
        min_a = max(4, int(pixels * self.min_area_ratio))
        max_a = int(pixels * self.max_area_ratio)
        nms_r = max(8, int(min(h, w) * 0.01))

        ref_kp, ref_des = None, None
        if self.stabilize:
            orb = cv2.ORB_create(nfeatures=1500)
            ref_kp, ref_des = orb.detectAndCompute(ref_gray, None)
        else:
            orb = None

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
                    detected.append({"x": cx, "y": cy, "timestamp": cur_t,
                                     "frame_idx": idx})
                    known.add(gk)

        detected.sort(key=lambda h: h["timestamp"])
        for i, hole in enumerate(detected):
            hole["shot_num"] = i + 1

        if progress_cb:
            progress_cb(1.0)
        log.info("检测到 %d 个弹孔", len(detected))
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
            return cv2.warpPerspective(frame_gray, H, (ref_gray.shape[1], ref_gray.shape[0]))
        except Exception:
            return frame_gray


# ═══════════════════════════════════════════
# 主控制器
# ═══════════════════════════════════════════

class VideoCalibrator:
    """视频校准主控器

    用法::

        vc = VideoCalibrator("m416", "A0B0C0", scope_val=1.0)
        vc.enable_hotkeys()          # F6 开始, F7 停止
        # ... 用户射击 ...
        result = vc.analyze()        # 自动分析
        vc.write_to_gundata(result)  # 一键写入
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
        self.analyzer = FrameAnalyzer(stabilize=True)

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

    # ── 分析 ──

    def analyze(self, mode="initial", prev_data=None, progress_cb=None):
        """
        :param mode: "initial" 初始生成 | "refine" 迭代修正
        :param prev_data: refine 模式下传入当前 y_array
        :param progress_cb: 进度回调 (0.0~1.0)
        """
        holes = self.analyzer.analyze(
            self.recorder.frames, self.fire_interval_ms, progress_cb)
        if len(holes) < 2:
            log.warning("弹孔不足 (%d), 无法计算", len(holes))
            return None
        if mode == "refine" and prev_data is not None:
            return self._refine(holes, prev_data)
        return self._generate(holes)

    def _generate(self, holes):
        """无宏模式: 从弹痕像素距反推 per-shot raw 值。"""
        factor = max(0.01, self.scope_val * self.posture_val)
        y_arr, x_arr, details = [], [], []

        for i in range(1, len(holes)):
            dy = abs(holes[i - 1]["y"] - holes[i]["y"])
            dx = holes[i]["x"] - holes[i - 1]["x"]
            ry = round(dy / factor, 2)
            rx = round(dx / factor, 2)
            y_arr.append(ry)
            x_arr.append(rx)
            details.append({
                "shot": i, "pixel_dy": round(dy, 2), "pixel_dx": round(dx, 2),
                "raw_y": ry, "raw_x": rx,
                "dt_ms": round((holes[i]["timestamp"] - holes[i - 1]["timestamp"]) * 1000, 1),
            })

        return {
            "mode": "initial",
            "gun_name": self.gun_name, "acc_code": self.acc_code,
            "scope_val": self.scope_val, "posture_val": self.posture_val,
            "n_holes": len(holes), "n_shots": len(y_arr),
            "rpm": round(60 / self.fire_interval) if self.fire_interval > 0 else 0,
            "ticks_per_shot": self.ticks_per_shot,
            "y_array": y_arr, "x_array": x_arr,
            "details": details, "holes": holes,
        }

    def _refine(self, holes, prev_y):
        """有宏模式: 根据残差弹痕迭代修正已有参数。"""
        factor = max(0.01, self.scope_val * self.posture_val)
        n = min(len(holes) - 1, len(prev_y))
        corrected = list(prev_y)
        details = []

        for i in range(n):
            dy = holes[i + 1]["y"] - holes[i]["y"]
            theo = prev_y[i] * self.scope_val * self.posture_val

            if abs(theo) > 0.01:
                ratio = theo / max(0.01, theo + abs(dy))
                if dy < 0:
                    ratio = 1.0 / max(0.01, ratio)
                ratio = max(0.1, min(10.0, ratio))
                corrected[i] = round(prev_y[i] * ratio, 2)
            elif abs(dy) > 2:
                corrected[i] = round(abs(dy) / factor, 2)

            details.append({
                "shot": i + 1, "residual_dy": round(dy, 2),
                "prev_y": prev_y[i], "corrected_y": corrected[i],
            })

        return {
            "mode": "refine",
            "gun_name": self.gun_name, "acc_code": self.acc_code,
            "n_shots_corrected": n,
            "original_y": list(prev_y), "corrected_y": corrected,
            "x_array": [0.0] * len(corrected), "details": details,
        }

    # ── GunData 写入 ──

    def write_to_gundata(self, result, backup=True):
        """将校准结果一键写入 GunData v2 JSON。"""
        if result is None:
            return False
        gp = self.gun_data_dir / f"{self.gun_name}.json"
        if not gp.exists():
            log.error("文件不存在: %s", gp)
            return False

        with open(gp, encoding="utf-8") as f:
            gd = json.load(f)
        if gd.get("version") != 2:
            log.error("非 v2 格式，请先运行 tools/migrate_gundata.py")
            return False

        if backup:
            bak = gp.with_suffix(f".{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
            with open(bak, "w", encoding="utf-8") as f:
                json.dump(gd, f, ensure_ascii=False, indent=4)

        y_key = "corrected_y" if result["mode"] == "refine" else "y_array"
        gd.setdefault("recoil", {})[self.acc_code] = {
            "y": result[y_key],
            "x": result.get("x_array", [0.0] * len(result[y_key])),
        }
        with open(gp, "w", encoding="utf-8") as f:
            json.dump(gd, f, ensure_ascii=False, indent=4)

        log.info("写入 %s [%s]: %d 发", self.gun_name, self.acc_code, len(result[y_key]))
        return True

    # ── 工具 ──

    def load_prev_data(self):
        """从 GunData 加载当前配件的 y_array (供 refine 模式使用)。"""
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

    def summary(self, result):
        if result is None:
            return "无结果"
        lines = [
            f"模式: {'初始生成' if result['mode'] == 'initial' else '迭代修正'}",
            f"枪械: {result.get('gun_name', '?')} [{result.get('acc_code', '?')}]",
        ]
        if result["mode"] == "initial":
            y = result.get("y_array", [])
            lines.append(f"弹孔数: {result.get('n_holes', 0)}")
            lines.append(f"per-shot: {len(y)} 发")
            if y:
                lines.append(f"范围: {min(y):.1f} ~ {max(y):.1f}, 均值: {sum(y)/len(y):.1f}")
        else:
            details = result.get("details", [])
            if details:
                res = [abs(d["residual_dy"]) for d in details]
                lines.append(f"修正: {result.get('n_shots_corrected', 0)} 发")
                lines.append(f"残差: 均{sum(res)/len(res):.1f}px, 最大{max(res):.1f}px")
        return "\n".join(lines)


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="PUBG 视频校准工具")
    parser.add_argument("gun", help="枪械名 (m416, akm, ...)")
    parser.add_argument("--acc", default="A0B0C0", help="配件码")
    parser.add_argument("--scope", type=float, default=1.0, help="倍镜灵敏度")
    parser.add_argument("--posture", type=float, default=1.0, help="姿态系数")
    parser.add_argument("--mode", choices=["initial", "refine"], default="initial")
    parser.add_argument("--write", action="store_true", help="自动写入 GunData")
    parser.add_argument("--region", help="捕获区域 left,top,width,height")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")

    region = tuple(int(x) for x in args.region.split(",")) if args.region else None

    vc = VideoCalibrator(args.gun, args.acc, args.scope, args.posture,
                         capture_region=region)

    prev_data = vc.load_prev_data() if args.mode == "refine" else None

    print(f"\n{'='*40}")
    print(f"  PUBG 视频校准")
    print(f"  枪械: {args.gun} [{args.acc}]")
    print(f"  模式: {'初始生成' if args.mode == 'initial' else '迭代修正'}")
    print(f"{'='*40}")
    print(f"\n  按 F6 开始录制 → 对墙射击 → 按 F7 停止")
    print(f"  Ctrl+C 退出\n")

    done = threading.Event()

    def on_start():
        print("  [录制中] 射击完毕后按 F7 ...")

    def on_stop():
        n = vc.recorder.frame_count
        print(f"  [停止] {n} 帧")
        if n < 10:
            print("  帧数不足, 请重新 F6 录制")
            return

        print("  分析中 ...")
        result = vc.analyze(args.mode, prev_data,
                            lambda p: print(f"\r  进度: {p*100:.0f}%", end="", flush=True))
        print()

        if result is None:
            print("  分析失败")
            return

        print(f"\n{vc.summary(result)}\n")
        y = result.get("y_array" if result["mode"] == "initial" else "corrected_y", [])
        print(f"  Y 值: {y}\n")

        if args.write:
            ok = vc.write_to_gundata(result)
            print(f"  {'写入成功' if ok else '写入失败'}")

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
