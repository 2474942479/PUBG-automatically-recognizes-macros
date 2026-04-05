#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 弹痕分析统一模块
═══════════════════════
核心类:
  BulletDetector      - 基于图像差分检测弹痕
  BulletSorter        - 按开枪顺序排序（先打的在下面）
  BulletComparator    - 与 GunData JSON 理论数据对比
  BulletVisualizer    - 绘制标注图和间距柱状图
  ResultSaver         - 保存分析结果（图片+JSON）
  ParameterCorrector  - 根据校准结果生成修正后的压枪参数
  MultiGroupAnalyzer  - 多组弹痕数据交叉比对
"""

import cv2
import json
import time
import numpy as np
from pathlib import Path
from datetime import datetime


def _find_gun_data_dir():
    """智能查找 GunData 目录"""
    candidates = [
        Path('./_internal/GunData'),
        Path('../_internal/GunData'),
        Path(__file__).resolve().parent.parent / '_internal' / 'GunData',
        Path(__file__).resolve().parent / '_internal' / 'GunData',
    ]
    for p in candidates:
        if p.is_dir():
            return str(p.resolve())
    return str(candidates[0])


def _load_sensitivity_config():
    """直接从配置文件读取灵敏度设置，不依赖 ProcessClass"""
    candidates = [
        Path('./Config/config.json'),
        Path('../Config/config.json'),
        Path(__file__).resolve().parent.parent / 'Config' / 'config.json',
    ]
    for p in candidates:
        if p.is_file():
            try:
                with open(p, encoding='utf-8') as f:
                    return json.load(f).get('sensitivity', {})
            except Exception:
                pass
    return {}


# FIRE1 (半自动枪械)：每个数组元素 = 一发子弹，tick间隔100ms
_SEMI_AUTO_GUNS = frozenset([
    "sks", "mini14", "delagongnuofu", "m16a4", "mk12", "mk47",
    "qbu", "zidongzhuangtianbuqiang",
])

# 全自动枪械：9ms/tick，每发子弹约10-15个tick
_AUTO_TICK_MS = 9


# ═══════════════════════════════════════════
# 自适应检测参数
# ═══════════════════════════════════════════

_DEFAULT_PARAMS = {
    'min_area': 20, 'max_area': 800,
    'min_circularity': 0.20, 'color_threshold': 12,
    'morph_kernel': 5, 'dilate_iterations': 1,
    'close_iterations': 2, 'max_lateral_deviation': 50,
}


def _scale_params(resolution):
    try:
        w, h = map(int, resolution.split('x'))
    except (ValueError, AttributeError):
        h = 1080
    scale = h / 1080.0
    area_scale = scale * scale
    return {
        'min_area': max(10, int(_DEFAULT_PARAMS['min_area'] * area_scale)),
        'max_area': int(_DEFAULT_PARAMS['max_area'] * area_scale),
        'min_circularity': _DEFAULT_PARAMS['min_circularity'],
        'color_threshold': _DEFAULT_PARAMS['color_threshold'],
        'morph_kernel': max(3, int(_DEFAULT_PARAMS['morph_kernel'] * scale)),
        'dilate_iterations': _DEFAULT_PARAMS['dilate_iterations'],
        'close_iterations': _DEFAULT_PARAMS['close_iterations'],
        'max_lateral_deviation': int(_DEFAULT_PARAMS['max_lateral_deviation'] * scale),
    }


# ═══════════════════════════════════════════
# 弹痕检测
# ═══════════════════════════════════════════

class BulletDetector:
    """基于前后帧差分检测弹痕位置"""

    def __init__(self, resolution="1920x1080"):
        self.params = _scale_params(resolution)

    def detect(self, base, result):
        if base.shape != result.shape:
            result = cv2.resize(result, (base.shape[1], base.shape[0]))

        bg = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
        rg = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(bg, rg)
        _, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        ks = self.params['morph_kernel']
        k = np.ones((ks, ks), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k,
                                  iterations=self.params['close_iterations'])
        thresh = cv2.dilate(thresh, k,
                            iterations=self.params['dilate_iterations'])

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        holes = []
        min_a, max_a = self.params['min_area'], self.params['max_area']
        min_c = self.params['min_circularity']
        color_th = self.params['color_threshold']

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (min_a < area < max_a):
                continue
            peri = cv2.arcLength(cnt, True)
            if peri == 0:
                continue
            circularity = 4 * np.pi * (area / (peri * peri))
            if circularity < min_c:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            mask = np.zeros(bg.shape[:2], dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            color_diff = abs(cv2.mean(bg, mask=mask)[0] - cv2.mean(rg, mask=mask)[0])
            if color_diff < color_th:
                continue

            holes.append({
                'x': cx, 'y': cy, 'area': area,
                'circularity': round(circularity, 3),
                'color_diff': round(color_diff, 1),
            })

        return self._filter_noise(holes)

    def _filter_noise(self, holes):
        if len(holes) < 4:
            return holes
        max_dx = self.params['max_lateral_deviation']
        xs = [h['x'] for h in holes]
        median_x = float(np.median(xs))
        main_group = [h for h in holes if abs(h['x'] - median_x) <= max_dx]
        if len(main_group) < 3:
            best_group = []
            for h in holes:
                group = [h2 for h2 in holes if abs(h2['x'] - h['x']) <= max_dx]
                if len(group) > len(best_group):
                    best_group = group
            return best_group if len(best_group) >= 3 else holes
        return main_group


# ═══════════════════════════════════════════
# 弹痕排序
# ═══════════════════════════════════════════

class BulletSorter:
    """
    按开枪顺序排序弹痕。
    PUBG 后坐力使子弹向上飞，先打的弹痕在下面（Y值大），后打的在上面（Y值小）。
    """

    @staticmethod
    def sort(holes):
        if not holes:
            return holes
        sorted_holes = sorted(holes, key=lambda h: h['y'], reverse=True)
        for i, h in enumerate(sorted_holes):
            h['shot_num'] = i + 1
        return sorted_holes


# ═══════════════════════════════════════════
# 理论数据对比（核心修复）
# ═══════════════════════════════════════════

class BulletComparator:
    """与 GunData JSON 弹道数据对比，计算校准系数。

    数据格式说明:
      Process.FIRE() 对弹道数组逐元素执行 mouse_R(0, posture*(val*scope))，
      间隔 9ms/tick。每发子弹约占 10-15 个 tick。
      因此每发子弹的理论补偿 = sum(chunk_values) * scope * posture (像素)。
      实际弹孔间距(像素) 与之对比可得校准比值。
    """

    def __init__(self, gun_data_dir=None):
        self.gun_data_dir = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())

    def compare(self, holes, gun_name, acc_code, scope_val, posture_val):
        if len(holes) < 2:
            return None

        s = sorted(holes, key=lambda h: h['shot_num'])

        gun_data = self._load_gun_data(gun_name)
        if gun_data is None:
            return None

        raw = gun_data.get(acc_code, gun_data.get("A0B0C0", []))
        if not raw:
            return None

        is_semi = gun_name.lower() in _SEMI_AUTO_GUNS
        chunk = self._estimate_chunk_size(raw, is_semi)

        n_intervals = len(s) - 1
        max_intervals = max(1, len(raw) // max(1, chunk))
        n_compare = min(n_intervals, max_intervals)

        # 实际间距: shot_num=1 在最下面(Y最大), 间距 = 前一发Y - 后一发Y
        actual_spacings = [s[i - 1]['y'] - s[i]['y'] for i in range(1, len(s))]
        actual_dx = [s[i]['x'] - s[i - 1]['x'] for i in range(1, len(s))]

        # 理论间距: 每个chunk的值求和 * scope * posture
        theory_chunks = []
        for i in range(n_compare):
            start = i * chunk
            end = min(start + chunk, len(raw))
            chunk_sum = sum(raw[start:end])
            theory_chunks.append(chunk_sum)

        details = []
        ratios = []
        for i in range(n_compare):
            actual = actual_spacings[i]
            raw_sum = theory_chunks[i]
            theory = raw_sum * scope_val * posture_val

            if theory > 0 and actual > 0:
                ratio = actual / theory
                ratios.append(ratio)
                status = "⚠偏大" if ratio > 1.3 else "⚠偏小" if ratio < 0.7 else "✅正常"
            elif actual <= 0:
                ratio = None
                status = "⚠异常(负间距)"
            else:
                ratio = None
                status = "⚠理论=0"

            details.append({
                'shot': i + 1,
                'actual_dy': round(float(actual), 1),
                'theory_dy': round(float(theory), 1),
                'raw_chunk_sum': round(float(raw_sum), 1),
                'ratio': round(float(ratio), 4) if ratio is not None else None,
                'x_drift': round(float(actual_dx[i]), 1) if i < len(actual_dx) else 0,
                'status': status,
            })

        if not ratios:
            return None

        avg_ratio = float(np.mean(ratios))
        std_ratio = float(np.std(ratios))
        suggested_scope = round(scope_val * avg_ratio, 3)

        # 水平漂移统计
        avg_dx = float(np.mean(actual_dx)) if actual_dx else 0.0
        max_dx = float(max(abs(d) for d in actual_dx)) if actual_dx else 0.0
        std_dx = float(np.std(actual_dx)) if len(actual_dx) > 1 else 0.0

        return {
            'gun': gun_name,
            'accessories_code': acc_code,
            'scope_val': scope_val,
            'posture_val': posture_val,
            'suggested_scope': suggested_scope,
            'avg_ratio': round(avg_ratio, 4),
            'std_ratio': round(std_ratio, 4),
            'shot_count': len(s),
            'valid_pairs': len(ratios),
            'chunk_size': chunk,
            'is_semi_auto': is_semi,
            'avg_horizontal_drift': round(avg_dx, 1),
            'max_horizontal_drift': round(max_dx, 1),
            'std_horizontal_drift': round(std_dx, 1),
            'horizontal_drifts': [round(d, 1) for d in actual_dx],
            'details': details,
        }

    @staticmethod
    def _estimate_chunk_size(raw, is_semi):
        """估算每发子弹对应的数组元素数量"""
        if is_semi:
            return 1
        # 全自动: 9ms/tick, 典型射速600-900RPM → 67-100ms/发 → 7-11 ticks
        # 用12作为默认值，适合大多数步枪(~600RPM)
        n = len(raw)
        if n <= 15:
            return max(1, n)
        estimated_intervals = max(1, round(n / 12))
        return max(3, n // estimated_intervals)

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
    """弹痕标注和图表绘制"""

    @staticmethod
    def draw_holes(img, holes):
        vis = img.copy()
        s = sorted(holes, key=lambda h: h['shot_num'])

        for i in range(len(s) - 1):
            dy = abs(s[i]['y'] - s[i + 1]['y'])
            dx = abs(s[i]['x'] - s[i + 1]['x'])
            color = (0, 0, 255) if (dy < 5 and dx < 5) else (0, 255, 255) if dy < 15 else (0, 255, 0)
            cv2.arrowedLine(vis, (s[i]['x'], s[i]['y']),
                            (s[i + 1]['x'], s[i + 1]['y']), color, 2, tipLength=0.15)

        for hv in s:
            n = hv['shot_num']
            col = (0, 0, 255) if n <= 5 else (0, 165, 255) if n <= 15 else (0, 255, 0)
            cv2.circle(vis, (hv['x'], hv['y']), 10, col, 2)
            cv2.circle(vis, (hv['x'], hv['y']), 3, col, -1)
            cv2.putText(vis, str(n), (hv['x'] + 14, hv['y'] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        if len(s) >= 2:
            spacings = [abs(s[i - 1]['y'] - s[i]['y']) for i in range(1, len(s))]
            dx_list = [s[i]['x'] - s[i - 1]['x'] for i in range(1, len(s))]
            y_pos = 35
            for text in [
                f"Shots: {len(holes)}",
                f"Avg Y-spacing: {np.mean(spacings):.1f}px",
                f"Max: {max(spacings):.1f}px  Min: {min(spacings):.1f}px",
                f"Avg X-drift: {np.mean(dx_list):+.1f}px",
                f"Max X-drift: {max(abs(d) for d in dx_list):.1f}px",
            ]:
                cv2.putText(vis, text, (10, y_pos),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
                y_pos += 28

        return vis

    @staticmethod
    def draw_spacing_chart(holes):
        if len(holes) < 2:
            return None
        s = sorted(holes, key=lambda h: h['shot_num'])
        spacings = [{'shot': i + 1, 'dy': abs(s[i - 1]['y'] - s[i]['y'])} for i in range(1, len(s))]

        W, H = 1000, 450
        chart = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.putText(chart, "Vertical Spacing (px)", (W // 2 - 120, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        max_dy = max(d['dy'] for d in spacings) or 1
        bar_w = max(18, (W - 110) // len(spacings))
        plot_h, base_y = H - 140, 70

        for i, d in enumerate(spacings):
            x = 90 + i * bar_w
            bar_h = int(d['dy'] / max_dy * plot_h)
            color = (0, 0, 255) if d['dy'] < 2 else (0, 165, 255) if d['dy'] < 8 else \
                (255, 100, 0) if d['dy'] > 20 else (0, 255, 0)
            cv2.rectangle(chart, (x, base_y + plot_h - bar_h),
                          (x + bar_w - 3, base_y + plot_h), color, -1)
            cv2.putText(chart, f"{d['dy']:.0f}", (x + 3, base_y + plot_h - bar_h - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            cv2.putText(chart, str(d['shot']), (x + bar_w // 2 - 5, H - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        cv2.line(chart, (82, 60), (82, base_y + plot_h + 5), (100, 100, 100), 1)
        step = max(1, int(max_dy / 8))
        for px in range(0, int(max_dy) + step, step):
            yy = base_y + plot_h - int(px / max_dy * plot_h)
            cv2.line(chart, (75, yy), (82, yy), (100, 100, 100), 1)
            cv2.putText(chart, f"{px}", (45, yy + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1)

        return chart

    @staticmethod
    def draw_drift_chart(holes):
        if len(holes) < 2:
            return None
        s = sorted(holes, key=lambda h: h['shot_num'])
        dx_list = [s[i]['x'] - s[i - 1]['x'] for i in range(1, len(s))]
        if not dx_list:
            return None

        W, H = 1000, 300
        chart = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.putText(chart, "Horizontal Drift (px)", (W // 2 - 120, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

        max_abs = max(abs(d) for d in dx_list) or 1
        bar_w = max(18, (W - 110) // len(dx_list))
        mid_y, plot_h = H // 2 + 20, (H - 100) // 2

        cv2.line(chart, (85, mid_y), (W - 10, mid_y), (80, 80, 80), 1)

        for i, dx in enumerate(dx_list):
            x = 90 + i * bar_w
            bar_h = int(abs(dx) / max_abs * plot_h)
            color = (0, 200, 255) if dx >= 0 else (255, 100, 100)
            if dx >= 0:
                cv2.rectangle(chart, (x, mid_y - bar_h), (x + bar_w - 3, mid_y), color, -1)
                cv2.putText(chart, f"{dx:+.0f}", (x, mid_y - bar_h - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
            else:
                cv2.rectangle(chart, (x, mid_y), (x + bar_w - 3, mid_y + bar_h), color, -1)
                cv2.putText(chart, f"{dx:+.0f}", (x, mid_y + bar_h + 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
            cv2.putText(chart, str(i + 2), (x + bar_w // 2 - 5, H - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

        return chart


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

    def save_json(self, name, data):
        path = self.save_dir / f"{self.timestamp}_{name}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path


# ═══════════════════════════════════════════
# 修正参数生成（支持小数）
# ═══════════════════════════════════════════

class ParameterCorrector:
    """根据校准结果生成修正后的压枪参数，支持小数精度"""

    def __init__(self, gun_data_dir=None):
        self.gun_data_dir = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())

    def correct(self, comparison_result, gun_name, acc_code, use_float=True):
        """
        生成修正后的弹道数组。

        :param use_float: True=保留1位小数精度, False=取整(兼容旧逻辑)
        """
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
        chunk = comparison_result.get('chunk_size', 12)
        details = comparison_result.get('details', [])

        def _round(v):
            return round(v, 1) if use_float else round(v)

        # 方案一：均匀修正（所有值乘以相同比率）
        corrected_uniform = [_round(v * avg_ratio) if v != 0 else 0 for v in original]

        # 方案二：逐发修正（每个chunk用对应的ratio）
        per_shot = list(original)
        for i, d in enumerate(details):
            r = d.get('ratio')
            if r is None:
                continue
            start = i * chunk
            end = min((i + 1) * chunk, len(per_shot))
            for j in range(start, end):
                per_shot[j] = _round(original[j] * r) if original[j] != 0 else 0

        # 水平漂移补偿建议
        x_comp = self._calc_x_compensation(comparison_result, chunk, original)

        return {
            'gun_name': gun_name,
            'acc_code': fallback_code,
            'file_path': str(gp),
            'avg_ratio': round(avg_ratio, 4),
            'scope_val': comparison_result.get('scope_val', 1.0),
            'posture_val': comparison_result.get('posture_val', 1.0),
            'suggested_scope': comparison_result.get('suggested_scope', 1.0),
            'original_array': original,
            'corrected_uniform': corrected_uniform,
            'corrected_per_shot': per_shot,
            'x_compensation': x_comp,
            'details': details,
            'chunk_size': chunk,
        }

    @staticmethod
    def _calc_x_compensation(comp, chunk, original):
        """根据水平漂移数据计算X轴补偿建议"""
        drifts = comp.get('horizontal_drifts', [])
        if not drifts:
            return None

        avg_dx = comp.get('avg_horizontal_drift', 0)
        std_dx = comp.get('std_horizontal_drift', 0)

        # 标准差 > 均值绝对值 → 随机性太强，不建议固定补偿
        if std_dx > abs(avg_dx) * 1.5 and abs(avg_dx) < 3:
            return {'type': 'random', 'avg': avg_dx, 'std': std_dx,
                    'suggestion': '水平漂移随机性强，不建议固定X补偿'}

        scope = comp.get('scope_val', 1.0)
        posture = comp.get('posture_val', 1.0)
        factor = max(0.01, scope * posture)

        # 生成每个chunk的X补偿值
        x_per_chunk = []
        for i, dx in enumerate(drifts):
            # dx > 0 表示弹道向右偏 → 需要向左补偿(负X移动)
            x_raw = round(-dx / factor / max(1, chunk), 1)
            x_per_chunk.append(x_raw)

        return {
            'type': 'compensatable',
            'avg': avg_dx,
            'std': std_dx,
            'x_per_chunk': x_per_chunk,
            'suggestion': f'平均水平偏移 {avg_dx:+.1f}px，可添加X轴补偿',
        }

    @staticmethod
    def format_array_for_json(arr, items_per_line=36):
        lines = []
        for i in range(0, len(arr), items_per_line):
            chunk = arr[i:i + items_per_line]
            lines.append("        " + ", ".join(str(v) for v in chunk))
        return "[\n" + ",\n".join(lines) + "\n    ]"

    @staticmethod
    def generate_patch_json(correction_result, mode='uniform'):
        """mode: 'uniform' (均匀修正) 或 'per_shot' (逐发修正)"""
        if not correction_result:
            return ""
        arr = correction_result['corrected_uniform'] if mode == 'uniform' \
            else correction_result['corrected_per_shot']
        key = correction_result['acc_code']
        formatted = ParameterCorrector.format_array_for_json(arr)
        return f'    "{key}": {formatted}'


# ═══════════════════════════════════════════
# 多组交叉比对
# ═══════════════════════════════════════════

class MultiGroupAnalyzer:
    """多组弹痕数据的交叉比对分析，取最优参数"""

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

    def analyze(self):
        if not self.groups:
            return None

        max_intervals = max(len(g['result']['details']) for g in self.groups)
        per_interval_ratios = [[] for _ in range(max_intervals)]
        per_interval_drifts = [[] for _ in range(max_intervals)]

        for g in self.groups:
            for i, d in enumerate(g['result']['details']):
                if d['ratio'] is not None:
                    per_interval_ratios[i].append(d['ratio'])
            for i, dx in enumerate(g['result'].get('horizontal_drifts', [])):
                if i < max_intervals:
                    per_interval_drifts[i].append(dx)

        interval_stats = []
        for i in range(max_intervals):
            rs = per_interval_ratios[i]
            ds = per_interval_drifts[i]
            if not rs:
                interval_stats.append(None)
                continue
            interval_stats.append({
                'interval': i + 1,
                'n_groups': len(rs),
                'avg_ratio': round(float(np.mean(rs)), 4),
                'std_ratio': round(float(np.std(rs)), 4),
                'min_ratio': round(float(min(rs)), 4),
                'max_ratio': round(float(max(rs)), 4),
                'avg_x_drift': round(float(np.mean(ds)), 1) if ds else 0,
                'std_x_drift': round(float(np.std(ds)), 1) if len(ds) > 1 else 0,
            })

        all_ratios = [r for rs in per_interval_ratios for r in rs]
        all_drifts = [d for ds in per_interval_drifts for d in ds]

        # IQR 去除离群值
        clean_ratios = all_ratios
        n_outliers = 0
        if len(all_ratios) >= 4:
            q1, q3 = np.percentile(all_ratios, [25, 75])
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            clean_ratios = [r for r in all_ratios if lower <= r <= upper]
            n_outliers = len(all_ratios) - len(clean_ratios)

        if len(self.groups) >= 3 and float(np.std(clean_ratios)) < 0.1:
            confidence = 'high'
        elif len(self.groups) >= 2:
            confidence = 'medium'
        else:
            confidence = 'low'

        return {
            'n_groups': len(self.groups),
            'interval_stats': interval_stats,
            'overall_avg_ratio': round(float(np.mean(clean_ratios)), 4) if clean_ratios else 1.0,
            'overall_std_ratio': round(float(np.std(clean_ratios)), 4) if clean_ratios else 0.0,
            'overall_avg_x_drift': round(float(np.mean(all_drifts)), 1) if all_drifts else 0,
            'overall_std_x_drift': round(float(np.std(all_drifts)), 1) if len(all_drifts) > 1 else 0,
            'n_outliers_removed': n_outliers,
            'confidence': confidence,
            'group_labels': [g['label'] for g in self.groups],
            'group_ratios': [round(g['result']['avg_ratio'], 4) for g in self.groups],
        }

    def generate_optimal_correction(self, gun_name, acc_code, gun_data_dir=None):
        """基于多组数据生成最优修正参数"""
        analysis = self.analyze()
        if not analysis:
            return None

        gd = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())
        gp = gd / f"{gun_name}.json"
        if not gp.exists():
            return None
        try:
            with open(gp, encoding='utf-8') as f:
                gun_data = json.load(f)
        except Exception:
            return None

        original = gun_data.get(acc_code, gun_data.get("A0B0C0", []))
        if not original:
            return None

        # 使用逐发最优比率修正
        chunk = self.groups[0]['result'].get('chunk_size', 12) if self.groups else 12
        corrected = list(original)

        for i, stat in enumerate(analysis['interval_stats']):
            if stat is None:
                continue
            r = stat['avg_ratio']
            start = i * chunk
            end = min((i + 1) * chunk, len(corrected))
            for j in range(start, end):
                corrected[j] = round(original[j] * r, 1) if original[j] != 0 else 0

        return {
            'gun_name': gun_name,
            'acc_code': acc_code,
            'corrected_optimal': corrected,
            'original_array': original,
            'analysis': analysis,
        }


# ═══════════════════════════════════════════
# 一站式分析 API
# ═══════════════════════════════════════════

def analyze_bullet_pattern(base_img, result_img, gun_name, acc_code,
                           scope_val=1.0, posture_val=1.0,
                           resolution="1920x1080", save_results=True):
    detector = BulletDetector(resolution)
    comparator = BulletComparator()
    visualizer = BulletVisualizer()

    holes = detector.detect(base_img, result_img)
    if not holes:
        return {'holes': [], 'comparison': None, 'error': '未检测到弹痕'}

    sorted_holes = BulletSorter.sort(holes)
    comparison = comparator.compare(sorted_holes, gun_name, acc_code, scope_val, posture_val)

    result = {
        'holes': sorted_holes,
        'comparison': comparison,
        'shot_count': len(sorted_holes),
    }

    vis = visualizer.draw_holes(result_img, sorted_holes)
    chart = visualizer.draw_spacing_chart(sorted_holes)
    drift_chart = visualizer.draw_drift_chart(sorted_holes)

    if save_results:
        saver = ResultSaver()
        result['vis_path'] = str(saver.save_image("bullet_holes_marked", vis))
        if chart is not None:
            result['chart_path'] = str(saver.save_image("spacing_chart", chart))
        if drift_chart is not None:
            result['drift_chart_path'] = str(saver.save_image("drift_chart", drift_chart))
        if comparison:
            saver.save_json("calibration_result", comparison)

    result['vis_image'] = vis
    result['chart_image'] = chart
    result['drift_chart_image'] = drift_chart

    return result


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

def _cli_main():
    import argparse

    parser = argparse.ArgumentParser(
        description="PUBG 弹痕分析工具 — 对比基线与结果截图，输出校准参数",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("base", help="空白墙面截图路径")
    parser.add_argument("result", help="打完后的墙面截图路径")
    parser.add_argument("--gun", default="m762", help="枪械名（JSON 文件名，默认 m762）")
    parser.add_argument("--acc", default="A0B0C0", help="配件码（默认 A0B0C0）")
    parser.add_argument("--scope", type=float, default=None,
                        help="倍镜灵敏度系数（默认从config.json读取）")
    parser.add_argument("--posture", type=float, default=1.0, help="姿态系数（默认 1.0）")
    parser.add_argument("--resolution", default="1920x1080", help="分辨率")
    parser.add_argument("--no-save", action="store_true", help="不保存结果到磁盘")

    args = parser.parse_args()

    # 自动从config读取scope
    scope = args.scope
    if scope is None:
        cfg = _load_sensitivity_config()
        scope = cfg.get('none', 1.0)

    base = cv2.imread(args.base)
    result = cv2.imread(args.result)
    if base is None:
        print(f"错误: 无法读取基线图 {args.base}")
        return 1
    if result is None:
        print(f"错误: 无法读取结果图 {args.result}")
        return 1

    print(f"\n{'='*55}")
    print(f"  PUBG 弹痕分析")
    print(f"{'='*55}")
    print(f"  枪械: {args.gun}  配件码: {args.acc}")
    print(f"  倍镜系数: {scope}  姿态系数: {args.posture}")
    print(f"{'='*55}\n")

    r = analyze_bullet_pattern(
        base, result,
        gun_name=args.gun, acc_code=args.acc,
        scope_val=scope, posture_val=args.posture,
        resolution=args.resolution, save_results=not args.no_save,
    )

    if not r['holes']:
        print("  未检测到弹痕。请检查两张截图是否正确。")
        return 1

    print(f"  检测到 {r['shot_count']} 个弹痕\n")

    comp = r.get('comparison')
    if comp:
        print(f"  {'发数':>4} {'实际px':>8} {'理论px':>8} {'原值':>6} {'比值':>8} {'X漂':>6} {'状态'}")
        print(f"  {'-'*58}")
        for d in comp['details']:
            ratio_str = f"{d['ratio']:.4f}" if d['ratio'] is not None else "  N/A"
            print(f"  {d['shot']:>4} {d['actual_dy']:>8.1f} {d['theory_dy']:>8.1f} "
                  f"{d['raw_chunk_sum']:>6.1f} {ratio_str:>8}  {d['x_drift']:>+5.0f} {d['status']}")
        print(f"  {'-'*58}")
        print(f"  平均比值: {comp['avg_ratio']:.4f}  标准差: {comp['std_ratio']:.4f}")
        print(f"  建议倍镜系数: {comp['suggested_scope']}")
        print(f"  水平漂移: 均值{comp['avg_horizontal_drift']:+.1f} "
              f"标准差{comp['std_horizontal_drift']:.1f} "
              f"最大{comp['max_horizontal_drift']:.1f}px")

        corrector = ParameterCorrector()
        correction = corrector.correct(comp, args.gun, args.acc)
        if correction:
            print(f"\n  修正后弹道数据 ({args.acc}):")
            patch = corrector.generate_patch_json(correction)
            print(patch)
    else:
        print("  无理论数据可供对比")

    if not args.no_save:
        print(f"\n  结果已保存到 calibration_results/")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(_cli_main() or 0)
