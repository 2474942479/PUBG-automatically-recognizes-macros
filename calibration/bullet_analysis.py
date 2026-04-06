#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 弹痕分析模块 (v3 重构)
═══════════════════════════
核心类:
  BulletDetector      - 弹痕检测 (SimpleBlobDetector / 中值差分 / 模板匹配)
  BulletSorter        - 按开枪顺序排序
  BulletComparator    - 与 GunData 理论数据对比
  BulletVisualizer    - 绘制标注图
  ProjectData         - 统一项目数据 (.calibration.json)
  ParameterCorrector  - 生成修正参数
  IterativeCorrector  - 迭代修正
  MultiGroupAnalyzer  - 多组交叉比对
"""

import copy
import cv2
import json
import logging
import numpy as np
from pathlib import Path
from datetime import datetime

log = logging.getLogger("bullet_analysis")

# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _find_gun_data_dir():
    """从多个候选路径查找 GunData 目录"""
    for p in [
        Path('./_internal/GunData'),
        Path('../_internal/GunData'),
        Path(__file__).resolve().parent.parent / '_internal' / 'GunData',
    ]:
        if p.is_dir():
            return str(p.resolve())
    return str(Path('./_internal/GunData'))


def _load_sensitivity_config():
    """从 Config/config.json 读取灵敏度 (scope multiplier) 配置"""
    for p in [
        Path('./Config/config.json'),
        Path('../Config/config.json'),
        Path(__file__).resolve().parent.parent / 'Config' / 'config.json',
    ]:
        if p.is_file():
            try:
                with open(p, encoding='utf-8') as f:
                    return json.load(f).get('sensitivity', {})
            except Exception:
                pass
    return {}


def _load_config_resolution():
    """从 Config/config.json 读取分辨率字符串"""
    for p in [
        Path('./Config/config.json'),
        Path('../Config/config.json'),
        Path(__file__).resolve().parent.parent / 'Config' / 'config.json',
    ]:
        if p.is_file():
            try:
                with open(p, encoding='utf-8') as f:
                    return json.load(f).get('resolution', '1920x1080')
            except Exception:
                pass
    return '1920x1080'


# 半自动枪械: 每个数组元素 = 一发子弹 (tick间隔 100ms)
_SEMI_AUTO_GUNS = frozenset([
    "sks", "mini14", "delagongnuofu", "m16a4", "mk12", "mk47",
    "qbu", "zidongzhuangtianbuqiang",
])

# 全自动 tick 间隔 (ms), 与 Process.FIRE 中的 sleep(9ms) 一致
_TICK_MS = 9

# 武器元数据 (来源: PUBG Resource v39.2 / PUBG Wiki 2026)
#   fire_interval: 射击间隔 (秒), 用于精确计算 ticks_per_shot
#   mag: 扩容弹夹容量, 仅在 fire_interval 不可用时回退使用
_GUN_META = {
    # === AR ===
    "ace32":  {"fire_interval": 0.088235, "mag": 40},
    "akm":    {"fire_interval": 0.100,    "mag": 40},
    "aug":    {"fire_interval": 0.080,    "mag": 40},
    "famas":  {"fire_interval": 0.06666,  "mag": 35},
    "g36c":   {"fire_interval": 0.0857,   "mag": 40},
    "groza":  {"fire_interval": 0.080,    "mag": 40},
    "k2":     {"fire_interval": 0.0857,   "mag": 40},
    "m16a4":  {"fire_interval": 0.075,    "mag": 40},
    "m416":   {"fire_interval": 0.0857,   "mag": 40},
    "m762":   {"fire_interval": 0.085714, "mag": 40},
    "mk47":   {"fire_interval": 0.075,    "mag": 40},
    "qbz":    {"fire_interval": 0.0923,   "mag": 40},
    "scar-l": {"fire_interval": 0.096,    "mag": 40},
    # === SMG ===
    "js9":    {"fire_interval": 0.0667,   "mag": 40},
    "mp5k":   {"fire_interval": 0.067,    "mag": 40},
    "p90":    {"fire_interval": 0.060,    "mag": 50},
    "pp19":   {"fire_interval": 0.086,    "mag": 53},
    "tangmuxunchongfengqiang": {"fire_interval": 0.080, "mag": 50},
    "ump45":  {"fire_interval": 0.090,    "mag": 35},
    "uzi":    {"fire_interval": 0.048,    "mag": 35},
    "vector": {"fire_interval": 0.0545,   "mag": 33},
    # === LMG ===
    "dp28":   {"fire_interval": 0.109,    "mag": 47},
    "m249":   {"fire_interval": 0.075,    "mag": 75},
    "mg3":    {"fire_interval": 0.085714, "mag": 75},
    # === DMR / Sniper (半自动, chunk 固定为 1) ===
    "delagongnuofu":         {"fire_interval": 0.100, "mag": 10},
    "mini14":                {"fire_interval": 0.100, "mag": 30},
    "mk12":                  {"fire_interval": 0.100, "mag": 30},
    "mk14":                  {"fire_interval": 0.090, "mag": 20},
    "qbu":                   {"fire_interval": 0.100, "mag": 20},
    "sks":                   {"fire_interval": 0.100, "mag": 20},
    "vss":                   {"fire_interval": 0.0856, "mag": 20},
    "zidongzhuangtianbuqiang": {"fire_interval": 0.100, "mag": 20},
}

def _get_gun_magazine(gun_name):
    """获取武器弹夹容量 (兼容旧接口)"""
    meta = _GUN_META.get(gun_name.lower())
    return meta["mag"] if meta else 0

def _get_fire_interval(gun_name):
    """获取武器射击间隔 (秒), 无数据则返回 None"""
    meta = _GUN_META.get(gun_name.lower())
    return meta["fire_interval"] if meta else None


def _trim_trailing_zeros(arr):
    """裁剪数组尾部连续零值, 返回有效长度"""
    i = len(arr) - 1
    while i >= 0 and arr[i] == 0:
        i -= 1
    return max(1, i + 1)


# ═══════════════════════════════════════════
# 弹痕检测 (Phase 1)
# ═══════════════════════════════════════════

class BulletDetector:
    """弹痕检测器 — 自动根据图片尺寸缩放参数

    三种检测策略:
      detect_single(image)           — 推荐: SimpleBlobDetector + 中值差分融合
      detect_with_template(img,tmpl) — 模板匹配
      detect(base, result)           — 双图差分

    所有参数根据图片实际像素尺寸自适应，不需要指定分辨率。
    """

    # 灵敏度预设: 使用相对面积比例, 对任意分辨率自适应
    _PRESETS = {
        'high': {
            'blob_min_area_ratio': 3e-6,    # minArea = 像素总数 * ratio
            'blob_max_area_ratio': 3e-3,
            'blob_min_circ': 0.15,
            'blob_min_conv': 0.3,
            'blob_min_thresh': 10,
            'blob_max_thresh': 230,
            'blob_thresh_step': 5,
            'diff_color_thresh': 2,
            'diff_min_circ': 0.08,
            'median_kernels_scale': [0.005, 0.008, 0.012, 0.018, 0.025],
            'lateral_dev_ratio': 0.06,      # max_lateral = 图宽 * ratio
        },
        'medium': {
            'blob_min_area_ratio': 8e-6,
            'blob_max_area_ratio': 2e-3,
            'blob_min_circ': 0.25,
            'blob_min_conv': 0.4,
            'blob_min_thresh': 15,
            'blob_max_thresh': 220,
            'blob_thresh_step': 8,
            'diff_color_thresh': 5,
            'diff_min_circ': 0.12,
            'median_kernels_scale': [0.008, 0.012, 0.020],
            'lateral_dev_ratio': 0.05,
        },
        'low': {
            'blob_min_area_ratio': 2e-5,
            'blob_max_area_ratio': 1e-3,
            'blob_min_circ': 0.35,
            'blob_min_conv': 0.5,
            'blob_min_thresh': 25,
            'blob_max_thresh': 200,
            'blob_thresh_step': 12,
            'diff_color_thresh': 12,
            'diff_min_circ': 0.25,
            'median_kernels_scale': [0.012, 0.020],
            'lateral_dev_ratio': 0.04,
        },
    }

    def __init__(self, sensitivity='medium'):
        self.sensitivity = sensitivity
        self.debug_info = {}
        self.debug_images = {}

    def _preset(self):
        return self._PRESETS.get(self.sensitivity, self._PRESETS['medium'])

    # ═══ 策略1: 单图自适应 (推荐) ═══

    def detect_single(self, image, roi=None):
        """单图检测: 暗点对比度 + SimpleBlobDetector + 中值差分, 三路融合去重。

        :param roi: 可选 (x, y, w, h) 元组, 只在该区域内检测
        """
        self._reset()
        img = image
        roi_offset = (0, 0)

        if roi:
            x, y, rw, rh = roi
            img = image[y:y + rh, x:x + rw]
            roi_offset = (x, y)
            log.info("ROI 裁剪: (%d,%d) %dx%d", x, y, rw, rh)

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()
        self.debug_images['01_gray'] = gray.copy()

        # 策略A: 暗点对比度检测 (主力 — 弹孔就是墙面上的暗色小点)
        dark_holes = self._detect_dark_spots(gray, h, w)
        log.debug("暗点检测: %d", len(dark_holes))

        # 策略B: SimpleBlobDetector (补充)
        blob_holes = self._detect_blobs(gray, h, w)
        log.debug("SimpleBlobDetector: %d", len(blob_holes))

        # 策略C: 多尺度中值差分 (补充)
        median_holes = self._detect_median_diff(gray, h, w)
        log.debug("中值差分: %d", len(median_holes))

        all_holes = dark_holes + blob_holes + median_holes
        self.debug_info['dark_count'] = len(dark_holes)
        self.debug_info['blob_count'] = len(blob_holes)
        self.debug_info['median_count'] = len(median_holes)

        # NMS 去重 + 噪声过滤
        nms_dist = max(8, int(min(h, w) * 0.008))
        merged = self._nms(all_holes, min_dist=nms_dist)
        filtered = self._filter_noise(merged, w)

        # ROI 坐标偏移还原
        if roi:
            for hole in filtered:
                hole['x'] += roi_offset[0]
                hole['y'] += roi_offset[1]

        self.debug_info.update(mode='单图自适应', sensitivity=self.sensitivity,
                               image_size=f'{w}x{h}', total_candidates=len(all_holes),
                               after_nms=len(merged), final=len(filtered))
        log.info("检测完成: 候选%d NMS%d 最终%d", len(all_holes), len(merged), len(filtered))
        return filtered

    # ═══ 暗点对比度检测 (PUBG 弹孔专用) ═══

    def _detect_dark_spots(self, gray, img_h, img_w):
        """弹孔 = 墙面上明显较暗的小斑点。
        原理: 用大半径高斯模糊估算局部背景亮度, 原图减去背景得到暗点图。
        """
        p = self._preset()
        short = min(img_h, img_w)

        # 1. 轻微降噪, 保留弹孔边缘
        denoised = cv2.GaussianBlur(gray, (3, 3), 0)

        # 2. 估算局部背景 (大核高斯)
        bg_k = max(51, int(short * 0.06) | 1)
        local_bg = cv2.GaussianBlur(gray, (bg_k, bg_k), 0)
        self.debug_images['dark_local_bg'] = local_bg.copy()

        # 3. 暗点图 = 背景 - 原图 (暗点为正值)
        diff = cv2.subtract(local_bg, denoised)
        self.debug_images['dark_diff'] = diff.copy()

        # 4. 自适应阈值: 暗点图中高于阈值的区域 = 弹孔候选
        sens_thresholds = {'high': 8, 'medium': 15, 'low': 25}
        dark_thresh = sens_thresholds.get(self.sensitivity, 15)
        _, binary = cv2.threshold(diff, dark_thresh, 255, cv2.THRESH_BINARY)

        # 形态学清理
        ks = max(3, int(short * 0.003)) | 1
        kernel = np.ones((ks, ks), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        self.debug_images['dark_binary'] = binary.copy()

        # 5. 找轮廓
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        px = img_h * img_w
        min_area = max(8, px * 3e-6)
        max_area = px * 5e-3
        min_circ = 0.15 if self.sensitivity == 'high' else 0.2

        holes = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (min_area < area < max_area):
                continue
            peri = cv2.arcLength(cnt, True)
            if peri == 0:
                continue
            circ = 4 * np.pi * area / (peri * peri)
            if circ < min_circ:
                continue

            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            # 验证中心确实是暗点 (与局部背景的亮度差)
            r = max(3, int(area ** 0.5 / 2))
            y1, y2 = max(0, cy - r), min(img_h, cy + r)
            x1, x2 = max(0, cx - r), min(img_w, cx + r)
            center_val = float(np.mean(gray[y1:y2, x1:x2]))
            bg_val = float(np.mean(local_bg[y1:y2, x1:x2]))
            darkness = bg_val - center_val
            if darkness < 5:
                continue

            holes.append({
                'x': cx, 'y': cy,
                'area': round(float(area), 1),
                'circularity': round(circ, 3),
                'color_diff': round(darkness, 1),
                'confidence': round(min(100, darkness * circ * 3), 1),
            })

        return holes

    # ═══ 策略2: 模板匹配 ═══

    def detect_with_template(self, image, template, threshold=0.55, roi=None):
        """模板匹配: 从弹痕图中裁一个弹孔 (约30x30px) 作为模板。

        模板要求:
          - 紧贴弹孔边缘裁剪, 包含弹孔+一圈背景
          - 建议 15~60px 正方形
          - 多尺度匹配, 不需要精确尺寸
        """
        self._reset()
        img = image
        roi_offset = (0, 0)
        if roi:
            x, y, rw, rh = roi
            img = image[y:y + rh, x:x + rw]
            roi_offset = (x, y)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()
        tmpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if template.ndim == 3 else template
        th, tw = tmpl.shape[:2]

        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray_e = clahe.apply(gray)
        tmpl_e = clahe.apply(tmpl)

        holes = []
        for scale in np.arange(0.5, 2.0, 0.1):
            st = cv2.resize(tmpl_e, None, fx=scale, fy=scale)
            if st.shape[0] >= gray_e.shape[0] or st.shape[1] >= gray_e.shape[1]:
                continue
            result = cv2.matchTemplate(gray_e, st, cv2.TM_CCOEFF_NORMED)
            locs = np.where(result >= threshold)
            for pt in zip(*locs[::-1]):
                cx = pt[0] + st.shape[1] // 2
                cy = pt[1] + st.shape[0] // 2
                holes.append({
                    'x': cx, 'y': cy,
                    'area': int(st.shape[0] * st.shape[1]),
                    'circularity': 1.0, 'color_diff': 50,
                    'confidence': float(result[pt[1], pt[0]]),
                })

        nms_dist = max(8, max(tw, th) // 2)
        merged = self._nms(holes, min_dist=nms_dist)
        filtered = self._filter_noise(merged, img.shape[1])

        if roi:
            for hole in filtered:
                hole['x'] += roi_offset[0]
                hole['y'] += roi_offset[1]

        self.debug_info.update(mode='模板匹配', total_candidates=len(holes),
                               after_nms=len(merged), final=len(filtered))
        return filtered

    # ═══ 策略3: 双图差分 ═══

    def detect(self, base, result):
        """双图差分: 空墙 vs 弹痕截图"""
        self._reset()
        if base.shape != result.shape:
            result = cv2.resize(result, (base.shape[1], base.shape[0]))
        bg = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
        rg = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        holes = self._diff_detect(bg, rg, base.shape[:2])
        self.debug_info.update(mode='双图差分', final=len(holes))
        return holes

    # ═══ SimpleBlobDetector 核心 ═══

    def _detect_blobs(self, gray, img_h, img_w):
        """SimpleBlobDetector: 专为深色圆形斑点设计。
        参数根据图片像素总数自适应缩放。
        """
        p = self._preset()
        px = img_h * img_w

        params = cv2.SimpleBlobDetector_Params()
        params.filterByColor = True
        params.blobColor = 0  # 深色斑点 (弹孔比墙面暗)
        params.filterByArea = True
        params.minArea = max(3, px * p['blob_min_area_ratio'])
        params.maxArea = max(50, px * p['blob_max_area_ratio'])
        params.filterByCircularity = True
        params.minCircularity = p['blob_min_circ']
        params.filterByConvexity = True
        params.minConvexity = p['blob_min_conv']
        params.filterByInertia = False
        params.minThreshold = p['blob_min_thresh']
        params.maxThreshold = p['blob_max_thresh']
        params.thresholdStep = p['blob_thresh_step']

        det = cv2.SimpleBlobDetector_create(params)
        keypoints = det.detect(gray)

        log.debug("  Blob params: minArea=%.0f maxArea=%.0f minCirc=%.2f",
                  params.minArea, params.maxArea, params.minCircularity)
        log.debug("  Blob keypoints: %d", len(keypoints))

        self.debug_info['blob_params'] = {
            'minArea': round(params.minArea), 'maxArea': round(params.maxArea),
            'minCirc': p['blob_min_circ'],
        }

        holes = []
        for kp in keypoints:
            holes.append({
                'x': int(kp.pt[0]), 'y': int(kp.pt[1]),
                'area': round(kp.size * kp.size * 0.785, 1),
                'circularity': 1.0, 'color_diff': 50,
                'confidence': float(kp.response) if kp.response else 50,
            })
        return holes

    # ═══ 多尺度中值差分 ═══

    def _detect_median_diff(self, gray, img_h, img_w):
        """多尺度中值滤波生成虚拟基线, 与原图差分检测弹孔。
        核大小根据图片短边按比例计算。
        """
        p = self._preset()
        short_side = min(img_h, img_w)
        all_holes = []

        for scale in p['median_kernels_scale']:
            ks = int(short_side * scale)
            ks = ks | 1  # 保证奇数
            ks = max(3, min(ks, 201))
            baseline = cv2.medianBlur(gray, ks)
            self.debug_images[f'median_k{ks}'] = baseline.copy()
            holes = self._diff_detect(baseline, gray, (img_h, img_w))
            log.debug("  median k=%d: %d holes", ks, len(holes))
            all_holes.extend(holes)

        return all_holes

    def _diff_detect(self, bg_gray, result_gray, shape):
        """差分 + 阈值 + 轮廓 检测核心流程"""
        p = self._preset()
        img_h, img_w = shape
        px = img_h * img_w

        diff = cv2.absdiff(bg_gray, result_gray)

        # OTSU 自动阈值, 异常时回退固定阈值
        otsu_val, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        white_ratio = np.sum(thresh > 0) / max(1, thresh.size)
        if white_ratio > 0.20 or white_ratio < 0.0001:
            fallback = max(6, int(otsu_val * 0.35)) if otsu_val > 15 else 8
            _, thresh = cv2.threshold(diff, fallback, 255, cv2.THRESH_BINARY)

        # 形态学: 核大小按图片缩放
        ks = max(3, int(min(img_h, img_w) * 0.003)) | 1
        k = np.ones((ks, ks), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k, iterations=2)
        thresh = cv2.dilate(thresh, k, iterations=1)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_a = max(3, px * self._preset()['blob_min_area_ratio'])
        max_a = px * self._preset()['blob_max_area_ratio']
        min_c = p['diff_min_circ']
        color_th = p['diff_color_thresh']

        holes = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (min_a < area < max_a):
                continue
            peri = cv2.arcLength(cnt, True)
            if peri == 0:
                continue
            circ = 4 * np.pi * area / (peri * peri)
            if circ < min_c:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
            mask = np.zeros(bg_gray.shape[:2], dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            cd = abs(cv2.mean(bg_gray, mask=mask)[0] - cv2.mean(result_gray, mask=mask)[0])
            if cd < color_th:
                continue
            holes.append({'x': cx, 'y': cy, 'area': round(float(area), 1),
                          'circularity': round(circ, 3), 'color_diff': round(cd, 1)})
        return holes

    # ═══ 去重与噪声过滤 ═══

    @staticmethod
    def _nms(holes, min_dist=12):
        if not holes:
            return []
        holes = sorted(holes, key=lambda h: h.get('confidence', h.get('color_diff', 0)), reverse=True)
        keep = []
        for h in holes:
            if not any(abs(h['x'] - k['x']) < min_dist and abs(h['y'] - k['y']) < min_dist for k in keep):
                keep.append(h)
        return keep

    def _filter_noise(self, holes, img_w):
        """噪声过滤: 弹痕应大致沿竖直线分布, 横向偏离太远的 = 噪声"""
        if len(holes) < 4:
            return holes
        max_dx = max(20, int(img_w * self._preset()['lateral_dev_ratio']))
        xs = [h['x'] for h in holes]
        median_x = float(np.median(xs))
        main = [h for h in holes if abs(h['x'] - median_x) <= max_dx]
        if len(main) < 3:
            best = []
            for h in holes:
                g = [h2 for h2 in holes if abs(h2['x'] - h['x']) <= max_dx]
                if len(g) > len(best):
                    best = g
            return best if len(best) >= 3 else holes
        return main

    def _reset(self):
        self.debug_info = {}
        self.debug_images = {}


# ═══════════════════════════════════════════
# 统一项目数据 (Phase 2)
# ═══════════════════════════════════════════

class ProjectData:
    """统一项目文件 (.calibration.json)

    一个文件包含全部状态: 弹孔坐标, 枪械配置, 对比结果, 修正参数。
    支持加载旧版 .analysis.json 格式。
    """
    VERSION = 3

    @staticmethod
    def save(path, holes, config, comparison=None, correction=None,
             image_path=None, image_size=None, iteration_round=1,
             parent_project=None):
        """保存项目文件

        :param config: dict 包含 gun_name, acc_code, scope_key, scope_val, pose_key, pose_val,
                       以及 muzzle_key, grip_key, stock_key (用于恢复combo)
        """
        data = {
            'version': ProjectData.VERSION,
            'image_path': str(image_path) if image_path else None,
            'image_size': list(image_size) if image_size else None,
            'holes': [{'x': h['x'], 'y': h['y'], 'shot_num': h.get('shot_num', 0),
                        'area': h.get('area', 100)} for h in holes],
            'config': config,
            'comparison': comparison,
            'correction': correction,
            'iteration_round': iteration_round,
            'parent_project': str(parent_project) if parent_project else None,
            'timestamp': datetime.now().isoformat(),
        }
        p = Path(path)
        if not p.suffix:
            p = p.with_suffix('.calibration.json')
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(p)

    @staticmethod
    def load(path):
        """加载项目文件, 返回 (data_dict, error_string)

        兼容:
          - v3 .calibration.json
          - v2 .analysis.json (旧格式)
          - ParameterCorrector 输出的 correction JSON
        """
        p = Path(path)
        if not p.exists():
            return None, f"文件不存在: {p}"
        try:
            with open(p, encoding='utf-8') as f:
                raw = json.load(f)
        except Exception as e:
            return None, f"JSON 解析失败: {e}"

        if raw.get('version') == ProjectData.VERSION:
            return raw, None

        # 兼容旧 .analysis.json
        if 'holes' in raw and 'version' in raw and raw['version'] < ProjectData.VERSION:
            meta = raw.get('metadata', {})
            return {
                'version': 2, 'holes': raw['holes'],
                'config': {
                    'gun_name': meta.get('gun', ''), 'acc_code': meta.get('acc', ''),
                    'scope_key': meta.get('scope_key', ''), 'scope_val': meta.get('scope', 1.0),
                    'pose_key': meta.get('pose_key', ''), 'pose_val': meta.get('posture', 1.0),
                },
                'comparison': None, 'correction': None, 'iteration_round': 1,
            }, None

        # 兼容 ParameterCorrector / IterativeCorrector 输出的 JSON
        corr_arr = raw.get('corrected_uniform') or raw.get('corrected_per_shot') or \
                   raw.get('corrected_optimal') or raw.get('corrected_params')
        if corr_arr:
            return {
                'version': 0, 'holes': [],
                'config': {
                    'gun_name': raw.get('gun_name', ''),
                    'acc_code': raw.get('acc_code', ''),
                },
                'correction': raw, 'comparison': None, 'iteration_round': 0,
            }, None

        return None, "无法识别的文件格式"

    @staticmethod
    def find_image(path):
        """查找项目关联的图片文件"""
        p = Path(path)
        stem = p.stem
        for suffix in ['.calibration', '.analysis']:
            stem = stem.replace(suffix, '')
        for ext in ['.png', '.jpg', '.bmp', '.jpeg']:
            img = p.parent / f"{stem}{ext}"
            if img.exists():
                return str(img)
        return None


# ═══════════════════════════════════════════
# 弹痕排序
# ═══════════════════════════════════════════

class BulletSorter:
    """弹孔排序器

    direction:
      'bottom_up' — 后坐力模式, Y值最大=第1发 (默认)
      'top_down'  — 反向模式, Y值最小=第1发
    start_shot: 起始发数编号
    """
    @staticmethod
    def sort(holes, direction='bottom_up', start_shot=1):
        if not holes:
            return holes
        reverse = (direction != 'top_down')
        sorted_h = sorted(holes, key=lambda h: h['y'], reverse=reverse)
        for i, h in enumerate(sorted_h):
            h['shot_num'] = start_shot + i
        return sorted_h


# ═══════════════════════════════════════════
# 理论数据对比 (Phase 6 修复)
# ═══════════════════════════════════════════

class BulletComparator:
    """对比实际弹孔间距 vs GunData 理论值

    核心公式 (来自 Process.FIRE):
      每个数组元素执行一次 mouse_R(0, round(posture * (value * scope)))
      间隔 9ms (全自动) 或 100ms (半自动)

    chunk_f 计算优先级:
      1. 射速优先: chunk_f = fire_interval_ms / tick_ms (最准确)
      2. 弹夹回退: chunk_f = effective_array_len / (mag - 1)
    """

    def __init__(self, gun_data_dir=None):
        self.gun_data_dir = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())

    def compare(self, holes, gun_name, acc_code, scope_val, posture_val):
        if len(holes) < 2:
            return None

        if not all('shot_num' in h for h in holes):
            BulletSorter.sort(holes)

        s = sorted(holes, key=lambda h: h['shot_num'])

        gun_data = self._load_gun_data(gun_name)
        if gun_data is None:
            return None

        raw = gun_data.get(acc_code, gun_data.get("A0B0C0", []))
        if not raw:
            return None

        is_semi = gun_name.lower() in _SEMI_AUTO_GUNS
        n_intervals = len(s) - 1

        if is_semi:
            chunk_f = 1.0
        else:
            fire_interval = _get_fire_interval(gun_name)
            if fire_interval and fire_interval > 0:
                chunk_f = fire_interval * 1000 / _TICK_MS
            else:
                effective_len = _trim_trailing_zeros(raw)
                mag_size = _get_gun_magazine(gun_name)
                if mag_size >= 2:
                    total_intervals = mag_size - 1
                else:
                    total_intervals = max(n_intervals, round(effective_len / 9.0))
                chunk_f = effective_len / max(1, total_intervals)

        n_compare = min(n_intervals, int(len(raw) / max(0.5, chunk_f)))

        # actual_dy: 相邻弹孔Y轴距离 (取绝对值, 兼容上→下/下→上两种方向)
        actual_dy = [abs(s[i - 1]['y'] - s[i]['y']) for i in range(1, len(s))]
        actual_dx = [s[i]['x'] - s[i - 1]['x'] for i in range(1, len(s))]

        # 理论值: 与压枪算法完全一致 — 每个 tick 执行 round(posture*(value*scope), 2)
        theory_chunks = []
        for i in range(n_compare):
            start = int(round(i * chunk_f))
            end = min(int(round((i + 1) * chunk_f)), len(raw))
            chunk_sum = sum(round(posture_val * (v * scope_val), 2) for v in raw[start:end])
            theory_chunks.append(round(chunk_sum, 2))

        details = []
        ratios = []
        for i in range(n_compare):
            act = actual_dy[i]
            raw_sum = theory_chunks[i]
            theo = raw_sum * scope_val * posture_val

            if theo > 0 and act > 0:
                ratio = act / theo
                ratios.append(ratio)
                status = '偏大' if ratio > 1.3 else '偏小' if ratio < 0.7 else '正常'
            elif act <= 0:
                ratio = None
                status = '异常(负间距)'
            else:
                ratio = None
                status = '理论=0'

            details.append({
                'shot': i + 1,
                'actual_dy': round(float(act), 2),
                'theory_dy': round(float(theo), 2),
                'raw_chunk_sum': round(float(raw_sum), 2),
                'ratio': round(float(ratio), 4) if ratio is not None else None,
                'x_drift': round(float(actual_dx[i]), 2) if i < len(actual_dx) else 0,
                'status': status,
            })

        if not ratios:
            return None

        # IQR 去除离群值后计算平均 ratio
        if len(ratios) >= 6:
            q1, q3 = np.percentile(ratios, [25, 75])
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            clean_ratios = [r for r in ratios if lo <= r <= hi]
            if len(clean_ratios) >= 3:
                avg_ratio = float(np.mean(clean_ratios))
            else:
                avg_ratio = float(np.mean(ratios))
        else:
            avg_ratio = float(np.mean(ratios))

        std_ratio = float(np.std(ratios))
        avg_dx = float(np.mean(actual_dx)) if actual_dx else 0.0
        max_dx = float(max(abs(d) for d in actual_dx)) if actual_dx else 0.0
        std_dx = float(np.std(actual_dx)) if len(actual_dx) > 1 else 0.0

        fire_interval = _get_fire_interval(gun_name)
        rpm = round(60 / fire_interval) if fire_interval else None

        chunk_int = max(1, int(round(chunk_f)))
        return {
            'gun': gun_name, 'accessories_code': acc_code,
            'scope_val': scope_val, 'posture_val': posture_val,
            'suggested_scope': round(scope_val * avg_ratio, 3),
            'avg_ratio': round(avg_ratio, 4), 'std_ratio': round(std_ratio, 4),
            'shot_count': len(s), 'valid_pairs': len(ratios),
            'chunk_size': chunk_int, 'chunk_size_f': round(chunk_f, 2),
            'is_semi_auto': is_semi,
            'fire_interval_ms': round(fire_interval * 1000, 2) if fire_interval else None,
            'rpm': rpm,
            'magazine_size': _get_gun_magazine(gun_name),
            'effective_array_len': _trim_trailing_zeros(raw) if not is_semi else len(raw),
            'avg_horizontal_drift': round(avg_dx, 2),
            'max_horizontal_drift': round(max_dx, 2),
            'std_horizontal_drift': round(std_dx, 2),
            'horizontal_drifts': [round(d, 2) for d in actual_dx],
            'details': details,
        }

    def _load_gun_data(self, gun_name):
        gp = self.gun_data_dir / f"{gun_name}.json"
        if not gp.exists():
            return None
        try:
            with open(gp, encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None


# ═══════════════════════════════════════════
# 可视化
# ═══════════════════════════════════════════

class BulletVisualizer:
    @staticmethod
    def draw_holes(img, holes):
        vis = img.copy()
        s = sorted(holes, key=lambda h: h.get('shot_num', 0))
        for i in range(len(s) - 1):
            dy = abs(s[i]['y'] - s[i + 1]['y'])
            dx = abs(s[i]['x'] - s[i + 1]['x'])
            color = (0, 0, 255) if (dy < 5 and dx < 5) else (0, 255, 255) if dy < 15 else (0, 255, 0)
            cv2.arrowedLine(vis, (s[i]['x'], s[i]['y']),
                            (s[i + 1]['x'], s[i + 1]['y']), color, 2, tipLength=0.15)
        for hv in s:
            n = hv.get('shot_num', 0)
            col = (0, 0, 255) if n <= 5 else (0, 165, 255) if n <= 15 else (0, 255, 0)
            cv2.circle(vis, (hv['x'], hv['y']), 10, col, 2)
            cv2.circle(vis, (hv['x'], hv['y']), 3, col, -1)
            cv2.putText(vis, str(n), (hv['x'] + 14, hv['y'] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return vis


# ═══════════════════════════════════════════
# 结果保存
# ═══════════════════════════════════════════

class ResultSaver:
    def __init__(self, save_dir="./calibration_results"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    def save_image(self, name, img):
        path = self.save_dir / f"{self.timestamp}_{name}.png"
        cv2.imwrite(str(path), img)
        return path


# ═══════════════════════════════════════════
# 修正参数
# ═══════════════════════════════════════════

class ParameterCorrector:
    """生成修正后的压枪参数"""

    def __init__(self, gun_data_dir=None):
        self.gun_data_dir = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())

    def correct(self, comparison_result, gun_name, acc_code, use_float=True):
        if not comparison_result:
            return None
        gp = self.gun_data_dir / f"{gun_name}.json"
        if not gp.exists():
            return None
        try:
            with open(gp, encoding='utf-8') as f:
                gun_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        original = gun_data.get(acc_code)
        fallback_code = acc_code
        if original is None:
            original = gun_data.get("A0B0C0", [])
            fallback_code = "A0B0C0"
        if not original:
            return None

        avg_ratio = comparison_result['avg_ratio']
        chunk_f = comparison_result.get('chunk_size_f',
                                        float(comparison_result.get('chunk_size', 12)))
        details = comparison_result.get('details', [])

        def _r(v):
            return round(v, 2) if use_float else round(v)

        corrected_uniform = [_r(v * avg_ratio) if v != 0 else 0 for v in original]

        per_shot = list(original)
        for i, d in enumerate(details):
            r = d.get('ratio')
            if r is None:
                continue
            start = int(round(i * chunk_f))
            end = min(int(round((i + 1) * chunk_f)), len(per_shot))
            for j in range(start, end):
                per_shot[j] = _r(original[j] * r) if original[j] != 0 else 0

        return {
            'gun_name': gun_name, 'acc_code': fallback_code, 'file_path': str(gp),
            'avg_ratio': round(avg_ratio, 4),
            'scope_val': comparison_result.get('scope_val', 1.0),
            'posture_val': comparison_result.get('posture_val', 1.0),
            'suggested_scope': comparison_result.get('suggested_scope', 1.0),
            'original_array': original,
            'corrected_uniform': corrected_uniform,
            'corrected_per_shot': per_shot,
            'chunk_size': max(1, int(round(chunk_f))),
            'chunk_size_f': round(chunk_f, 2),
        }

    @staticmethod
    def format_array_for_json(arr, items_per_line=36):
        lines = []
        for i in range(0, len(arr), items_per_line):
            c = arr[i:i + items_per_line]
            lines.append("        " + ", ".join(str(v) for v in c))
        return "[\n" + ",\n".join(lines) + "\n    ]"

    @staticmethod
    def generate_patch_json(correction_result, mode='uniform'):
        if not correction_result:
            return ""
        arr = correction_result.get('corrected_uniform') if mode == 'uniform' \
            else correction_result.get('corrected_per_shot', correction_result.get('corrected_uniform'))
        if not arr:
            return ""
        key = correction_result.get('acc_code', 'A0B0C0')
        return f'    "{key}": {ParameterCorrector.format_array_for_json(arr)}'


# ═══════════════════════════════════════════
# 迭代修正 (Phase 3 修复)
# ═══════════════════════════════════════════

class IterativeCorrector:
    """迭代修正: 宏开启后弹痕 + 上一轮参数 → 微调

    输出格式与 ParameterCorrector 对齐:
      corrected_uniform, acc_code, chunk_size 等字段一致,
      确保自己的输出可以被下一轮加载。
    """

    @staticmethod
    def correct(residual_holes, prev_correction, scope_val, posture_val):
        """
        :param prev_correction: 上轮修正结果 dict (包含 corrected_uniform, chunk_size, acc_code 等)
        :return: dict 格式与 ParameterCorrector 输出一致
        """
        prev_params = prev_correction.get('corrected_uniform') or \
                      prev_correction.get('corrected_per_shot') or \
                      prev_correction.get('corrected_optimal') or \
                      prev_correction.get('corrected_params')
        if not prev_params or len(residual_holes) < 2:
            return None

        prev_params = list(prev_params)
        chunk_f = prev_correction.get('chunk_size_f',
                                      float(prev_correction.get('chunk_size', 12)))
        acc_code = prev_correction.get('acc_code', 'A0B0C0')

        s = sorted(residual_holes, key=lambda h: h.get('shot_num', 0))
        n_intervals = len(s) - 1
        max_chunk = len(prev_params) / max(1, n_intervals)
        chunk_f = min(chunk_f, max_chunk)
        factor = max(0.01, scope_val * posture_val)

        corrected = [float(v) for v in prev_params]
        residuals = []

        for i in range(1, len(s)):
            dy = s[i]['y'] - s[i - 1]['y']
            dx = s[i]['x'] - s[i - 1]['x']
            adjustment_raw = -dy / factor

            start = int(round((i - 1) * chunk_f))
            end = min(int(round(i * chunk_f)), len(corrected))
            chunk_sum = sum(abs(prev_params[j]) for j in range(start, min(end, len(prev_params))))

            if chunk_sum > 0:
                for j in range(start, min(end, len(corrected))):
                    if prev_params[j] != 0:
                        corrected[j] = round(corrected[j] + adjustment_raw * abs(prev_params[j]) / chunk_sum, 2)
            elif end > start:
                per_tick = round(adjustment_raw / max(1, end - start), 2)
                for j in range(start, min(end, len(corrected))):
                    corrected[j] = round(corrected[j] + per_tick, 2)

            residuals.append({
                'shot': i, 'dy': round(float(dy), 2), 'dx': round(float(dx), 2),
                'adjustment_px': round(float(-dy), 2), 'adjustment_raw': round(float(adjustment_raw), 2),
            })

        chunk_int = max(1, int(round(chunk_f)))
        return {
            'gun_name': prev_correction.get('gun_name', ''),
            'acc_code': acc_code,
            'corrected_uniform': corrected,
            'original_array': prev_params,
            'avg_ratio': 1.0,
            'chunk_size': chunk_int,
            'chunk_size_f': round(chunk_f, 2),
            'scope_val': scope_val, 'posture_val': posture_val,
            'residuals': residuals,
            'avg_residual_dy': round(float(np.mean([r['dy'] for r in residuals])), 2),
            'max_residual_dy': round(float(max(abs(r['dy']) for r in residuals)), 2),
            'is_iterative': True,
        }


# ═══════════════════════════════════════════
# 多组比对 (Phase 4 修复)
# ═══════════════════════════════════════════

class MultiGroupAnalyzer:
    """多组弹痕交叉比对 — 验证同枪/同配件一致性"""

    def __init__(self):
        self.groups = []

    def add_group(self, comparison_result, label=""):
        if comparison_result:
            self.groups.append({
                'result': comparison_result,
                'label': label or f"第{len(self.groups) + 1}组",
            })

    def remove_group(self, index):
        if 0 <= index < len(self.groups):
            self.groups.pop(index)

    def clear(self):
        self.groups = []

    @property
    def count(self):
        return len(self.groups)

    def validate_consistency(self):
        """校验所有组是否为同一枪械/配件"""
        if self.count < 2:
            return True, ""
        guns = set(g['result'].get('gun', '') for g in self.groups)
        accs = set(g['result'].get('accessories_code', '') for g in self.groups)
        warnings = []
        if len(guns) > 1:
            warnings.append(f"枪械不一致: {guns}")
        if len(accs) > 1:
            warnings.append(f"配件不一致: {accs}")
        return not warnings, "; ".join(warnings)

    def analyze(self):
        if not self.groups:
            return None

        max_n = max(len(g['result']['details']) for g in self.groups)
        per_ratios = [[] for _ in range(max_n)]
        per_drifts = [[] for _ in range(max_n)]

        for g in self.groups:
            for i, d in enumerate(g['result']['details']):
                if d['ratio'] is not None:
                    per_ratios[i].append(d['ratio'])
            for i, dx in enumerate(g['result'].get('horizontal_drifts', [])):
                if i < max_n:
                    per_drifts[i].append(dx)

        stats = []
        for i in range(max_n):
            rs, ds = per_ratios[i], per_drifts[i]
            if not rs:
                stats.append(None)
                continue
            stats.append({
                'interval': i + 1, 'n_groups': len(rs),
                'avg_ratio': round(float(np.mean(rs)), 4),
                'std_ratio': round(float(np.std(rs)), 4),
                'avg_x_drift': round(float(np.mean(ds)), 1) if ds else 0,
            })

        all_ratios = [r for rs in per_ratios for r in rs]
        clean = all_ratios
        n_outliers = 0
        if len(all_ratios) >= 4:
            q1, q3 = np.percentile(all_ratios, [25, 75])
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            clean = [r for r in all_ratios if lo <= r <= hi]
            n_outliers = len(all_ratios) - len(clean)

        confidence = 'high' if self.count >= 3 and float(np.std(clean)) < 0.1 else \
                     'medium' if self.count >= 2 else 'low'

        return {
            'n_groups': self.count, 'interval_stats': stats,
            'overall_avg_ratio': round(float(np.mean(clean)), 4) if clean else 1.0,
            'overall_std_ratio': round(float(np.std(clean)), 4) if clean else 0.0,
            'n_outliers_removed': n_outliers, 'confidence': confidence,
            'group_labels': [g['label'] for g in self.groups],
            'group_ratios': [round(g['result']['avg_ratio'], 4) for g in self.groups],
        }

    def generate_optimal_correction(self, gun_name, acc_code, gun_data_dir=None):
        analysis = self.analyze()
        if not analysis:
            return None
        gd = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())
        gp = gd / f"{gun_name}.json"
        if not gp.exists():
            return None
        try:
            with open(gp, encoding='utf-8') as f:
                gdata = json.load(f)
        except Exception:
            return None
        original = gdata.get(acc_code, gdata.get("A0B0C0", []))
        if not original:
            return None

        chunk_f = self.groups[0]['result'].get('chunk_size_f',
                    float(self.groups[0]['result'].get('chunk_size', 12))) if self.groups else 12.0
        corrected = list(original)
        for i, stat in enumerate(analysis['interval_stats']):
            if stat is None:
                continue
            r = stat['avg_ratio']
            start = int(round(i * chunk_f))
            end = min(int(round((i + 1) * chunk_f)), len(corrected))
            for j in range(start, end):
                corrected[j] = round(original[j] * r, 2) if original[j] != 0 else 0

        chunk_int = max(1, int(round(chunk_f)))
        return {
            'gun_name': gun_name, 'acc_code': acc_code,
            'corrected_optimal': corrected, 'corrected_uniform': corrected,
            'original_array': original,
            'chunk_size': chunk_int, 'chunk_size_f': round(chunk_f, 2),
            'analysis': analysis,
        }


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def _cli_main():
    import argparse
    parser = argparse.ArgumentParser(description="PUBG 弹痕分析 CLI")
    parser.add_argument("result", help="弹痕截图路径")
    parser.add_argument("--template", default=None, help="弹孔模板小图 (可选)")
    parser.add_argument("--gun", default="m762")
    parser.add_argument("--acc", default="A0B0C0")
    parser.add_argument("--scope", type=float, default=None)
    parser.add_argument("--posture", type=float, default=1.0)
    parser.add_argument("--sensitivity", choices=['low', 'medium', 'high'], default='medium')
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="  [DEBUG] %(message)s")

    scope = args.scope or _load_sensitivity_config().get('none', 1.0)

    img = cv2.imread(args.result)
    if img is None:
        print(f"错误: 无法读取 {args.result}")
        return 1

    det = BulletDetector(args.sensitivity)
    if args.template:
        tmpl = cv2.imread(args.template)
        if tmpl is None:
            print(f"错误: 无法读取模板 {args.template}")
            return 1
        holes = det.detect_with_template(img, tmpl)
    else:
        holes = det.detect_single(img)

    if not holes:
        print("未检测到弹痕")
        return 1

    BulletSorter.sort(holes)
    print(f"检测到 {len(holes)} 个弹痕")

    comp = BulletComparator().compare(holes, args.gun, args.acc, scope, args.posture)
    if comp:
        for d in comp['details']:
            r = f"{d['ratio']:.3f}" if d['ratio'] else "N/A"
            print(f"  #{d['shot']} 实际{d['actual_dy']:.0f}px 理论{d['theory_dy']:.0f}px 比值{r}")
        print(f"  平均比值: {comp['avg_ratio']:.4f}")
        corr = ParameterCorrector().correct(comp, args.gun, args.acc)
        if corr:
            print(f"\n修正参数:\n{ParameterCorrector.generate_patch_json(corr)}")
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(_cli_main() or 0)
