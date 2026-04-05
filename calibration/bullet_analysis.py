#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 弹痕分析统一模块
═══════════════════════
提供弹痕检测、排序、对比、可视化的统一实现，供所有校准工具复用。

核心类:
  BulletDetector   - 基于图像差分检测弹痕
  BulletSorter     - 按开枪顺序排序（先打的在下面）
  BulletComparator - 与 GunData JSON 理论数据对比
  BulletVisualizer - 绘制标注图和间距柱状图
  ResultSaver      - 保存分析结果（图片+JSON）
"""

import cv2
import json
import time
import numpy as np
from pathlib import Path
from datetime import datetime


def _find_gun_data_dir():
    """智能查找 GunData 目录，兼容从项目根目录或子目录运行"""
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


# ═══════════════════════════════════════════
# 自适应检测参数
# ═══════════════════════════════════════════

_DEFAULT_PARAMS = {
    'min_area': 20,
    'max_area': 800,
    'min_circularity': 0.20,
    'color_threshold': 12,
    'morph_kernel': 5,
    'dilate_iterations': 1,
    'close_iterations': 2,
    'max_lateral_deviation': 50,
}


def _scale_params(resolution):
    """根据分辨率自动缩放检测参数"""
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
        """
        检测弹痕。
        :param base: 空白墙面截图 (BGR numpy array)
        :param result: 打完后的墙面截图 (BGR numpy array)
        :return: list[dict] 弹痕列表, 每个 {'x','y','area','circularity','color_diff'}
        """
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
        min_a = self.params['min_area']
        max_a = self.params['max_area']
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

        holes = self._filter_noise(holes)
        return holes

    def _filter_noise(self, holes):
        """
        过滤偏离主弹道线的噪点。
        算法: 按 X 坐标聚类，取最大组作为主弹道线。
        """
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
    shot_num=1 对应最下面的弹痕（第一发）。
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
# 理论数据对比
# ═══════════════════════════════════════════

class BulletComparator:
    """与 GunData JSON 弹道数据对比，计算校准系数"""

    def __init__(self, gun_data_dir=None):
        self.gun_data_dir = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())

    def compare(self, holes, gun_name, acc_code, scope_val, posture_val):
        """
        对比实际弹痕间距与理论弹道数据。

        :param holes: 已排好序的弹痕列表（含 shot_num）
        :param gun_name: 枪械名称（JSON文件名，不含扩展名）
        :param acc_code: 配件码，如 "A0B0C0"
        :param scope_val: 倍镜灵敏度系数
        :param posture_val: 姿态系数
        :return: dict 分析结果 或 None
        """
        if len(holes) < 2:
            return None

        s = sorted(holes, key=lambda h: h['shot_num'])

        gun_data = self._load_gun_data(gun_name)
        if gun_data is None:
            return None

        raw = gun_data.get(acc_code, gun_data.get("A0B0C0", []))
        if not raw:
            return None

        # shot_num=1 在最下面（Y最大），shot_num=2 在上面（Y较小）
        # 间距 = 前一发Y - 后一发Y = 正值
        actual_spacings = []
        for i in range(1, len(s)):
            dy = s[i - 1]['y'] - s[i]['y']
            actual_spacings.append(dy)

        # 从理论数据提取每发对应的值（偶数索引）
        n_pairs = min(len(actual_spacings), len(raw) // 2)
        if n_pairs == 0:
            return None

        theory_raw = [raw[j * 2] for j in range(n_pairs)]
        theory_spacings = [v * scope_val * posture_val for v in theory_raw]

        # 逐发配对对比，保持严格1:1对齐
        details = []
        ratios = []
        for i in range(n_pairs):
            actual = actual_spacings[i]
            theory = theory_spacings[i]

            if theory > 0 and actual > 0:
                ratio = actual / theory
                ratios.append(ratio)
                status = "⚠偏大" if ratio > 1.3 else "⚠偏小" if ratio < 0.7 else "✅正常"
            elif actual <= 0:
                ratio = None
                status = "⚠异常(负间距)"
            else:
                ratio = None
                status = "⚠理论值为0"

            details.append({
                'shot': i + 1,
                'actual_dy': round(float(actual), 1),
                'theory_dy': round(float(theory), 1),
                'ratio': round(float(ratio), 3) if ratio is not None else None,
                'status': status,
            })

        if not ratios:
            return None

        avg_ratio = float(np.mean(ratios))
        std_ratio = float(np.std(ratios))
        suggested_scope = round(scope_val * avg_ratio, 2)

        # 水平漂移分析
        dx_list = [s[i]['x'] - s[i - 1]['x'] for i in range(1, len(s))]
        avg_dx = float(np.mean(dx_list)) if dx_list else 0.0
        max_dx = float(max(abs(d) for d in dx_list)) if dx_list else 0.0

        return {
            'gun': gun_name,
            'accessories_code': acc_code,
            'scope_val': scope_val,
            'posture_val': posture_val,
            'suggested_scope': suggested_scope,
            'avg_ratio': round(avg_ratio, 3),
            'std_ratio': round(std_ratio, 3),
            'shot_count': len(s),
            'valid_pairs': len(ratios),
            'avg_horizontal_drift': round(avg_dx, 1),
            'max_horizontal_drift': round(max_dx, 1),
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
    """弹痕标注和图表绘制"""

    @staticmethod
    def draw_holes(img, holes):
        """在图像上绘制弹痕标注（编号、连线、统计信息）"""
        vis = img.copy()
        s = sorted(holes, key=lambda h: h['shot_num'])

        for i in range(len(s) - 1):
            dy = abs(s[i]['y'] - s[i + 1]['y'])
            dx = abs(s[i]['x'] - s[i + 1]['x'])
            if dy < 5 and dx < 5:
                color = (0, 0, 255)
            elif dy < 15:
                color = (0, 255, 255)
            else:
                color = (0, 255, 0)
            cv2.arrowedLine(vis,
                            (s[i]['x'], s[i]['y']),
                            (s[i + 1]['x'], s[i + 1]['y']),
                            color, 2, tipLength=0.15)

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
            stats = [
                f"Shots: {len(holes)}",
                f"Avg Y-spacing: {np.mean(spacings):.1f}px",
                f"Max: {max(spacings):.1f}px  Min: {min(spacings):.1f}px",
                f"Avg X-drift: {np.mean(dx_list):+.1f}px",
                f"Max X-drift: {max(abs(d) for d in dx_list):.1f}px",
            ]
            for text in stats:
                cv2.putText(vis, text, (10, y_pos),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
                y_pos += 28

        return vis

    @staticmethod
    def draw_spacing_chart(holes):
        """绘制垂直间距柱状图"""
        if len(holes) < 2:
            return None

        s = sorted(holes, key=lambda h: h['shot_num'])
        spacings = []
        for i in range(1, len(s)):
            dy = abs(s[i - 1]['y'] - s[i]['y'])
            spacings.append({'shot': i + 1, 'dy': dy})

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
            if d['dy'] < 2:
                color = (0, 0, 255)
            elif d['dy'] < 8:
                color = (0, 165, 255)
            elif d['dy'] > 20:
                color = (255, 100, 0)
            else:
                color = (0, 255, 0)
            cv2.rectangle(chart, (x, base_y + plot_h - bar_h),
                          (x + bar_w - 3, base_y + plot_h), color, -1)
            cv2.putText(chart, f"{d['dy']:.0f}",
                        (x + 3, base_y + plot_h - bar_h - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            cv2.putText(chart, str(d['shot']),
                        (x + bar_w // 2 - 5, H - 15),
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
        """绘制水平漂移图"""
        if len(holes) < 2:
            return None

        s = sorted(holes, key=lambda h: h['shot_num'])
        W, H = 1000, 300
        chart = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.putText(chart, "Horizontal Drift (px)", (W // 2 - 120, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

        dx_list = [s[i]['x'] - s[i - 1]['x'] for i in range(1, len(s))]
        if not dx_list:
            return None

        max_abs = max(abs(d) for d in dx_list) or 1
        bar_w = max(18, (W - 110) // len(dx_list))
        mid_y = H // 2 + 20
        plot_h = (H - 100) // 2

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
    """保存分析结果到磁盘"""

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
# 一站式分析 API
# ═══════════════════════════════════════════

def analyze_bullet_pattern(base_img, result_img, gun_name, acc_code,
                           scope_val=1.0, posture_val=1.0,
                           resolution="1920x1080",
                           save_results=True):
    """
    一站式弹痕分析入口。

    :param base_img: 空白墙面 BGR 图像
    :param result_img: 打完后 BGR 图像
    :param gun_name: 枪械名（JSON 文件名）
    :param acc_code: 配件码 "A#B#C#"
    :param scope_val: 倍镜灵敏度系数
    :param posture_val: 姿态系数
    :param resolution: 当前分辨率
    :param save_results: 是否保存结果到磁盘
    :return: dict with keys: holes, comparison, vis_path, chart_path
    """
    detector = BulletDetector(resolution)
    sorter = BulletSorter()
    comparator = BulletComparator()
    visualizer = BulletVisualizer()

    holes = detector.detect(base_img, result_img)
    if not holes:
        return {'holes': [], 'comparison': None, 'error': '未检测到弹痕'}

    sorted_holes = sorter.sort(holes)
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
# 修正参数生成
# ═══════════════════════════════════════════

class ParameterCorrector:
    """根据校准结果生成修正后的压枪参数"""

    def __init__(self, gun_data_dir=None):
        self.gun_data_dir = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())

    def correct(self, comparison_result, gun_name, acc_code):
        """
        生成修正后的弹道数组。

        原理:
          ratio = 实际间距 / 理论间距
          ratio > 1 → 实际后坐力 > 理论预测 → JSON值偏低 → 需要放大
          ratio < 1 → 实际后坐力 < 理论预测 → JSON值偏高 → 需要缩小
          corrected_value = original_value * avg_ratio

        :return: dict 包含原始和修正数组、元信息
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
        if original is None:
            original = gun_data.get("A0B0C0", [])
            acc_code = "A0B0C0"
        if not original:
            return None

        avg_ratio = comparison_result['avg_ratio']
        corrected = [round(v * avg_ratio) if v != 0 else 0 for v in original]

        # 逐发修正（如果有逐发 ratio）
        per_shot_corrected = None
        details = comparison_result.get('details', [])
        if details:
            per_shot_ratios = [d['ratio'] for d in details if d.get('ratio') is not None]
            if per_shot_ratios:
                per_shot_corrected = list(original)
                ticks_per_bullet = max(1, len(original) // max(1, comparison_result.get('shot_count', 10)))
                for i, d in enumerate(details):
                    r = d.get('ratio')
                    if r is None:
                        continue
                    start = i * ticks_per_bullet
                    end = min((i + 1) * ticks_per_bullet, len(per_shot_corrected))
                    for j in range(start, end):
                        v = per_shot_corrected[j]
                        per_shot_corrected[j] = round(v * r) if v != 0 else 0

        return {
            'gun_name': gun_name,
            'acc_code': acc_code,
            'file_path': str(gp),
            'avg_ratio': round(avg_ratio, 3),
            'scope_val': comparison_result.get('scope_val', 1.0),
            'suggested_scope': comparison_result.get('suggested_scope', 1.0),
            'original_array': original,
            'corrected_uniform': corrected,
            'corrected_per_shot': per_shot_corrected,
            'details': details,
        }

    @staticmethod
    def format_array_for_json(arr, items_per_line=36):
        """将数组格式化为可直接粘贴到 JSON 文件的字符串"""
        lines = []
        for i in range(0, len(arr), items_per_line):
            chunk = arr[i:i + items_per_line]
            lines.append("        " + ", ".join(str(v) for v in chunk))
        return "[\n" + ",\n".join(lines) + "\n    ]"

    @staticmethod
    def generate_patch_json(correction_result):
        """生成可直接替换的完整 JSON 片段"""
        if not correction_result:
            return ""
        arr = correction_result['corrected_uniform']
        key = correction_result['acc_code']
        formatted = ParameterCorrector.format_array_for_json(arr)
        return f'    "{key}": {formatted}'


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
    parser.add_argument("--scope", type=float, default=1.0, help="倍镜灵敏度系数（默认 1.0）")
    parser.add_argument("--posture", type=float, default=1.0, help="姿态系数（默认 1.0）")
    parser.add_argument("--resolution", default="1920x1080", help="分辨率（默认 1920x1080）")
    parser.add_argument("--no-save", action="store_true", help="不保存结果到磁盘")

    args = parser.parse_args()

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
    print(f"  倍镜系数: {args.scope}  姿态系数: {args.posture}")
    print(f"  分辨率: {args.resolution}")
    print(f"{'='*55}\n")

    r = analyze_bullet_pattern(
        base, result,
        gun_name=args.gun,
        acc_code=args.acc,
        scope_val=args.scope,
        posture_val=args.posture,
        resolution=args.resolution,
        save_results=not args.no_save,
    )

    if not r['holes']:
        print("  未检测到弹痕。请检查两张截图是否正确。")
        return 1

    print(f"  检测到 {r['shot_count']} 个弹痕\n")

    comp = r.get('comparison')
    if comp:
        print(f"  {'发数':>4} {'实际':>8} {'理论':>8} {'比值':>8} {'状态'}")
        print(f"  {'-'*48}")
        for d in comp['details']:
            ratio_str = f"{d['ratio']:.3f}" if d['ratio'] is not None else "  N/A"
            print(f"  {d['shot']:>4} {d['actual_dy']:>8.1f} {d['theory_dy']:>8.1f} {ratio_str:>8}  {d['status']}")
        print(f"  {'-'*48}")
        print(f"  平均比值: {comp['avg_ratio']:.3f}  标准差: {comp['std_ratio']:.3f}")
        print(f"  建议倍镜系数: {comp['suggested_scope']}")
        print(f"  水平漂移: 平均 {comp['avg_horizontal_drift']:+.1f}px  最大 {comp['max_horizontal_drift']:.1f}px")

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
