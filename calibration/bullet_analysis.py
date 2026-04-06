#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 弹痕分析统一模块
═══════════════════════
核心类:
  BulletDetector      - 弹痕检测 (单图自适应 / 模板匹配 / 双图差分)
  BulletSorter        - 按开枪顺序排序（先打的在下面）
  BulletComparator    - 与 GunData JSON 理论数据对比
  BulletVisualizer    - 绘制标注图和间距柱状图
  ResultSaver         - 保存分析结果（图片+JSON）
  AnnotationData      - 标注数据持久化 (JSON sidecar)
  ParameterCorrector  - 根据校准结果生成修正后的压枪参数
  IterativeCorrector  - 迭代修正（宏开启后弹痕→微调参数）
  MultiGroupAnalyzer  - 多组弹痕数据交叉比对
"""

import cv2
import json
import time
import logging
import numpy as np
from pathlib import Path
from datetime import datetime

# ── 日志配置 ──
# 使用方法: 在外部设置 logging.basicConfig(level=logging.DEBUG) 即可看到检测细节
log = logging.getLogger("bullet_analysis")


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _find_gun_data_dir():
    """从多个候选路径中查找 GunData 目录。
    优先级: 当前目录 > 上一级 > 脚本同级 > 脚本上一级
    """
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
    """从 Config/config.json 读取灵敏度配置，不依赖 ProcessClass"""
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


# ── 枪械分类常量 ──

# 半自动枪械列表 (FIRE1模式): 每个数组元素 = 一发子弹
_SEMI_AUTO_GUNS = frozenset([
    "sks", "mini14", "delagongnuofu", "m16a4", "mk12", "mk47",
    "qbu", "zidongzhuangtianbuqiang",
])

# 全自动枪械的tick间隔(ms)
_AUTO_TICK_MS = 9


# ═══════════════════════════════════════════
# 检测灵敏度预设
# ═══════════════════════════════════════════
#
# 为什么需要灵敏度预设？
# ───────────────────
# PUBG 弹痕在截图中的表现差异很大:
#   - 墙面颜色/纹理影响对比度
#   - 截图分辨率影响弹痕像素大小
#   - 远距离射击时弹痕更小
#   - JPEG压缩会模糊边缘
#
# 三档灵敏度从"宽松"到"严格":
#   高敏: 尽可能多检测，可能有假阳性（建议搭配手工修正）
#   标准: 平衡精度和召回率
#   低敏: 只保留最确定的弹痕，漏检多但误检少

_SENSITIVITY_PRESETS = {
    'high': {
        'min_area': 3,            # 极小弹痕也检测（远距离/小分辨率）
        'max_area': 3000,
        'min_circularity': 0.08,  # 几乎不限制形状
        'color_threshold': 2,     # 极低对比度也检测
        'morph_kernel': 3,
        'dilate_iterations': 2,
        'close_iterations': 3,
        'max_lateral_deviation': 80,
        'median_kernels': [7, 11, 15, 21, 31],  # 更多尺度
    },
    'medium': {
        'min_area': 8,
        'max_area': 2000,
        'min_circularity': 0.12,
        'color_threshold': 5,
        'morph_kernel': 5,
        'dilate_iterations': 1,
        'close_iterations': 2,
        'max_lateral_deviation': 60,
        'median_kernels': [11, 21, 31],
    },
    'low': {
        'min_area': 30,
        'max_area': 1000,
        'min_circularity': 0.30,
        'color_threshold': 15,
        'morph_kernel': 5,
        'dilate_iterations': 1,
        'close_iterations': 2,
        'max_lateral_deviation': 40,
        'median_kernels': [21, 31],
    },
}


def _get_params(sensitivity='medium', resolution="1920x1080"):
    """根据灵敏度和分辨率生成检测参数"""
    base = _SENSITIVITY_PRESETS.get(sensitivity, _SENSITIVITY_PRESETS['medium']).copy()

    # 按分辨率缩放面积相关参数
    try:
        _, h = map(int, resolution.split('x'))
    except (ValueError, AttributeError):
        h = 1080
    scale = h / 1080.0
    area_scale = scale * scale
    base['min_area'] = max(2, int(base['min_area'] * area_scale))
    base['max_area'] = int(base['max_area'] * area_scale)
    base['morph_kernel'] = max(3, int(base['morph_kernel'] * scale)) | 1  # 保证奇数
    base['max_lateral_deviation'] = int(base['max_lateral_deviation'] * scale)
    return base


# ═══════════════════════════════════════════
# 弹痕检测（核心）
# ═══════════════════════════════════════════

class BulletDetector:
    """弹痕检测器

    支持三种检测模式:
      1. detect_single(image)           — 单图自适应（推荐，无需基线图）
      2. detect_with_template(img,tmpl) — 模板匹配（你提供一个弹孔的小截图）
      3. detect(base, result)           — 双图差分（需要基线图，最准但麻烦）

    所有模式都返回 list[dict]，每个 dict 包含 x, y, area, circularity 等字段。

    检测过程中产生的调试信息保存在 self.debug_info 中，
    调试图像保存在 self.debug_images 中，供 GUI 展示。
    """

    def __init__(self, resolution="1920x1080", sensitivity='medium'):
        """
        :param resolution: 截图分辨率，如 "1920x1080"
        :param sensitivity: 灵敏度 'low'(严格) / 'medium'(标准) / 'high'(宽松)
        """
        self.sensitivity = sensitivity
        self.params = _get_params(sensitivity, resolution)

        # ── debug 容器（每次检测前清空）──
        self.debug_info = {}     # 文本信息: 各步骤候选数、过滤原因等
        self.debug_images = {}   # 中间图像: diff, threshold, contours 等

    # ═══ 模式1: 单图自适应 ═══

    def detect_single(self, image):
        """【推荐】只需一张弹痕截图，自动检测弹孔。

        原理:
          1. CLAHE 增强对比度（让暗弹痕更明显）
          2. 多尺度中值滤波生成虚拟基线（不同kernel捕获不同大小的弹痕）
             - 小kernel(11): 只模糊小特征，适合检测较大弹痕
             - 大kernel(31): 模糊大特征，适合检测较小弹痕
          3. 对每个尺度做 差分→阈值→轮廓检测
          4. 合并所有尺度的结果，NMS 去重
          5. 噪声过滤（移除偏离主弹道的散点）

        如果检测不到:
          - 尝试 sensitivity='high'
          - 或改用 detect_with_template() 模板匹配
        """
        self._reset_debug()
        log.info("开始单图自适应检测, 灵敏度=%s", self.sensitivity)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self.debug_images['01_gray'] = gray.copy()

        # Step 1: CLAHE 对比度增强
        # 为什么用 CLAHE? 弹痕是深色小区域，在浅色墙面上可能对比度很低
        # CLAHE (Contrast Limited Adaptive Histogram Equalization) 局部增强对比度
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        self.debug_images['02_clahe'] = enhanced.copy()
        log.debug("CLAHE 增强完成")

        # Step 2: 多尺度中值滤波 → 差分检测
        all_holes = []
        kernels = self.params.get('median_kernels', [11, 21, 31])
        log.debug("使用中值滤波核: %s", kernels)

        for ks in kernels:
            # 中值滤波: 用半径为 ks//2 的邻域中值替代每个像素
            # 效果: 移除小于半径的特征（如弹痕），保留大面积区域（如墙面）
            baseline = cv2.medianBlur(enhanced, ks)
            self.debug_images[f'03_baseline_k{ks}'] = baseline.copy()

            holes = self._detect_from_diff(baseline, enhanced, tag=f'median_k{ks}')
            log.debug("  核%d: 检测到 %d 个候选", ks, len(holes))
            all_holes.extend(holes)

        # Step 3: 自适应阈值策略（补充检测暗色斑点）
        # 为什么需要这个? 中值滤波可能miss掉与背景色差很小的弹痕
        adaptive_holes = self._detect_adaptive(enhanced, tag='adaptive')
        log.debug("自适应阈值: 检测到 %d 个候选", len(adaptive_holes))
        all_holes.extend(adaptive_holes)

        # Step 4: NMS 去重（多策略可能检测到同一个弹痕多次）
        before_nms = len(all_holes)
        merged = self._nms(all_holes, min_dist=12)
        log.debug("NMS 去重: %d → %d", before_nms, len(merged))

        # Step 5: 噪声过滤
        filtered = self._filter_noise(merged)
        log.info("最终结果: %d 个弹痕 (候选%d, NMS后%d)", len(filtered), before_nms, len(merged))

        self.debug_info['total_candidates'] = before_nms
        self.debug_info['after_nms'] = len(merged)
        self.debug_info['final'] = len(filtered)
        self.debug_info['mode'] = '单图自适应'
        self.debug_info['sensitivity'] = self.sensitivity
        self.debug_info['params'] = {k: v for k, v in self.params.items() if k != 'median_kernels'}

        return filtered

    # ═══ 模式2: 模板匹配 ═══

    def detect_with_template(self, image, template, threshold=0.55):
        """用弹孔模板在图中匹配。

        模板要求（重要!）:
          - 截取图中一个弹孔，紧贴边缘裁剪
          - 尺寸建议 15x15 ~ 50x50 像素
          - 背景色应与目标墙面一致
          - 可以直接从弹痕截图中 截取一个弹孔 作为模板

        原理:
          1. 多尺度匹配: 模板缩放 0.5x~1.8x，因为弹痕大小不完全一致
          2. 归一化相关系数匹配 (TM_CCOEFF_NORMED): 对亮度变化鲁棒
          3. 超过阈值的位置 → 候选弹痕
          4. NMS 去除重叠检测

        :param template: 弹孔模板图 (BGR 或灰度，15~50px 的小图)
        :param threshold: 匹配置信度阈值 (0~1, 越低越宽松, 默认0.55)
        """
        self._reset_debug()
        log.info("开始模板匹配检测, threshold=%.2f", threshold)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        tmpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if template.ndim == 3 else template
        th, tw = tmpl.shape[:2]
        log.debug("模板尺寸: %dx%d", tw, th)

        self.debug_images['01_image'] = gray.copy()
        self.debug_images['02_template'] = tmpl.copy()

        # CLAHE 增强（让弹痕更清晰）
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray_e = clahe.apply(gray)
        tmpl_e = clahe.apply(tmpl)

        holes = []
        # 多尺度: 弹痕在图中可能比模板稍大或稍小
        for scale in np.arange(0.5, 1.9, 0.1):
            st = cv2.resize(tmpl_e, None, fx=scale, fy=scale)
            if st.shape[0] >= gray_e.shape[0] or st.shape[1] >= gray_e.shape[1]:
                continue

            # TM_CCOEFF_NORMED: 值范围 -1~1, 越接近1越匹配
            result = cv2.matchTemplate(gray_e, st, cv2.TM_CCOEFF_NORMED)
            locs = np.where(result >= threshold)

            for pt in zip(*locs[::-1]):
                cx = pt[0] + st.shape[1] // 2
                cy = pt[1] + st.shape[0] // 2
                conf = float(result[pt[1], pt[0]])
                holes.append({
                    'x': cx, 'y': cy,
                    'area': int(st.shape[0] * st.shape[1]),
                    'circularity': 1.0,
                    'color_diff': 50,
                    'confidence': conf,
                })

            if locs[0].size > 0:
                log.debug("  scale=%.2f: 找到 %d 个匹配", scale, locs[0].size)

        before_nms = len(holes)
        # NMS 距离 = 模板尺寸的一半（避免重叠检测）
        holes = self._nms(holes, min_dist=max(8, max(tw, th) // 2))
        filtered = self._filter_noise(holes)

        log.info("模板匹配完成: 候选%d, NMS后%d, 最终%d", before_nms, len(holes), len(filtered))

        self.debug_info['total_candidates'] = before_nms
        self.debug_info['after_nms'] = len(holes)
        self.debug_info['final'] = len(filtered)
        self.debug_info['mode'] = '模板匹配'
        self.debug_info['template_size'] = f'{tw}x{th}'
        self.debug_info['threshold'] = threshold

        return filtered

    # ═══ 模式3: 双图差分 ═══

    def detect(self, base, result):
        """传统模式: 基线图(空墙) vs 结果图(弹痕)

        :param base: 空墙面截图 (BGR)
        :param result: 打完后的截图 (BGR)
        """
        self._reset_debug()
        log.info("开始双图差分检测")

        if base.shape != result.shape:
            result = cv2.resize(result, (base.shape[1], base.shape[0]))
        bg = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
        rg = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)

        self.debug_images['01_base'] = bg.copy()
        self.debug_images['02_result'] = rg.copy()

        holes = self._detect_from_diff(bg, rg, tag='dual_diff')

        self.debug_info['total_candidates'] = len(holes)
        self.debug_info['final'] = len(holes)
        self.debug_info['mode'] = '双图差分'

        return holes

    # ═══ 核心检测引擎 ═══

    def _detect_from_diff(self, bg_gray, result_gray, tag=''):
        """差分检测核心流程:
          1. 计算两张灰度图的绝对差 → diff
          2. OTSU 自动阈值 → 二值化 (如果OTSU效果不好则用固定阈值回退)
          3. 形态学操作(闭运算+膨胀) → 填充弹痕内部空洞
          4. 轮廓检测 → 候选区域
          5. 过滤: 面积、圆形度、颜色差异

        :param tag: 调试标签，用于区分不同策略
        """
        diff = cv2.absdiff(bg_gray, result_gray)
        self.debug_images[f'{tag}_diff'] = diff.copy()

        # OTSU 阈值: 自动寻找最佳分割点
        # 如果图像大部分没变化（弹痕占比很小），OTSU 可能选错阈值
        otsu_val, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        white_ratio = np.sum(thresh > 0) / max(1, thresh.size)
        log.debug("  [%s] OTSU阈值=%d, 白色像素占比=%.4f", tag, otsu_val, white_ratio)

        # 如果 OTSU 效果异常（白色太多或太少），用固定低阈值回退
        if white_ratio > 0.20 or white_ratio < 0.0001:
            fallback_th = max(8, int(otsu_val * 0.4)) if otsu_val > 20 else 10
            _, thresh = cv2.threshold(diff, fallback_th, 255, cv2.THRESH_BINARY)
            log.debug("  [%s] OTSU 异常, 回退固定阈值=%d", tag, fallback_th)

        self.debug_images[f'{tag}_thresh'] = thresh.copy()

        # 形态学: 闭运算填充小孔洞 → 膨胀扩大轮廓使碎片连通
        ks = self.params['morph_kernel']
        k = np.ones((ks, ks), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k,
                                  iterations=self.params['close_iterations'])
        thresh = cv2.dilate(thresh, k,
                            iterations=self.params['dilate_iterations'])

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        log.debug("  [%s] 轮廓数=%d", tag, len(contours))

        holes = []
        min_a = self.params['min_area']
        max_a = self.params['max_area']
        min_c = self.params['min_circularity']
        color_th = self.params['color_threshold']
        rejected = {'area_small': 0, 'area_big': 0, 'shape': 0, 'color': 0}

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_a:
                rejected['area_small'] += 1
                continue
            if area > max_a:
                rejected['area_big'] += 1
                continue

            # 圆形度 = 4π·面积/周长² , 圆=1.0, 方形=π/4≈0.785, 长条<0.5
            peri = cv2.arcLength(cnt, True)
            if peri == 0:
                continue
            circularity = 4 * np.pi * (area / (peri * peri))
            if circularity < min_c:
                rejected['shape'] += 1
                continue

            # 质心坐标
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            # 颜色差异: 背景和结果在该区域的平均亮度之差
            mask = np.zeros(bg_gray.shape[:2], dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            color_diff = abs(cv2.mean(bg_gray, mask=mask)[0] - cv2.mean(result_gray, mask=mask)[0])
            if color_diff < color_th:
                rejected['color'] += 1
                continue

            holes.append({
                'x': cx, 'y': cy,
                'area': round(float(area), 1),
                'circularity': round(circularity, 3),
                'color_diff': round(color_diff, 1),
            })

        log.debug("  [%s] 通过=%d, 拒绝: 面积小=%d 面积大=%d 形状=%d 颜色=%d",
                  tag, len(holes), rejected['area_small'], rejected['area_big'],
                  rejected['shape'], rejected['color'])
        self.debug_info[f'{tag}_rejected'] = rejected
        self.debug_info[f'{tag}_passed'] = len(holes)

        return self._filter_noise(holes)

    def _detect_adaptive(self, gray, tag='adaptive'):
        """自适应阈值检测: 不需要差分，直接找深色斑点。

        原理: 用 cv2.adaptiveThreshold 将每个像素与其邻域比较，
        比邻域暗的区域 → 白色 → 候选弹痕。

        适合: 弹痕与墙面对比度低、或中值滤波效果差的情况。
        缺点: 墙面本身有纹理时容易误检。
        """
        # blockSize=21: 21x21 邻域
        # C=8: 低于邻域均值 8 个灰度值才算前景
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 8)

        ks = self.params['morph_kernel']
        k = np.ones((ks, ks), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k, iterations=1)

        self.debug_images[f'{tag}_binary'] = binary.copy()

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        log.debug("  [%s] 轮廓数=%d", tag, len(contours))

        holes = []
        min_a = self.params['min_area']
        max_a = self.params['max_area']
        min_c = self.params['min_circularity'] * 1.5  # 自适应模式需要更严格的形状约束

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
            holes.append({
                'x': cx, 'y': cy,
                'area': round(float(area), 1),
                'circularity': round(circularity, 3),
                'color_diff': 50,  # 无差分时无法计算，给默认值
            })

        log.debug("  [%s] 通过=%d", tag, len(holes))
        return holes

    # ═══ 去重与过滤 ═══

    @staticmethod
    def _nms(holes, min_dist=12):
        """非极大值抑制: 多策略检测同一弹痕时去重。
        保留置信度/颜色差最高的那个。
        """
        if not holes:
            return holes
        holes = sorted(holes, key=lambda h: h.get('confidence', h.get('color_diff', 0)), reverse=True)
        keep = []
        for h in holes:
            if not any(abs(h['x'] - k['x']) < min_dist and abs(h['y'] - k['y']) < min_dist for k in keep):
                keep.append(h)
        return keep

    def _filter_noise(self, holes):
        """噪声过滤: 弹痕应该沿一条竖直线分布（后坐力是竖直的），
        偏离主轴太远的点 → 噪声/误检。

        算法:
          1. 计算所有弹孔 X 坐标的中位数 → 主轴
          2. 保留 |x - median_x| < max_lateral_deviation 的弹孔
          3. 如果主轴组太少，尝试其他中心点
        """
        if len(holes) < 4:
            return holes
        max_dx = self.params['max_lateral_deviation']
        xs = [h['x'] for h in holes]
        median_x = float(np.median(xs))

        main_group = [h for h in holes if abs(h['x'] - median_x) <= max_dx]
        if len(main_group) < 3:
            # 中位数不靠谱时，以每个点为中心找最大群组
            best_group = []
            for h in holes:
                group = [h2 for h2 in holes if abs(h2['x'] - h['x']) <= max_dx]
                if len(group) > len(best_group):
                    best_group = group
            return best_group if len(best_group) >= 3 else holes
        return main_group

    def _reset_debug(self):
        self.debug_info = {}
        self.debug_images = {}


# ═══════════════════════════════════════════
# 标注数据持久化
# ═══════════════════════════════════════════

class AnnotationData:
    """标注数据的保存和加载（JSON sidecar 文件）

    保存: 每次保存标注图时，在同目录生成 <文件名>.analysis.json
    加载: 选 .analysis.json 或 图片文件（自动查找同名JSON）
    """

    @staticmethod
    def save(image_path, holes, metadata=None):
        """保存标注数据"""
        p = Path(image_path)
        json_path = p.parent / f"{p.stem}.analysis.json"
        data = {
            'version': 2,
            'holes': [{'x': h['x'], 'y': h['y'], 'shot_num': h.get('shot_num', 0),
                        'area': h.get('area', 100), 'circularity': h.get('circularity', 1.0),
                        'color_diff': h.get('color_diff', 50)} for h in holes],
            'metadata': metadata or {},
            'timestamp': datetime.now().isoformat(),
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(json_path)

    @staticmethod
    def load(path):
        """加载标注数据，返回 (holes, metadata) 或 (None, None)"""
        p = Path(path)
        if p.suffix.lower() == '.json':
            json_path = p
        else:
            json_path = p.parent / f"{p.stem}.analysis.json"
        if not json_path.exists():
            return None, None
        try:
            with open(json_path, encoding='utf-8') as f:
                data = json.load(f)
            return data.get('holes', []), data.get('metadata', {})
        except Exception:
            return None, None

    @staticmethod
    def find_image_for_json(json_path):
        """根据 JSON 路径查找对应的原始图片"""
        p = Path(json_path)
        stem = p.stem.replace('.analysis', '')
        for ext in ['.png', '.jpg', '.bmp', '.jpeg']:
            img = p.parent / f"{stem}{ext}"
            if img.exists():
                return str(img)
        return None

    @staticmethod
    def list_annotations(directory):
        """列出目录下所有标注文件"""
        d = Path(directory)
        return sorted(d.glob("*.analysis.json"), key=lambda f: f.stat().st_mtime, reverse=True)


# ═══════════════════════════════════════════
# 迭代修正
# ═══════════════════════════════════════════

class IterativeCorrector:
    """迭代修正: 宏开启后拍新弹痕 + 上一轮参数 → 微调

    工作流:
      Round 1: 不开宏射击 → 分析 → 修正参数 v1
      Round 2: 开宏(用v1)射击 → 残余偏移 → 微调 → 修正参数 v2
      Round N: ...

    原理:
      宏开启后，理想情况所有弹孔应在同一位置（完美补偿）。
      实际残余偏移 = 补偿误差:
        dy > 0（弹孔偏下）→ 补偿过度 → 减小参数
        dy < 0（弹孔偏上）→ 补偿不足 → 增大参数
    """

    @staticmethod
    def correct(residual_holes, prev_params, scope_val, posture_val, chunk_size=12):
        """
        :param residual_holes: 宏开启后的弹痕坐标
        :param prev_params: 上一轮的参数数组
        :return: dict 包含 corrected_params, residuals 等
        """
        if len(residual_holes) < 2 or not prev_params:
            return None

        s = sorted(residual_holes, key=lambda h: h.get('shot_num', 0))
        n_intervals = len(s) - 1
        chunk = min(chunk_size, max(1, len(prev_params) // max(1, n_intervals)))
        factor = max(0.01, scope_val * posture_val)

        corrected = [float(v) for v in prev_params]
        residuals = []

        for i in range(1, len(s)):
            dy = s[i]['y'] - s[i - 1]['y']
            dx = s[i]['x'] - s[i - 1]['x']

            # 需要增减的补偿量（像素 → 原始值空间）
            adjustment_raw = -dy / factor

            start = (i - 1) * chunk
            end = min(i * chunk, len(corrected))
            chunk_sum = sum(abs(prev_params[j]) for j in range(start, min(end, len(prev_params))))

            # 按原始值的比例分配调整量到各个tick
            for j in range(start, min(end, len(corrected))):
                if chunk_sum > 0 and prev_params[j] != 0:
                    proportion = abs(prev_params[j]) / chunk_sum
                    corrected[j] = round(corrected[j] + adjustment_raw * proportion, 1)

            residuals.append({
                'shot': i,
                'dy': round(float(dy), 1),
                'dx': round(float(dx), 1),
                'adjustment_px': round(float(-dy), 1),
                'adjustment_raw': round(float(adjustment_raw), 2),
            })

        return {
            'previous_params': prev_params,
            'corrected_params': corrected,
            'residuals': residuals,
            'scope_val': scope_val,
            'posture_val': posture_val,
            'avg_residual_dy': round(float(np.mean([r['dy'] for r in residuals])), 1),
            'max_residual_dy': round(float(max(abs(r['dy']) for r in residuals)), 1),
        }


# ═══════════════════════════════════════════
# 弹痕排序
# ═══════════════════════════════════════════

class BulletSorter:
    """排序弹痕: PUBG 后坐力使子弹向上飞

    先打的弹痕在最下面（Y值最大），后打的在上面（Y值最小）。
    排序后为每个弹孔分配 shot_num: 1=第一发(Y最大), 2=第二发 ...
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
    """与 GunData JSON 弹道数据对比，计算校准系数。

    核心公式:
      实际补偿(像素) = 弹孔间距 = |Y₁ - Y₂|
      理论补偿(像素) = sum(chunk_values) × 灵敏度 × 姿态系数

      比值 = 实际/理论:
        > 1.0 → 弹跳大于预期 → 参数偏小（补偿不足）
        < 1.0 → 弹跳小于预期 → 参数偏大（过度补偿）
        ≈ 1.0 → 参数准确

    数据格式:
      Process.FIRE() 对弹道数组逐元素执行 mouse_R(0, 姿态*(值*灵敏度))
      间隔 9ms/tick。M762(600RPM) 每发≈100ms → 约11个tick/发
    """

    def __init__(self, gun_data_dir=None):
        self.gun_data_dir = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())

    def compare(self, holes, gun_name, acc_code, scope_val, posture_val):
        """对比实际弹痕间距与理论值

        :param holes: 已排序的弹痕列表
        :param gun_name: 枪械名 (如 "m762")
        :param acc_code: 配件码 (如 "A0B0C0")
        :param scope_val: 灵敏度系数
        :param posture_val: 姿态系数
        :return: dict 包含 details, avg_ratio 等
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

        is_semi = gun_name.lower() in _SEMI_AUTO_GUNS
        chunk = self._estimate_chunk_size(raw, is_semi)

        n_intervals = len(s) - 1
        max_intervals = max(1, len(raw) // max(1, chunk))
        n_compare = min(n_intervals, max_intervals)

        # 实际间距(px): shot 1(Y最大) - shot 2(Y次大) = 第1→2发的Y位移
        actual_spacings = [s[i - 1]['y'] - s[i]['y'] for i in range(1, len(s))]
        actual_dx = [s[i]['x'] - s[i - 1]['x'] for i in range(1, len(s))]

        # 理论间距(px): chunk内所有tick值的累加 × 灵敏度 × 姿态
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
                status = "偏大" if ratio > 1.3 else "偏小" if ratio < 0.7 else "正常"
            elif actual <= 0:
                ratio = None
                status = "异常(负间距)"
            else:
                ratio = None
                status = "理论=0"

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
        """估算每发子弹对应的数组元素数量

        半自动: 1个元素=1发
        全自动: 9ms/tick, 射速决定每发的tick数
          600RPM → 100ms/发 → 11 ticks
          800RPM → 75ms/发 → 8 ticks
        """
        if is_semi:
            return 1
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
    """绘制弹痕标注图和柱状图"""

    @staticmethod
    def draw_holes(img, holes):
        """在图上标注弹孔编号、箭头连线、间距信息"""
        vis = img.copy()
        s = sorted(holes, key=lambda h: h['shot_num'])

        # 相邻弹孔连线（箭头）
        for i in range(len(s) - 1):
            dy = abs(s[i]['y'] - s[i + 1]['y'])
            dx = abs(s[i]['x'] - s[i + 1]['x'])
            # 颜色编码: 红=间距极小(可能误检), 黄=间距偏小, 绿=正常
            color = (0, 0, 255) if (dy < 5 and dx < 5) else (0, 255, 255) if dy < 15 else (0, 255, 0)
            cv2.arrowedLine(vis, (s[i]['x'], s[i]['y']),
                            (s[i + 1]['x'], s[i + 1]['y']), color, 2, tipLength=0.15)

        # 弹孔标记
        for hv in s:
            n = hv['shot_num']
            # 颜色编码: 红=前5发, 橙=6-15发, 绿=后续
            col = (0, 0, 255) if n <= 5 else (0, 165, 255) if n <= 15 else (0, 255, 0)
            cv2.circle(vis, (hv['x'], hv['y']), 10, col, 2)
            cv2.circle(vis, (hv['x'], hv['y']), 3, col, -1)
            cv2.putText(vis, str(n), (hv['x'] + 14, hv['y'] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # 统计信息
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
        """绘制纵向间距柱状图"""
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
        """绘制水平漂移柱状图"""
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
    """分析结果文件保存器"""

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
# 修正参数生成
# ═══════════════════════════════════════════

class ParameterCorrector:
    """根据校准结果生成修正后的压枪参数

    两种修正方案:
      均匀修正: 所有tick值 × 平均比值 (简单, 推荐先试)
      逐发修正: 每个chunk × 对应比值 (精确, 但可能过拟合)
    """

    def __init__(self, gun_data_dir=None):
        self.gun_data_dir = Path(gun_data_dir) if gun_data_dir else Path(_find_gun_data_dir())

    def correct(self, comparison_result, gun_name, acc_code, use_float=True):
        """
        :param use_float: True=保留1位小数, False=取整
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

        # 方案一: 均匀修正 — 所有值乘以相同比率
        corrected_uniform = [_round(v * avg_ratio) if v != 0 else 0 for v in original]

        # 方案二: 逐发修正 — 每个chunk用对应的ratio
        per_shot = list(original)
        for i, d in enumerate(details):
            r = d.get('ratio')
            if r is None:
                continue
            start = i * chunk
            end = min((i + 1) * chunk, len(per_shot))
            for j in range(start, end):
                per_shot[j] = _round(original[j] * r) if original[j] != 0 else 0

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
        """分析水平漂移，判断是随机还是系统性的"""
        drifts = comp.get('horizontal_drifts', [])
        if not drifts:
            return None

        avg_dx = comp.get('avg_horizontal_drift', 0)
        std_dx = comp.get('std_horizontal_drift', 0)

        # 标准差 >> 均值 → 随机性为主
        if std_dx > abs(avg_dx) * 1.5 and abs(avg_dx) < 3:
            return {'type': 'random', 'avg': avg_dx, 'std': std_dx,
                    'suggestion': '水平漂移随机性强，不建议固定X补偿'}

        scope = comp.get('scope_val', 1.0)
        posture = comp.get('posture_val', 1.0)
        factor = max(0.01, scope * posture)

        x_per_chunk = []
        for i, dx in enumerate(drifts):
            x_raw = round(-dx / factor / max(1, chunk), 1)
            x_per_chunk.append(x_raw)

        return {
            'type': 'compensatable',
            'avg': avg_dx, 'std': std_dx,
            'x_per_chunk': x_per_chunk,
            'suggestion': f'平均水平偏移 {avg_dx:+.1f}px，可添加X轴补偿',
        }

    @staticmethod
    def format_array_for_json(arr, items_per_line=36):
        """格式化数组为 JSON 可读格式"""
        lines = []
        for i in range(0, len(arr), items_per_line):
            chunk = arr[i:i + items_per_line]
            lines.append("        " + ", ".join(str(v) for v in chunk))
        return "[\n" + ",\n".join(lines) + "\n    ]"

    @staticmethod
    def generate_patch_json(correction_result, mode='uniform'):
        """生成可直接粘贴到 JSON 的修正参数"""
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
    """多组弹痕数据交叉比对，取最优参数

    使用场景: 多次射击取平均，提高修正参数的可靠性。
    IQR 方法自动移除异常组（比如手抖了那次）。
    """

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
        """跨组统计分析"""
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

        # IQR 离群值移除
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

def analyze_bullet_pattern(result_img, gun_name, acc_code,
                           scope_val=1.0, posture_val=1.0,
                           resolution="1920x1080", save_results=True,
                           base_img=None, template_img=None,
                           sensitivity='medium'):
    """一站式弹痕分析

    :param result_img: 弹痕截图 (BGR)
    :param base_img: 基线图 (可选)
    :param template_img: 弹孔模板 (可选)
    :param sensitivity: 检测灵敏度 'low'/'medium'/'high'
    """
    detector = BulletDetector(resolution, sensitivity)
    comparator = BulletComparator()
    visualizer = BulletVisualizer()

    if template_img is not None:
        holes = detector.detect_with_template(result_img, template_img)
    elif base_img is not None:
        holes = detector.detect(base_img, result_img)
    else:
        holes = detector.detect_single(result_img)

    if not holes:
        return {'holes': [], 'comparison': None, 'error': '未检测到弹痕',
                'debug_info': detector.debug_info}

    sorted_holes = BulletSorter.sort(holes)
    comparison = comparator.compare(sorted_holes, gun_name, acc_code, scope_val, posture_val)

    result = {
        'holes': sorted_holes,
        'comparison': comparison,
        'shot_count': len(sorted_holes),
        'debug_info': detector.debug_info,
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
        description="PUBG 弹痕分析工具 — 支持单图/模板/双图模式",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("result", help="射击后的墙面截图路径")
    parser.add_argument("--base", default=None, help="基线图(可选)")
    parser.add_argument("--template", default=None, help="弹孔模板图(可选)")
    parser.add_argument("--gun", default="m762", help="枪械名")
    parser.add_argument("--acc", default="A0B0C0", help="配件码")
    parser.add_argument("--scope", type=float, default=None, help="灵敏度系数")
    parser.add_argument("--posture", type=float, default=1.0, help="姿态系数")
    parser.add_argument("--resolution", default="1920x1080", help="分辨率")
    parser.add_argument("--sensitivity", choices=['low', 'medium', 'high'],
                        default='medium', help="检测灵敏度")
    parser.add_argument("--debug", action="store_true", help="显示详细调试信息")
    parser.add_argument("--no-save", action="store_true", help="不保存结果")

    args = parser.parse_args()

    # debug 模式开启详细日志
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="  [DEBUG] %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="  %(message)s")

    scope = args.scope
    if scope is None:
        cfg = _load_sensitivity_config()
        scope = cfg.get('none', 1.0)

    result_img = cv2.imread(args.result)
    if result_img is None:
        print(f"错误: 无法读取结果图 {args.result}")
        return 1

    detector = BulletDetector(args.resolution, args.sensitivity)
    if args.template:
        tmpl = cv2.imread(args.template)
        if tmpl is None:
            print(f"错误: 无法读取模板图 {args.template}")
            return 1
        holes = detector.detect_with_template(result_img, tmpl)
        mode = "模板匹配"
    elif args.base:
        base_img = cv2.imread(args.base)
        if base_img is None:
            print(f"错误: 无法读取基线图 {args.base}")
            return 1
        holes = detector.detect(base_img, result_img)
        mode = "双图差分"
    else:
        holes = detector.detect_single(result_img)
        mode = "单图自适应"

    print(f"\n{'=' * 55}")
    print(f"  PUBG 弹痕分析 ({mode}, 灵敏度={args.sensitivity})")
    print(f"{'=' * 55}")
    print(f"  枪械: {args.gun}  配件码: {args.acc}")
    print(f"  倍镜系数: {scope}  姿态系数: {args.posture}")
    print(f"{'=' * 55}\n")

    if args.debug:
        di = detector.debug_info
        print(f"  [调试] 候选={di.get('total_candidates', '?')}"
              f"  NMS后={di.get('after_nms', '?')}"
              f"  最终={di.get('final', '?')}")
        for k, v in di.items():
            if k.endswith('_rejected'):
                print(f"  [调试] {k}: {v}")
        print()

    if not holes:
        print("  未检测到弹痕。")
        print("  建议: --sensitivity high 或 --template <弹孔截图>")
        return 1

    sorted_holes = BulletSorter.sort(holes)
    comparator = BulletComparator()
    comparison = comparator.compare(sorted_holes, args.gun, args.acc, scope, args.posture)

    if not args.no_save:
        visualizer = BulletVisualizer()
        saver = ResultSaver()
        vis = visualizer.draw_holes(result_img, sorted_holes)
        saver.save_image("bullet_holes_marked", vis)
        AnnotationData.save(args.result, sorted_holes, {
            'gun': args.gun, 'acc': args.acc, 'scope': scope, 'posture': args.posture,
        })
        if args.debug:
            for name, img in detector.debug_images.items():
                saver.save_image(f"debug_{name}", img)
            print(f"  [调试] 中间图像已保存到 calibration_results/\n")

    print(f"  检测到 {len(sorted_holes)} 个弹痕\n")

    if comparison:
        print(f"  {'发':>4} {'实际px':>8} {'理论px':>8} {'原值':>6} {'比值':>8} {'X漂':>6} {'状态'}")
        print(f"  {'-' * 58}")
        for d in comparison['details']:
            ratio_str = f"{d['ratio']:.4f}" if d['ratio'] is not None else "  N/A"
            print(f"  {d['shot']:>4} {d['actual_dy']:>8.1f} {d['theory_dy']:>8.1f} "
                  f"{d['raw_chunk_sum']:>6.1f} {ratio_str:>8}  {d['x_drift']:>+5.0f} {d['status']}")
        print(f"  {'-' * 58}")
        print(f"  平均比值: {comparison['avg_ratio']:.4f}  标准差: {comparison['std_ratio']:.4f}")
        print(f"  建议倍镜系数: {comparison['suggested_scope']}")
        print(f"  水平漂移: 均值{comparison['avg_horizontal_drift']:+.1f} "
              f"标准差{comparison['std_horizontal_drift']:.1f} "
              f"最大{comparison['max_horizontal_drift']:.1f}px")

        corrector = ParameterCorrector()
        correction = corrector.correct(comparison, args.gun, args.acc)
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
