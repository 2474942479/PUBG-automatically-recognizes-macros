import cv2
import json
import logging
import mss
import os
import threading
import time
import asyncio
import numpy as np
from collections import Counter
from PIL import ImageGrab

from core.paths import res_path
# ✅ 不再从 data.resolution_setting 导入，由调用方传入配置
# from data.resolution_setting import RESOLUTION_SETTINGS, GUNS_REOLUTION_SETTINGS, Click

logger = logging.getLogger(__name__)

# 全局 SIFT 检测器（避免重复创建）
_sift_detector = None
# ✅ 全局 FLANN 匹配器（避免重复创建）
_flann_matcher = None
# ✅ 全局 ORB 检测器（避免重复创建，用于小图标特征匹配）
_orb_detector = None
# ✅ 全局 ROI 配置缓存
_roi_config_cache = None
_roi_config_cache_time = 0
_roi_config_cache_ttl = 60  # 缓存 60 秒

# ROI 裁剪边距(px)，补偿模板和截图之间的像素级位置偏移
# PUBG 背包 UI 在每次打开时可能有 ±1~2px 的抖动
# 裁剪时扩边 → matchTemplate 滑动窗口自动找最佳对齐位置
PADDING = 2

# 单次 Tab 多帧截图投票（FPS 游戏实时性要求高，不依赖跨次 Tab 累积历史）
# 每次按 Tab 快速截取 N 帧背包大图，对每帧独立识别，投票取共识结果
# 帧间隔 ≥ 1 个游戏渲染帧（60fps=16.7ms），确保是不同画面
MULTI_FRAME_COUNT = 3         # 截取帧数
MULTI_FRAME_INTERVAL = 0.04   # 帧间隔 40ms
MULTI_FRAME_MIN_VOTES = 2     # 投票最少一致票数

# ============================================================
# HUD 枪械图标识别稳定性机制（最高优先准确性）
# ============================================================
# 多帧共识：Gun_1 / Gun_2 的近 N 帧识别历史，与当前帧不一致时
# 用共识结果兰底，避免单帧误识导致压枪数据错乱。
# FPS 游戏：1/2 切枪频繁，5 帧 / 3 票避免切枪瞬间的单帧噪声
_HUD_CONSENSUS_WINDOW = 5
_HUD_CONSENSUS_MIN_VOTES = 3
_hud_slot_history = {"Gun_1": [], "Gun_2": []}

# ⚠️ 已弃用：亮度判活已由按键（1/2）驱动替代，HUD 识别不再决定当前持枪。
# 保留亮度字段仅用于调试日志输出，不参与决策。

# Otsu 阈值跨帧 EMA 平滑：消除同一枪图标帧间阈值抖动导致的分数波动，
# 以 (slot_key, current_res) 为键。所有通道中唯一的带状态磁贴。
_otsu_threshold_ema = {}
_OTSU_EMA_ALPHA = 0.3  # 新帧权重：0.3 新帧 + 0.7 历史，平滑强度适中

# 背包配件 Otsu EMA 缓存（与 HUD 隔离）
# 仅在单次 Tab 的多帧之内有效，每次 Tab 开始时清空
_backpack_otsu_ema = {}

# HUD 区分度判定门槛：Top1-Top2 gap 过小 且 分数未达到高分线，拒绝识别。
_HUD_GAP_MIN = 0.03      # 最小差距
_HUD_HIGH_SCORE = 0.60   # 高分线：达到此分数即使 gap 小也接受

# 背包配件区分度判定门槛（与 HUD 参数独立，可单独调优）
_BACKPACK_GAP_MIN = 0.03
_BACKPACK_HIGH_SCORE = 0.55


def clear_backpack_otsu_ema():
    """每次 Tab 开始时清空背包配件 Otsu EMA 缓存，避免跨次 Tab 干扰"""
    global _backpack_otsu_ema
    _backpack_otsu_ema = {}

def _get_sift_detector():
    """获取或创建 SIFT 检测器（单例模式）"""
    global _sift_detector
    if _sift_detector is None:
        _sift_detector = cv2.SIFT_create()
    return _sift_detector

def _get_flann_matcher():
    """获取或创建 FLANN 匹配器（单例模式）"""
    global _flann_matcher
    if _flann_matcher is None:
        _flann_matcher = cv2.FlannBasedMatcher(FLANN_INDEX_PARAMS, FLANN_SEARCH_PARAMS)
    return _flann_matcher

def _get_orb_detector():
    global _orb_detector
    if _orb_detector is None:
        _orb_detector = cv2.ORB_create(
            nfeatures=200, scaleFactor=1.2, nlevels=4,
            edgeThreshold=5, patchSize=15
        )
    return _orb_detector


def _match_icon_canny(src, tmpl):
    """Canny edge matching - immune to brightness/transparency, fourth channel"""
    # 低阈值捕捉更多边缘，适合 99×75 的小图标
    e1 = cv2.Canny(src, 30, 100)
    e2 = cv2.Canny(tmpl, 30, 100)
    if e1.shape != e2.shape:
        return 0.0
    # 检查是否有足够边缘（全黑 = 无边缘 = 无效）
    if cv2.countNonZero(e1) < 20 or cv2.countNonZero(e2) < 20:
        return 0.0
    result = cv2.matchTemplate(e1, e2, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return score


def _classify_resolution(current_res):
    """
    分辨率三档分类：large (>=4K), medium (2K), small (<=1080p)
    :return: (tier, scale) where tier in ('large','medium','small'), scale = width/3840
    """
    if not current_res:
        return 'large', 1.0
    try:
        w = int(current_res.split('x')[0])
    except (ValueError, IndexError):
        return 'large', 1.0
    scale = w / 3840.0
    if w >= 3000:
        return 'large', scale
    elif w >= 2000:
        return 'medium', scale
    else:
        return 'small', scale


def _get_clahe_params(tier, scale):
    """分辨率自适应的 CLAHE 参数"""
    if tier == 'large':
        return 1.5, (4, 4)
    elif tier == 'medium':
        return 1.5, (3, 3)
    else:
        return 1.2, (2, 2)


def _preprocess_gun_icon(img_gray, tier='large', fixed_threshold=None):
    """
    HUD 枪械图标预处理 - 抗游戏滤镜干扰
    
    流程：CLAHE(增强对比度) → Otsu二值化(去颜色/亮度差异) → 中值滤波(去噪)
    
    原理：
    - 游戏滤镜主要改变颜色和整体亮度，但枪械轮廓形状不变
    - Otsu 二值化自动找最佳阈值，将图像转为黑白，去除滤镜带来的差异
    - 只保留枪械图标的黑白轮廓，不管滤镜怎么变，二值化后都接近
    
    注意：如果传入 fixed_threshold，则使用固定阈值进行二值化，
          确保模板和截图使用相同的阈值（必须两者都用相同阈值才有效）
    
    :param img_gray: 灰度图
    :param tier: 分辨率等级
    :param fixed_threshold: 固定阈值（用于确保模板和截图使用相同阈值）
    :return: 预处理后的图像
    """
    # 1. CLAHE 增强对比度（与现有逻辑一致）
    clip_limit, tile_grid = _get_clahe_params(tier, 1.0)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    img_enhanced = clahe.apply(img_gray)
    
    # 2. 二值化
    if fixed_threshold is not None:
        # 使用固定阈值（确保模板和截图使用相同阈值）
        _, img_binary = cv2.threshold(img_enhanced, fixed_threshold, 255, cv2.THRESH_BINARY)
    else:
        # Otsu 自动计算阈值
        _, img_binary = cv2.threshold(img_enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 3. 中值滤波去噪（平滑二值化带来的噪点）
    img_clean = cv2.medianBlur(img_binary, 3)
    
    return img_clean


def _get_canny_params(tier):
    """分辨率自适应的 Canny 阈值"""
    if tier == 'large':
        return 30, 100
    elif tier == 'medium':
        return 20, 70
    else:
        return 15, 50


def _match_icon_ccorr(src, tmpl):
    """
    CCORR_NORMED 模板匹配 -- 中/小图主力通道
    不依赖均值估计，纯幅度归一化，66px 以下比 CCOEFF 更稳定
    """
    if src.shape != tmpl.shape:
        return 0.0
    result = cv2.matchTemplate(src, tmpl, cv2.TM_CCORR_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return score


def _match_icon_sobel(src, tmpl, sobel_thresh=20):
    """Sobel 梯度匹配（独立函数）"""
    gx1 = cv2.Sobel(src, cv2.CV_64F, 1, 0, ksize=3)
    gy1 = cv2.Sobel(src, cv2.CV_64F, 0, 1, ksize=3)
    gm1 = cv2.magnitude(gx1, gy1).astype(np.uint8)
    gx2 = cv2.Sobel(tmpl, cv2.CV_64F, 1, 0, ksize=3)
    gy2 = cv2.Sobel(tmpl, cv2.CV_64F, 0, 1, ksize=3)
    gm2 = cv2.magnitude(gx2, gy2).astype(np.uint8)
    _, e1 = cv2.threshold(gm1, sobel_thresh, 255, cv2.THRESH_BINARY)
    _, e2 = cv2.threshold(gm2, sobel_thresh, 255, cv2.THRESH_BINARY)
    result = cv2.matchTemplate(e1, e2, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return score


def _match_icon_small(src, tmpl, tier, scale):
    """
    小图专用匹配 (<=1080p)
    pipeline: CLAHE_bilateral + CCORR_NORMED + ORB_multi_scale
    放弃 Sobel/Canny（40px 边缘太少），改用双边滤波平滑背景
    模板缩放到 90%/100%/110% 三个尺度匹配取 max
    """
    clip_limit, tile_grid = _get_clahe_params(tier, scale)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    src_c = clahe.apply(src)
    tmpl_c = clahe.apply(tmpl)
    # 双边滤波平滑背景，保留边缘
    src_c = cv2.bilateralFilter(src_c, 5, 50, 50)
    tmpl_c = cv2.bilateralFilter(tmpl_c, 5, 50, 50)
    # 主通道：CCORR_NORMED
    score_ccorr = _match_icon_ccorr(src_c, tmpl_c)
    # 多尺度 ORB（模板缩放 90%/100%/110%）
    score_orb = _match_icon_orb(src_c, tmpl_c)
    ht, wt = tmpl_c.shape
    for r in [0.9, 1.1]:
        new_h, new_w = max(10, int(ht * r)), max(10, int(wt * r))
        tmpl_scaled = cv2.resize(tmpl_c, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        ch, cw = tmpl_scaled.shape
        cy_s = max(0, (ch - ht) // 2)
        cx_s = max(0, (cw - wt) // 2)
        tmpl_cropped = tmpl_scaled[cy_s:cy_s + ht, cx_s:cx_s + wt]
        if tmpl_cropped.shape == src_c.shape:
            score_orb = max(score_orb, _match_icon_orb(src_c, tmpl_cropped))
    return max(score_ccorr, score_orb)


def _match_icon_orb(src, tmpl):
    """ORB binary feature matching - third channel"""
    orb = _get_orb_detector()
    kp1, des1 = orb.detectAndCompute(src, None)
    kp2, des2 = orb.detectAndCompute(tmpl, None)
    if des1 is None or des2 is None or len(des1) < 3 or len(des2) < 3:
        return 0.0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING2, crossCheck=True)
    try:
        matches = bf.match(des1, des2)
    except cv2.error:
        return 0.0
    if not matches:
        return 0.0
    matches = sorted(matches, key=lambda x: x.distance)
    good = [m for m in matches if m.distance < 60]
    max_possible = max(len(kp1), len(kp2))
    return min(len(good) / (max_possible + 0.1), 1.0)


def _match_hud_gun_icon(roi_gray, tmpl_img, tier, scale, slot_key, current_res):
    """
    HUD 枪械图标多通道融合匹配（最高优先准确性）

    融合通道（取 max）：
      1. CLAHE + TM_CCOEFF_NORMED   — 灰度底层匹配
      2. Sobel 梯度                   — 抜除绝对亮度，只留梯度结构
      3. Canny 边缘                   — 更鲁棒的轮廓提取，不对亮度敏感
      4. Otsu 二值化（跨帧 EMA 平滑阈值）

    关键鲁棒性设计：
      - 四通道任一失效，剩余通道仍能给出正确判断
      - Otsu 阈值跨帧 EMA 平滑，消除同一枪帧间阈值抖动导致的分数波动
      - 所有通道用同一组 CLAHE 增强后的灰度图作输入，避免重复计算
      - 对尺寸不同的 roi/tmpl 使用 matchTemplate 滑动窗口匹配

    :param roi_gray: HUD 枪械图标的 ROI 灰度图（带 PADDING 边距）
    :param tmpl_img: 枪械模板灰度图
    :param tier: 分辨率等级 'large'/'medium'/'small'
    :param scale: 分辨率缩放系数
    :param slot_key: 'Gun_1' 或 'Gun_2'（用于 Otsu EMA 缓存的按槽位隔离）
    :param current_res: 当前分辨率字符串（用于 Otsu EMA 缓存键）
    :return: best_score float ∈ [0, 1]
    """
    hs, ws = roi_gray.shape[:2]
    ht, wt = tmpl_img.shape[:2]
    if hs < ht or ws < wt:
        return 0.0

    # 统一 CLAHE 预处理（所有通道共用，避免重复计算）
    clip_limit, tile_grid = _get_clahe_params(tier, 1.0)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    roi_c = clahe.apply(roi_gray)
    tmpl_c = clahe.apply(tmpl_img)

    scores = []

    # 通道 1：CLAHE 灰度 CCOEFF_NORMED
    try:
        r1 = cv2.matchTemplate(roi_c, tmpl_c, cv2.TM_CCOEFF_NORMED)
        _, s1, _, _ = cv2.minMaxLoc(r1)
        scores.append(float(s1))
    except cv2.error:
        pass

    # 通道 2：Sobel 梯度（对亮度偏移免疫）
    try:
        sobel_thresh = 20 if tier == 'large' else (15 if tier == 'medium' else 10)
        s2 = _match_icon_sobel(roi_c, tmpl_c, sobel_thresh)
        scores.append(float(s2))
    except cv2.error:
        pass

    # 通道 3：Canny 边缘（滑动窗口匹配，不要求等尺寸）
    try:
        lo, hi = _get_canny_params(tier)
        e1 = cv2.Canny(roi_c, lo, hi)
        e2 = cv2.Canny(tmpl_c, lo, hi)
        if cv2.countNonZero(e1) >= 20 and cv2.countNonZero(e2) >= 20:
            r3 = cv2.matchTemplate(e1, e2, cv2.TM_CCOEFF_NORMED)
            _, s3, _, _ = cv2.minMaxLoc(r3)
            scores.append(float(s3))
    except cv2.error:
        pass

    # 通道 4：Otsu 二值化（阈值跨帧 EMA 平滑，根治帧间波动）
    try:
        raw_otsu, _ = cv2.threshold(roi_c, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        raw_otsu = float(raw_otsu)
        ema_key = (slot_key, current_res)
        prev = _otsu_threshold_ema.get(ema_key)
        if prev is None:
            _otsu_threshold_ema[ema_key] = raw_otsu
            t = int(raw_otsu)
        else:
            smoothed = _OTSU_EMA_ALPHA * raw_otsu + (1.0 - _OTSU_EMA_ALPHA) * prev
            _otsu_threshold_ema[ema_key] = smoothed
            t = int(smoothed)
        _, b1 = cv2.threshold(roi_c, t, 255, cv2.THRESH_BINARY)
        _, b2 = cv2.threshold(tmpl_c, t, 255, cv2.THRESH_BINARY)
        b1 = cv2.medianBlur(b1, 3)
        b2 = cv2.medianBlur(b2, 3)
        r4 = cv2.matchTemplate(b1, b2, cv2.TM_CCOEFF_NORMED)
        _, s4, _, _ = cv2.minMaxLoc(r4)
        scores.append(float(s4))
    except cv2.error:
        pass

    return max(scores) if scores else 0.0

def _load_roi_config():
    """
    加载 ROI 配置（带缓存机制）
    :return: 配置字典
    """
    global _roi_config_cache, _roi_config_cache_time
    
    current_time = time.time()
    # 如果缓存未过期，直接返回
    if _roi_config_cache is not None and (current_time - _roi_config_cache_time) < _roi_config_cache_ttl:
        return _roi_config_cache
    
    # 缓存过期或不存在，重新加载
    from core.paths import res_path
    config_file = res_path('Config', 'roi_config.json')
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            _roi_config_cache = json.load(f)
        _roi_config_cache_time = current_time
        logger.debug(f"✅ ROI 配置已加载并缓存（TTL: {_roi_config_cache_ttl}s）")
        return _roi_config_cache
    except Exception as e:
        logger.error(f"❌ 读取 ROI 配置失败: {e}")
        return _roi_config_cache if _roi_config_cache else {}

# FLANN 匹配器参数（全局常量）
FLANN_INDEX_KDTREE = 0
FLANN_INDEX_PARAMS = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
FLANN_SEARCH_PARAMS = dict(checks=50)

# 多线程下并发 mss 抓屏可能导致帧错乱或驱动层阻塞，串行化避免「假死/压枪失效」
_mss_capture_lock = threading.RLock()


def _normalize_roi_ltrb(coords):
    """
    将 ROI 统一为 (left, top, right, bottom) 格式。
    
    【坐标格式规范】
    - 配置文件、ROI工具、识别模块 统一使用 (left, top, right, bottom)
    - 背包区域：屏幕绝对坐标
    - 枪械 ROI：相对于背包左上角的相对坐标
    
    不做格式兼容：如果 right <= left 或 bottom <= top，直接返回 None。
    """
    if not isinstance(coords, (list, tuple)) or len(coords) != 4:
        return None
    left, top, right, bottom = coords
    left, top = int(left), int(top)
    right, bottom = int(right), int(bottom)
    if right > left and bottom > top:
        return left, top, right, bottom
    logger.error(f"Invalid ROI coords (right<=left or bottom<=top): {coords}")
    return None

# ✅ 全局缓存：预加载所有模板到内存，避免重复读取磁盘
_template_cache = {}  # {template_path: img_array}

def _load_template_cached(template_path):
    """
    从缓存加载模板，如果不存在则读取并缓存
    :param template_path: 模板文件路径
    :return: 灰度图像数组
    """
    if template_path not in _template_cache:
        img = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            _template_cache[template_path] = img
        else:
            logger.warning(f"无法加载模板: {template_path}")
            return None
    return _template_cache[template_path]


def _ensure_min_size(img, min_dim=200):
    """
    确保图片至少 min_dim 像素，不足时用 Lanczos 插值放大 + 锐化
    
    65×65 的握把图标在 SIFT 下只能检出 1~29 个特征点，
    放大到 200×200 后可提升到 280~500 个，匹配更可靠。
    
    Lanczos 是 OpenCV 最清晰的插值算法，配合锐化核
    可以最大程度减少模糊。
    """
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    if h >= min_dim and w >= min_dim:
        return img
    
    # 计算放大比例，保证最短边达到 min_dim
    scale = max(min_dim / h, min_dim / w)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    
    # Lanczos 插值（目前最好的通用插值算法）
    enlarged = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    
    # 轻微锐化补偿插值模糊
    kernel = np.array([
        [0, -0.5, 0],
        [-0.5, 3, -0.5],
        [0, -0.5, 0]
    ], dtype=np.float32)
    sharpened = cv2.filter2D(enlarged, -1, kernel)
    
    return sharpened


def _match_single_template(args):
    """
    并行化 SIFT 匹配任务（用于 ThreadPoolExecutor）
    :param args: (img1, template_path, template_name, current_res[, slot_key])
    :return: (template_name, score) 或 None
    """
    slot_key = None
    if len(args) == 5:
        img1, template_path, template_name, current_res, slot_key = args
    elif len(args) == 4:
        img1, template_path, template_name, current_res = args
    else:
        img1, template_path, template_name = args
        current_res = None
    img2 = _load_template_cached(template_path)
    
    if img2 is None:
        return None
    
    try:
        score = match_sift(img1, img2, current_res, slot_key=slot_key)
        return (template_name, score)
    except Exception as e:
        from core.process import ProcessClass
        pc = ProcessClass()
        if getattr(pc, 'debug_input_trace', False):
            logger.debug(f"[DEBUG] 模板匹配失败 {template_name}: {e}")
        return None

def MSS_Img(Values):
    """
    截取指定 ROI 区域
    :param Values: 坐标 (left, top, right, bottom) - 严格此格式，不做兼容
    :return: (img_gray, img_np)
    """
    if len(Values) != 4:
        raise ValueError(f"坐标格式错误，期望4个值 (left, top, right, bottom)，收到: {Values}")
    norm = _normalize_roi_ltrb(Values)
    if not norm:
        logger.error(f"无效的 ROI 坐标: {Values}")
        empty_img = np.zeros((100, 100, 3), dtype=np.uint8)
        empty_gray = cv2.cvtColor(empty_img, cv2.COLOR_BGR2GRAY)
        return empty_gray, empty_img
    left, top, right, bottom = norm
    width = right - left
    height = bottom - top
    
    try:
        with _mss_capture_lock:
            with mss.mss() as sct:
                monitor = {"top": top, "left": left, "width": width, "height": height}
                img = sct.grab(monitor)
        img_np = np.array(img)  # 转换为numpy数组

        # 检查图像是否有效
        if img_np is None or img_np.size == 0:
            logger.error(f"截图失败，ROI: {Values}")
            empty_img = np.zeros((height, width, 3), dtype=np.uint8)
            return cv2.cvtColor(empty_img, cv2.COLOR_BGR2GRAY), empty_img

        # 确保是 3 通道图像
        if len(img_np.shape) == 2:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
        elif len(img_np.shape) == 3 and img_np.shape[2] == 4:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)

        img_gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)  # 转换为灰度图

        # 最终验证
        if img_gray is None or img_gray.size == 0:
            logger.error(f"灰度转换失败，ROI: {Values}")
            empty_img = np.zeros((height, width), dtype=np.uint8)
            return empty_img, cv2.cvtColor(empty_img, cv2.COLOR_GRAY2BGR)

        return img_gray, img_np

    except Exception as e:
        logger.error(f"MSS_Img 异常: {e}, ROI: {Values}")
        # 返回默认大小的空图像
        empty_img = np.zeros((max(height, 100), max(width, 100), 3), dtype=np.uint8)
        empty_gray = cv2.cvtColor(empty_img, cv2.COLOR_BGR2GRAY)
        return empty_gray, empty_img

def compute_matches_mask(matches, distance_threshold):
    matchesMask = np.zeros((len(matches), 2), dtype=np.int32)
    matchedPoints1 = 0

    for i in range(len(matches)):
        m, n = matches[i]
        if m.distance < distance_threshold * n.distance:
            matchesMask[i, 0] = 1
            matchedPoints1 += 1

    return matchesMask, matchedPoints1


def _match_icon_hybrid(src, tmpl, tier='large', scale=1.0, slot_key=None, current_res=None):
    """
    分辨率自适应匹配（4K/2K/1080p 自动分流）

    large  (>=4K):  CLAHE + CCOEFF + Sobel + Otsu  (抗背景亮度差异)
    medium (2K):     CLAHE + CCOEFF + CCORR + Sobel  (双路归一化，放弃易噪的 Canny)
    small  (<=1080p): 委托 _match_icon_small           (CCORR + 双边滤波 + 多尺度 ORB)

    Otsu 通道改进（移植自 _match_hud_gun_icon）：
      - 统一阈值：src 和 tmpl 使用同一个 Otsu 阈值做二值化
      - EMA 平滑：同一 slot_key 的阈值跨帧平滑，消除帧间波动
      - 中值滤波：二值化后 medianBlur(3) 去噪

    :param slot_key: 槽位标识（如 'Muzzle_1'），用于 EMA 缓存隔离
    :param current_res: 当前分辨率字符串，用于 EMA 缓存键
    """
    # 尺寸保护：src 任一维小于 tmpl → matchTemplate 会断言失败
    hs, ws = src.shape[:2]
    ht, wt = tmpl.shape[:2]
    if hs < ht or ws < wt:
        return 0.0

    clip_limit, tile_grid = _get_clahe_params(tier, scale)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    src_c = clahe.apply(src)
    tmpl_c = clahe.apply(tmpl)

    # --- 方法1：像素级 TM_CCOEFF_NORMED（所有 tier 共用） ---
    result = cv2.matchTemplate(src_c, tmpl_c, cv2.TM_CCOEFF_NORMED)
    _, score_ccoeff, _, _ = cv2.minMaxLoc(result)

    # --- 小图分支：委托专用 pipeline ---
    if tier == 'small':
        score_small = _match_icon_small(src, tmpl, tier, scale)
        return max(score_ccoeff, score_small)

    # --- 方法2：梯度级匹配（large + medium） ---
    sobel_thresh = 20 if tier == 'large' else 15  # medium 用更低阈值
    score_sobel = _match_icon_sobel(src_c, tmpl_c, sobel_thresh)

    # --- 方法3：Canny 边缘匹配（large + medium，押滤镜端部透明背景） ---
    score_canny = _match_icon_canny(src_c, tmpl_c)

    # --- 中图分支：CCORR_NORMED 替代 Canny（更稳定） ---
    if tier == 'medium':
        score_ccorr = _match_icon_ccorr(src_c, tmpl_c)
        return max(score_ccoeff, score_sobel, score_ccorr, score_canny)

    # --- 大图分支：Otsu 二值化（统一阈值 + EMA 平滑 + 中值滤波） ---
    score_otsu = 0.0
    try:
        raw_otsu, _ = cv2.threshold(src_c, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        raw_otsu = float(raw_otsu)

        if slot_key is not None:
            ema_key = (slot_key, current_res)
            prev = _backpack_otsu_ema.get(ema_key)
            if prev is None:
                _backpack_otsu_ema[ema_key] = raw_otsu
                t = int(raw_otsu)
            else:
                smoothed = _OTSU_EMA_ALPHA * raw_otsu + (1.0 - _OTSU_EMA_ALPHA) * prev
                _backpack_otsu_ema[ema_key] = smoothed
                t = int(smoothed)
        else:
            t = int(raw_otsu)

        _, bin1 = cv2.threshold(src_c, t, 255, cv2.THRESH_BINARY)
        _, bin2 = cv2.threshold(tmpl_c, t, 255, cv2.THRESH_BINARY)
        bin1 = cv2.medianBlur(bin1, 3)
        bin2 = cv2.medianBlur(bin2, 3)
        if cv2.countNonZero(bin1) >= 20 and cv2.countNonZero(bin2) >= 20:
            result_b = cv2.matchTemplate(bin1, bin2, cv2.TM_CCOEFF_NORMED)
            _, score_otsu, _, _ = cv2.minMaxLoc(result_b)
    except cv2.error:
        pass

    return max(score_ccoeff, score_sobel, score_otsu, score_canny)

def match_sift(img1, img2, current_res=None, slot_key=None):
    """
    SIFT 特征匹配
    :param img1: 待匹配的图像（灰度图）
    :param img2: 模板图像（灰度图）
    :param current_res: 当前分辨率字符串（如 '2560x1440'）
    :param slot_key: 槽位标识（如 'Muzzle_1'），用于 Otsu EMA 缓存隔离
    :return: 匹配率
    """
    # 验证输入图像
    if img1 is None or img2 is None:
        logger.warning("match_sift: 输入图像为 None")
        return 0.0
    
    if img1.size == 0 or img2.size == 0:
        logger.warning(f"match_sift: 输入图像为空 - img1.shape={img1.shape if hasattr(img1, 'shape') else 'N/A'}, img2.shape={img2.shape if hasattr(img2, 'shape') else 'N/A'}")
        return 0.0
    
    # 确保是 8 位单通道图像
    if img1.dtype != np.uint8:
        logger.warning(f"match_sift: img1 数据类型错误: {img1.dtype}，转换为 uint8")
        img1 = img1.astype(np.uint8)
    
    if img2.dtype != np.uint8:
        logger.warning(f"match_sift: img2 数据类型错误: {img2.dtype}，转换为 uint8")
        img2 = img2.astype(np.uint8)
    
    # ✅ 小图（任一维度 < 100px）直接用模板匹配 TM_CCOEFF_NORMED
    # SIFT 在 62x65 的图标上特征点太少（0~29个），匹配不可靠
    # 模板匹配在同尺寸图上零特征提取、极快（1ms 10次）、100% 准确
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]
    if (h1 < 100 or w1 < 100) and (h2 < 100 or w2 < 100):
        # 分辨率自适应 pipeline（两路径共用）
        tier, scale = _classify_resolution(current_res) if current_res else ('large', 1.0)
        # 路径1：尺寸完全一致 → 分辨率自适应多通道融合
        if img1.shape == img2.shape:
            score_tm = _match_icon_hybrid(img1, img2, tier, scale, slot_key=slot_key, current_res=current_res)
            score_orb = _match_icon_orb(img1, img2)
            return float(max(score_tm, score_orb))
        
        # 路径2：尺寸在 ±2*PADDING 内 → 滑动窗口匹配
        # ROI 裁剪时每边加了 PADDING px，总差异 = 2*PADDING
        # 用 matchTemplate 滑动窗口找最佳对齐位置，补偿 PUBG 背包 UI 的 ±1~2px 像素抖动
        if abs(h1 - h2) <= 2 * PADDING and abs(w1 - w2) <= 2 * PADDING:
            # 大图为源（滑动窗口 TM），小图为模板
            if h1 >= h2 and w1 >= w2:
                src, tmpl = img1, img2
            else:
                src, tmpl = img2, img1
            score_tm = _match_icon_hybrid(src, tmpl, tier, scale, slot_key=slot_key, current_res=current_res)
            # ORB: 裁取源图中心区域（去掉 padding 边距）
            h_s, w_s = src.shape[:2]
            h_t, w_t = tmpl.shape[:2]
            cy = (h_s - h_t) // 2
            cx = (w_s - w_t) // 2
            src_center = src[cy:cy+h_t, cx:cx+w_t]
            score_orb = _match_icon_orb(src_center, tmpl)
            return float(max(score_tm, score_orb))
    
    # ✅ 使用全局 SIFT 检测器（避免重复创建）
    sift = _get_sift_detector()
    # ✅ 使用全局 FLANN 匹配器（避免重复创建）
    flann = _get_flann_matcher()
    
    try:
        # 查找监测点和匹配符
        kp1, des1 = sift.detectAndCompute(img1, None)
        kp2, des2 = sift.detectAndCompute(img2, None)

        if des1 is not None and len(des1) > 2 and des2 is not None and len(des2) > 2:
            # 使用knnMatch匹配处理，并返回匹配matches
            matches = flann.knnMatch(des1, des2, k=2)
            matches_array = np.array([[m, n] for m, n in matches], dtype=object)

            matchesMask, matchedPoints1 = compute_matches_mask(matches_array, 0.7)

            # ✅ 优化匹配率计算：使用匹配对数作为分母，更准确反映匹配质量
            totalMatches = len(matches)
            matchRate = matchedPoints1 / (totalMatches + 0.1)

            return matchRate
        else:
            return 0.0
            
    except Exception as e:
        logger.error(f"match_sift 异常: {e}")
        return 0.0

async def capture_and_compare(Data):
    """
    异步截取单个 ROI 区域
    :param Data: {key: (left, top, right, bottom)}
    :return: (key, roi_image)
    """
    Keys = list(Data.keys())[0]
    Values = list(Data.values())[0]
    
    # 确保是元组或列表格式
    if not isinstance(Values, (tuple, list)) or len(Values) != 4:
        logger.error(f"ROI 坐标格式错误 {Keys}: {Values}")
        empty_img = np.zeros((50, 50), dtype=np.uint8)
        return Keys, empty_img
    
    norm = _normalize_roi_ltrb(Values)
    if not norm:
        logger.error(f"无效的 ROI 坐标: {Keys}={Values}")
        empty_img = np.zeros((50, 50), dtype=np.uint8)
        return Keys, empty_img
    left, top, right, bottom = norm
    
    # 直接使用 MSS_Img 截取该 ROI 区域
    try:
        img_gray, _ = MSS_Img((left, top, right, bottom))
        logger.debug(f"成功截取 {Keys}: ({left}, {top}, {right}, {bottom}), 尺寸: {img_gray.shape}")
        return Keys, img_gray
    except Exception as e:
        logger.error(f"截取 ROI {Keys} 失败: {e}, 坐标: ({left}, {top}, {right}, {bottom})")
        # 返回空图像
        empty_img = np.zeros((50, 50), dtype=np.uint8)
        return Keys, empty_img

async def capture_all_guns(pathData, current_res=None, gun_name=None):
    """
    识别枪械配件
    :param pathData: {key: img} 待识别的 ROI 图像
    :param current_res: 当前分辨率（如 '2560x1440'）
    :param gun_name: 已识别的枪械名称，用于配件限制过滤
    :return: 识别结果字典
    """
    # ✅ 提前检查调试模式
    from core.process import ProcessClass
    pc = ProcessClass._instance if hasattr(ProcessClass, '_instance') else ProcessClass()
    debug_mode = getattr(pc, 'debug_input_trace', False)
    
    ReturnData = {}
    for mode, img1 in pathData.items():
        if debug_mode:
            logger.debug(f"[DEBUG] 开始识别 {mode}")
        
        # ✅ 配件限制过滤：根据枪械名称跳过不支持的槽位/模板
        slot_type = mode[:-2]  # 'Muzzle_1' -> 'Muzzle'
        if gun_name and slot_type not in ("Name",):
            from data.fire_data import get_allowed_templates
            allowed = get_allowed_templates(gun_name, slot_type)
            if allowed is not None and len(allowed) == 0:
                # 该枪不支持此槽位，直接跳过
                ReturnData[slot_type] = "none"
                if debug_mode:
                    logger.info(f"[配件限制] {mode} 跳过（{gun_name} 不支持 {slot_type}）")
                continue
        else:
            allowed = None
        
        # 验证图像
        if img1 is None or img1.size == 0:
            logger.warning(f"{mode} 图像为空，跳过")
            ReturnData[mode[:-2]] = "None"
            continue
        
        # ✅ 根据分辨率确定模板路径（三级降级）
        # 优先级: 分辨率目录 > 根目录（兼容旧版本）
        match_Path = None
        if current_res:
            # 1. 先尝试使用分辨率特定的模板
            candidate = res_path('_internal', 'data', 'firearms', current_res, mode[:-2]) + os.sep
            if os.path.exists(candidate):
                match_Path = candidate
            else:
                # 2. 降级到根目录（兼容旧版本）
                match_Path = res_path('_internal', 'data', 'firearms', mode[:-2]) + os.sep
        else:
            # 使用根目录（兼容旧版本）
            match_Path = res_path('_internal', 'data', 'firearms', mode[:-2]) + os.sep
        
        if not os.path.exists(match_Path):
            logger.warning(f"模板目录不存在: {match_Path}")
            ReturnData[mode[:-2]] = "None"
            continue
        
        content = os.listdir(match_Path)
        
        # ✅ 类型级过滤：只保留允许的模板文件
        # 大小写归一化：将模板文件名与 allowed 集合统一转小写后比较
        # 防御性措施：避免因模板文件名大小写（如 BanJieShi.png）导致过滤失效
        if allowed is not None and len(allowed) > 0:
            original_count = len(content)
            allowed_lower = {n.lower() for n in allowed}
            content = [f for f in content if f[:-4].lower() in allowed_lower or f[:-4].lower() == "none"]
            if debug_mode:
                logger.info(f"[配件限制] {mode} 模板过滤: {original_count} -> {len(content)} ({gun_name})")
        if debug_mode:
            logger.debug(f"[DEBUG] {mode} 模板目录: {match_Path}")
            logger.debug(f"[DEBUG] {mode} 模板数量: {len(content)}")
        
        # ✅ 并行化 SIFT 匹配（使用线程池）
        from concurrent.futures import ThreadPoolExecutor
        
        # 准备任务列表（传入 current_res + slot_key 以启用 EMA 平滑匹配）
        # 模板名统一转小写，确保与 KEY_DATA_V3/ACCESSORIES_CH 的键匹配
        tasks = [
            (img1, match_Path + each, each[:-4].lower(), current_res, mode)
            for each in content
        ]
        
        MatchValue = 0.0
        MatchName = ""
        scores_detail = []  # 记录每个模板的置信度（调试用）
        
        # ✅ 根据模板数量选择串行或并行
        # 少于 10 个模板时，串行更快（避免线程开销）
        if len(tasks) < 10:
            # 串行模式
            for template_path, _, template_name, res in [(t[1], t[0], t[2], t[3]) for t in tasks]:
                result = _match_single_template((img1, template_path, template_name, res))
                if result:
                    name, score = result
                    scores_detail.append((name, score))
                    if score > MatchValue:
                        MatchName = name
                        MatchValue = score
                        # ✅ 移除提前终止：确保遍历所有模板，找到最佳匹配
        else:
            # 并行模式（根据 CPU 核心数动态调整）
            max_workers = min(os.cpu_count() or 4, len(tasks), 8)  # 最多 8 个线程
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                results = list(executor.map(_match_single_template, tasks))
                
                # 处理结果
                for result in results:
                    if result:
                        name, score = result
                        scores_detail.append((name, score))
                        if score > MatchValue:
                            MatchName = name
                            MatchValue = score
        
        # ✅ 比值驱动阈值：区分度优先，高分兜底
        # 第一名/第二名 ≥ RATIO_THRESHOLD 且分数 ≥ SCORE_FLOOR → 接受
        # 否则分数 ≥ 0.5 → 接受
        scores_detail.sort(key=lambda x: x[1], reverse=True)
        top5 = scores_detail[:5]
        top5_str = ", ".join([f"{n}:{s:.4f}" for n, s in top5])
        
        second_best = top5[1][1] if len(top5) >= 2 else 0.0
        gap = MatchValue - second_best
        ratio = MatchValue / second_best if second_best > 0 else float('inf')
        
        # 分辨率自适应阈值
        tier, scale = _classify_resolution(current_res) if current_res else ('large', 1.0)
        MATCH_THRESHOLD = max(0.38, 0.50 * scale)       # 4K→0.50, 2K→0.33(限0.38), 1080p→0.38
        RATIO_THRESHOLD = max(2.5, 4.0 * scale)         # 4K→4.0, 2K→2.67, 1080p→2.5
        SCORE_FLOOR = max(0.18, 0.25 * scale)            # 4K→0.25, 2K→0.18, 1080p→0.18
        
        accept = False
        if ratio >= RATIO_THRESHOLD and MatchValue >= SCORE_FLOOR:
            accept = True
            if debug_mode:
                logger.info(f"[DEBUG] {mode} 低分高区分度({MatchName}={MatchValue:.4f},ratio={ratio:.1f}x,gap={gap:.4f})")
        elif MatchValue >= _BACKPACK_HIGH_SCORE:
            accept = True
        elif MatchValue >= MATCH_THRESHOLD and gap >= _BACKPACK_GAP_MIN:
            accept = True
        elif MatchValue >= MATCH_THRESHOLD:
            if debug_mode:
                logger.info(f"[DEBUG] {mode} 区分度不足，拒绝({MatchName}={MatchValue:.4f},gap={gap:.4f}<{_BACKPACK_GAP_MIN})")
        
        if debug_mode:
            logger.info(f"[匹配详情] {mode}: 最佳={MatchName}({MatchValue:.4f}) gap={gap:.4f} | Top5: {top5_str}")
        
        if not accept or not MatchName:
            MatchName = "none"
            if debug_mode:
                logger.info(f"[DEBUG] {mode}=none({MatchValue:.4f},gap={gap:.4f})")
        else:
            logger.info(f"{mode}={MatchName}({MatchValue:.4f},gap={gap:.4f})")
        
        ReturnData[mode[:-2]] = MatchName
        
        # ✅ 调试模式：识别完成后，将 ROI 图片保存到 {category}/{result_name}/ 子目录
        # 文件名格式: {result_name}_{timestamp}.png
        # - 目录名 = 结果名（YOLO 分类任务的类别标签，直接符合训练数据规范）
        # - 文件名也带结果名（拖出目录后仍能一眼看出类别，批量确认时无需逐个打开）
        # 目录结构示例: logs/training_data/Muzzle/buqiangbuchang/buqiangbuchang_2026-04-27_17-30-00_123.png
        if debug_mode and img1 is not None and img1.size > 0:
            try:
                from datetime import datetime
                category = mode[:-2]   # 'Muzzle_1' → 'Muzzle'
                base_train_dir = res_path('logs', 'training_data', category, MatchName)
                os.makedirs(base_train_dir, exist_ok=True)
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')[:-3]
                save_path = os.path.join(base_train_dir, f"{MatchName}_{timestamp}.png")
                cv2.imwrite(save_path, img1)
            except Exception:
                pass
    
    return ReturnData

def _crop_backpack_roi(key, coords, backpack_gray, backpack_color, debug_mode):
    """
    从背包大图中裁剪单个 ROI，带 PADDING 边距。
    :return: (roi_gray, roi_color) 或空图
    """
    norm = _normalize_roi_ltrb(coords)
    if not norm:
        logger.error(f"无效 ROI: {key}={coords}")
        empty = np.zeros((50, 50), dtype=np.uint8)
        return empty, cv2.cvtColor(empty, cv2.COLOR_GRAY2BGR)

    left, top, right, bottom = norm
    hs, ws = backpack_gray.shape[:2]
    l_p = max(0, left - PADDING)
    t_p = max(0, top - PADDING)
    r_p = min(ws, right + PADDING)
    b_p = min(hs, bottom + PADDING)
    roi_gray = backpack_gray[t_p:b_p, l_p:r_p]
    roi_color = backpack_color[t_p:b_p, l_p:r_p]

    if roi_gray.size == 0:
        logger.warning(f"裁剪 ROI {key} 为空: ({left},{top},{right},{bottom})")
        empty = np.zeros((50, 50), dtype=np.uint8)
        return empty, cv2.cvtColor(empty, cv2.COLOR_GRAY2BGR)

    if debug_mode:
        logger.debug(
            f"🔄 [DEBUG] {key}: 相对坐标({left},{top},{right},{bottom}), "
            f"尺寸: {right-left}x{bottom-top}, 截图尺寸: {roi_gray.shape}"
        )
        # 保存原始 ROI 图片（按槽位分组，不含识别结果，用于 ROI 框位置调试）
        try:
            from datetime import datetime
            base_debug_dir = res_path('logs', 'roi_debug')
            category = key.split('_')[0]
            slot = key.split('_')[1] if '_' in key else ''
            category_dir = os.path.join(base_debug_dir, f'{category}_{slot}')
            os.makedirs(category_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            cv2.imwrite(os.path.join(category_dir, f"{timestamp}.png"), roi_color)
        except Exception:
            pass

    return roi_gray, roi_color


async def _recognize_single_frame(backpack_gray, backpack_color, Guns_img, current_res, debug_mode, is_last_frame):
    """
    对单帧背包大图执行两阶段识别。
    :param is_last_frame: 是否最后一帧（仅最后一帧保存调试 ROI 截图，避免重复保存）
    :return: (result_slot1_dict, result_slot2_dict)
    """
    from data.fire_data import get_allowed_slots

    save_debug = debug_mode and is_last_frame

    # 阶段1: Name
    name_rois_1, name_rois_2 = {}, {}
    if "Name_1" in Guns_img:
        roi_gray, _ = _crop_backpack_roi("Name_1", Guns_img["Name_1"], backpack_gray, backpack_color, save_debug)
        name_rois_1["Name_1"] = roi_gray
    if "Name_2" in Guns_img:
        roi_gray, _ = _crop_backpack_roi("Name_2", Guns_img["Name_2"], backpack_gray, backpack_color, save_debug)
        name_rois_2["Name_2"] = roi_gray

    name_r1, name_r2 = await asyncio.gather(
        capture_all_guns(name_rois_1, current_res, gun_name=None),
        capture_all_guns(name_rois_2, current_res, gun_name=None),
    )
    gun_name_1 = name_r1.get('Name')
    gun_name_2 = name_r2.get('Name')

    # 阶段2: 根据枪名裁剪/识别配件
    def _build_acc_rois(slot_suffix, gun_name):
        allowed_slots = get_allowed_slots(gun_name)
        rois = {}
        for key, coords in Guns_img.items():
            if key == "posture_roi" or not key.endswith(slot_suffix):
                continue
            slot_type = key[:-len(slot_suffix)]
            if slot_type == "Name":
                continue
            if allowed_slots is not None and slot_type not in allowed_slots:
                continue
            roi_gray, _ = _crop_backpack_roi(key, coords, backpack_gray, backpack_color, save_debug)
            rois[key] = roi_gray
        return rois

    acc_rois_1 = _build_acc_rois('_1', gun_name_1)
    acc_rois_2 = _build_acc_rois('_2', gun_name_2)

    acc_r1, acc_r2 = await asyncio.gather(
        capture_all_guns(acc_rois_1, current_res, gun_name=gun_name_1),
        capture_all_guns(acc_rois_2, current_res, gun_name=gun_name_2),
    )

    return {**name_r1, **acc_r1}, {**name_r2, **acc_r2}


def _vote_frame_results(results_list, debug_mode):
    """
    对多帧识别结果做 majority vote（按字段独立投票）。
    :param results_list: [dict, dict, ...] 每帧同一槽位的识别结果
    :return: 投票后的结果字典
    """
    if not results_list:
        return {}
    all_keys = set()
    for r in results_list:
        all_keys.update(r.keys())

    voted = {}
    for key in all_keys:
        values = [r.get(key, "none") for r in results_list]
        counter = Counter(values)
        top_val, top_count = counter.most_common(1)[0]
        voted[key] = top_val
        if debug_mode and top_count < len(results_list):
            logger.info(f"[多帧投票] {key}: {dict(counter)} → {top_val} ({top_count}/{len(results_list)}票)")
    return voted


async def capture_all_positions_thread(current_res, resolution_settings=None, guns_resolution_settings=None):
    """
    多帧两阶段背包识别：
      1. 快速截取 MULTI_FRAME_COUNT 帧背包大图（帧间隔 MULTI_FRAME_INTERVAL）
      2. 对每帧独立做两阶段识别（先枪名 → 再配件）
      3. 对多帧结果按字段 majority vote，消除单帧噪声
    适用于 FPS 游戏：单次 Tab 即可得到稳定结果，不依赖跨次 Tab 累积历史。
    """
    start_time = time.time()

    # 每次 Tab 清空背包 Otsu EMA 缓存，避免上次 Tab 的历史阈值干扰本次识别
    clear_backpack_otsu_ema()

    from core.process import ProcessClass
    pc = ProcessClass._instance if hasattr(ProcessClass, '_instance') else ProcessClass()
    debug_mode = getattr(pc, 'debug_input_trace', False)

    if debug_mode:
        logger.info(f"🔍 [DEBUG] 开始多帧两阶段识别（{MULTI_FRAME_COUNT}帧），分辨率: {current_res}")

    user_config = _load_roi_config()
    if not user_config:
        logger.error("❌ ROI 配置为空")
        return [{}, {}]

    Guns_img = user_config.get(current_res, {})
    backpack_roi = user_config.get('_GUNS_REOLUTION_SETTINGS', {}).get(current_res)
    if not backpack_roi:
        logger.warning(f"⚠️ 未找到分辨率 {current_res} 的背包区域配置（必需）")
        return [{}, {}]

    norm_backpack = _normalize_roi_ltrb(backpack_roi)
    if not norm_backpack:
        logger.error(f"无效的背包 ROI: {backpack_roi}")
        return [{}, {}]

    # ══════════════════════════════════════════════════
    # 快速截取多帧背包大图
    # ══════════════════════════════════════════════════
    frames = []
    for i in range(MULTI_FRAME_COUNT):
        try:
            bg, bc = MSS_Img(norm_backpack)
            frames.append((bg, bc))
        except Exception as e:
            logger.error(f"第{i+1}帧截图失败: {e}")
        if i < MULTI_FRAME_COUNT - 1:
            time.sleep(MULTI_FRAME_INTERVAL)

    if not frames:
        logger.error("所有帧截图均失败")
        return [{}, {}]

    t_capture = time.time() - start_time
    logger.info(f"✅ 成功截取 {len(frames)} 帧背包大图 (耗时: {t_capture:.3f}s)")

    # ══════════════════════════════════════════════════
    # 对每帧独立做两阶段识别
    # ══════════════════════════════════════════════════
    t_recognize = time.time()
    all_results = []  # [(slot1_dict, slot2_dict), ...]

    for frame_idx, (bg, bc) in enumerate(frames):
        is_last = (frame_idx == len(frames) - 1)
        r1, r2 = await _recognize_single_frame(bg, bc, Guns_img, current_res, debug_mode, is_last)
        all_results.append((r1, r2))
        if debug_mode:
            logger.info(f"[多帧F{frame_idx+1}/{len(frames)}] 槽1={r1}, 槽2={r2}")

    # ══════════════════════════════════════════════════
    # 多帧投票（按字段独立 majority vote）
    # ══════════════════════════════════════════════════
    final_1 = _vote_frame_results([r[0] for r in all_results], debug_mode)
    final_2 = _vote_frame_results([r[1] for r in all_results], debug_mode)

    elapsed = time.time() - start_time
    t_recog = time.time() - t_recognize
    logger.info(
        "⏱️ 多帧识别耗时: %.2f 秒 [截图%d帧: %.3fs, 识别+投票: %.3fs]",
        elapsed, len(frames), t_capture, t_recog,
    )

    if debug_mode:
        logger.info(f"[多帧投票] 最终结果: 槽1={final_1}, 槽2={final_2}")

    return [final_1, final_2]

def recogniseif_firearm(current_res):
    """识别是否开镜（通过像素颜色检测）"""
    import json
    from core.paths import res_path
    
    # ✅ 从 roi_config.json 读取开镜坐标
    config_file = res_path('Config', 'roi_config.json')
    click_pos = None
    
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                roi_config = json.load(f)
            # 从 _CLICK_POSITION 读取开镜坐标
            click_positions = roi_config.get('_CLICK_POSITION', {})
            click_pos = click_positions.get(current_res)
    except Exception as e:
        logger.error(f"读取开镜坐标失败: {e}")
    
    if not click_pos:
        logger.warning(f"未找到分辨率 {current_res} 的开镜坐标")
        return False
    
    x1, x2 = click_pos
    # 使用Pillow库获取屏幕像素颜色
    screenshot = ImageGrab.grab(bbox=(x1, x2, x1 + 1, x2 + 1))
    r, g, b = screenshot.getpixel((0, 0))
    S_Max, S_Min = 255, 200
    if S_Min <= g <= S_Max and S_Min <= r <= S_Max and S_Min <= b <= S_Max:
        return True
    else:
        return False


def capture_hud_area(hud_roi):
    """
    截取 HUD 区域大图（一次截图）
    :param hud_roi: (left, top, right, bottom) - HUD 枪械图标区域包围框（屏幕绝对坐标）
    :return: (hud_gray, hud_color) 或 (None, None) 如果失败
    """
    if not hud_roi or len(hud_roi) != 4:
        logger.error(f"HUD ROI 坐标无效: {hud_roi}")
        return None, None
    
    norm = _normalize_roi_ltrb(hud_roi)
    if not norm:
        logger.error(f"无效的 HUD ROI 坐标: {hud_roi}")
        return None, None
    
    left, top, right, bottom = norm
    width = right - left
    height = bottom - top
    
    try:
        with _mss_capture_lock:
            with mss.mss() as sct:
                monitor = {"top": top, "left": left, "width": width, "height": height}
                img = sct.grab(monitor)
        img_np = np.array(img)
        
        if img_np is None or img_np.size == 0:
            logger.error(f"HUD 截图失败，ROI: {hud_roi}")
            return None, None
        
        # BGRA → BGR → Gray
        img_color = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
        img_gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
        
        return img_gray, img_color
    except Exception as e:
        logger.error(f"HUD 截图异常: {e}")
        return None, None


def _crop_from_image(img_gray, img_color, roi):
    """
    从已截取的图像中裁剪出子 ROI（相对坐标）
    :param img_gray: 灰度图
    :param img_color: 彩色图
    :param roi: (left, top, right, bottom) - 相对于 HUD 大图的坐标（可以是相对或绝对）
    :return: (roi_gray, roi_color) 或 (None, None)
    """
    if not roi or len(roi) != 4:
        return None, None
    
    left, top, right, bottom = roi
    
    # ✅ 裁剪时加 PADDING 边距，用于补偿 HUD UI 抖动导致的 ±1~2px 偏移
    # matchTemplate 滑动窗口会自动找最佳对齐位置（与背包配件识别算法一致）
    h, w = img_gray.shape[:2]
    left_pad = max(0, left - PADDING)
    top_pad = max(0, top - PADDING)
    right_pad = min(w, right + PADDING)
    bottom_pad = min(h, bottom + PADDING)
    
    roi_color = img_color[top_pad:bottom_pad, left_pad:right_pad]
    roi_gray = img_gray[top_pad:bottom_pad, left_pad:right_pad]
    
    # 验证裁剪结果
    if roi_gray.size == 0:
        logger.warning(f"裁剪 ROI 为空: ({left},{top},{right},{bottom})")
        return None, None
    
    return roi_gray, roi_color


def capture_gun_icons(current_res):
    """
    从 HUD 右下角截取枪械图标，识别两把枪械名称并通过亮度判断当前使用的枪械
    
    优化方案：先截取 HUD 大图（一次 mss 调用），再裁剪两个 ROI（纯 NumPy 操作）
    
    :param current_res: 当前分辨率（如 '3840x2160'）
    :return: {"Gun_1": name, "Gun_2": name, "active": 1|2} 或 None
    """
    from core.process import ProcessClass
    pc = ProcessClass._instance if hasattr(ProcessClass, '_instance') else ProcessClass()
    debug_mode = getattr(pc, 'debug_input_trace', False)
    
    # 1. 读取 HUD 枪械图标区域配置（从独立配置节点读取，类似背包区域）
    user_config = _load_roi_config()
    
    # 读取 HUD 包围框（屏幕绝对坐标，类似 _GUNS_REOLUTION_SETTINGS）
    hud_settings = user_config.get('_GUN_HUD_SETTINGS', {})
    hud_roi = hud_settings.get(current_res)
    
    # 读取 Gun_1 和 Gun_2（相对于 hud_roi 的坐标，在分辨率配置下）
    res_config = user_config.get(current_res, {})
    gun1_roi_rel = res_config.get('Gun_1')
    gun2_roi_rel = res_config.get('Gun_2')
    
    if not hud_roi or not gun1_roi_rel or not gun2_roi_rel:
        logger.warning(f"未找到分辨率 {current_res} 的 HUD 枪械图标配置: _GUN_HUD_SETTINGS={hud_roi}, Gun_1={gun1_roi_rel}, Gun_2={gun2_roi_rel}")
        return None
    
    # 2. 截取 HUD 大图（仅一次 mss 调用）
    hud_gray, hud_color = capture_hud_area(hud_roi)
    if hud_gray is None:
        logger.error(f"截取 HUD 大图失败: {hud_roi}")
        return None
    
    if debug_mode:
        logger.info(f"[枪械图标] HUD 大图截取成功: {hud_gray.shape[1]}x{hud_gray.shape[0]}")
    
    # 3. 从 HUD 大图中裁剪两个枪械图标 ROI（纯 NumPy 操作，零开销）
    gun1_gray, gun1_color = _crop_from_image(hud_gray, hud_color, gun1_roi_rel)
    gun2_gray, gun2_color = _crop_from_image(hud_gray, hud_color, gun2_roi_rel)
    
    if gun1_gray is None or gun2_gray is None:
        logger.error(f"从 HUD 大图中裁剪 ROI 失败: Gun_1={gun1_roi_rel}, Gun_2={gun2_roi_rel}")
        return None
    
    if debug_mode:
        logger.info(f"[枪械图标] ROI 裁剪成功: Gun_1={gun1_gray.shape}, Gun_2={gun2_gray.shape}")
        logger.info(f"[枪械图标] ROI 配置: Gun_1={gun1_roi_rel}, Gun_2={gun2_roi_rel}")
        logger.info(f"[枪械图标] HUD 包围框: {hud_roi}")
    
    # 4. 亮度仅用于调试日志（不再参与枪位决策；当前持枪由按键 1/2 驱动）
    brightness_1 = float(np.mean(gun1_gray))
    brightness_2 = float(np.mean(gun2_gray))
    if debug_mode:
        logger.info(f"[枪械图标] 亮度: Gun_1={brightness_1:.1f}, Gun_2={brightness_2:.1f} (仅调试，不判活)")
    
    # 5. 加载枪械图标模板
    gun_template_dir = None
    candidate = res_path('_internal', 'data', 'firearms', current_res, 'gun')
    if os.path.exists(candidate):
        gun_template_dir = candidate
        if debug_mode:
            logger.info(f"[枪械图标] 使用分辨率特定模板: {candidate}")
    else:
        # 降级到根目录
        fallback = res_path('_internal', 'data', 'firearms', 'gun')
        if os.path.exists(fallback):
            gun_template_dir = fallback
            if debug_mode:
                logger.info(f"[枪械图标] 降级使用根目录模板: {fallback}")
    
    if not gun_template_dir:
        logger.warning("枪械图标模板目录不存在")
        return {"Gun_1": "none", "Gun_2": "none"}
    
    # 枚举所有模板文件（.bmp 和 .png）
    template_files = [f for f in os.listdir(gun_template_dir) 
                      if f.lower().endswith(('.bmp', '.png'))]
    
    if not template_files:
        logger.warning(f"枪械图标模板目录为空: {gun_template_dir}")
        return {"Gun_1": "none", "Gun_2": "none"}
    
    if debug_mode:
        logger.info(f"[枪械图标] 模板目录: {gun_template_dir}")
        logger.info(f"[枪械图标] 模板文件列表: {template_files}")
        logger.info(f"[枪械图标] 模板总数: {len(template_files)}")
    
    # 5. 对两把枪分别进行模板匹配
    tier, scale = _classify_resolution(current_res) if current_res else ('large', 1.0)
    results = {}
    
    if debug_mode:
        logger.info(f"[枪械图标] 分辨率等级: {tier}, 缩放比例: {scale:.2f}")
    
    for slot_key, roi_gray, roi_color in [("Gun_1", gun1_gray, gun1_color), ("Gun_2", gun2_gray, gun2_color)]:
        best_name = "none"
        best_score = 0.0
        scores_detail = []
        
        if debug_mode:
            logger.info(f"[枪械图标] ===== 开始匹配 {slot_key} =====")
            logger.info(f"[枪械图标] {slot_key} ROI 尺寸: {roi_gray.shape[1]}x{roi_gray.shape[0]} (宽x高)")
        
        matched_count = 0
        skipped_count = 0
        
        for tmpl_file in template_files:
            tmpl_path = os.path.join(gun_template_dir, tmpl_file)
            tmpl_img = _load_template_cached(tmpl_path)
            if tmpl_img is None:
                continue
            
            # 使用 CLAHE + TM_CCOEFF_NORMED 进行匹配
            # 枪械图标尺寸较大 (~284x104)，用 matchTemplate 滑动窗口
            hs, ws = roi_gray.shape[:2]
            ht, wt = tmpl_img.shape[:2]
            
            if hs < ht or ws < wt:
                # ROI 比模板小，跳过
                skipped_count += 1
                if debug_mode:
                    logger.debug(f"[枪械图标]   跳过 {tmpl_file}: 模板尺寸({wt}x{ht}) > ROI尺寸({ws}x{hs})")
                continue
            
            # ✅ 多通道融合匹配（CLAHE + Sobel + Canny + Otsu EMA）
            # 任一通道失效不影响整体判断，Otsu 阈值跨帧平滑根治分数波动
            score = _match_hud_gun_icon(roi_gray, tmpl_img, tier, scale, slot_key, current_res)
            
            tmpl_name = os.path.splitext(tmpl_file)[0]  # 去掉扩展名
            scores_detail.append((tmpl_name, score))
            
            if score > best_score:
                best_score = score
                best_name = tmpl_name
                matched_count += 1
                if debug_mode:
                    logger.debug(f"[枪械图标]   {tmpl_file}: {score:.4f} ★ 新的最佳匹配")
            elif debug_mode and score > 0.3:
                logger.debug(f"[枪械图标]   {tmpl_file}: {score:.4f}")
        
        if debug_mode:
            logger.info(f"[枪械图标] {slot_key} 匹配统计: 成功匹配{matched_count}个, 跳过{skipped_count}个")
        
        # ✅ 判定门槛：绝对阈值 + 区分度 (Top1-Top2 gap) 双保险
        # - 高分线（score >= _HUD_HIGH_SCORE）：直接接受
        # - 中等分 + 高 gap：接受（区分度满足）
        # - 中等分 + 低 gap：拒绝（防止误识）
        scores_detail.sort(key=lambda x: x[1], reverse=True)
        MATCH_THRESHOLD = max(0.38, 0.50 * scale)
        second_best = scores_detail[1][1] if len(scores_detail) >= 2 else 0.0
        gap = best_score - second_best
        
        if debug_mode:
            logger.info(f"[枪械图标] {slot_key} 判定阈值: {MATCH_THRESHOLD:.4f} (基于 scale={scale:.2f}), gap门槛={_HUD_GAP_MIN}, 高分线={_HUD_HIGH_SCORE}")
        
        # 分级接受逻辑
        accept = False
        reject_reason = ""
        if best_score >= _HUD_HIGH_SCORE:
            accept = True
        elif best_score >= MATCH_THRESHOLD and gap >= _HUD_GAP_MIN:
            accept = True
        elif best_score >= MATCH_THRESHOLD:
            reject_reason = f"区分度不足(gap={gap:.4f}<{_HUD_GAP_MIN})"
        else:
            reject_reason = f"分数低于阈值({best_score:.4f}<{MATCH_THRESHOLD:.4f})"
        
        if accept:
            results[slot_key] = best_name
            if debug_mode:
                logger.info(f"[枪械图标] {slot_key} ✅ 匹配成功: {best_name} (置信度={best_score:.4f}, gap={gap:.4f})")
        else:
            results[slot_key] = "none"
            if debug_mode:
                logger.warning(f"[枪械图标] {slot_key} ❌ 匹配失败: 最佳={best_name}({best_score:.4f}), 理由={reject_reason}")
        
        if debug_mode:
            top5 = scores_detail[:5]
            top5_str = ", ".join([f"{n}:{s:.4f}" for n, s in top5])
            logger.info(f"[枪械图标] {slot_key} Top5: {top5_str}")
            
            # 输出置信度差距分析
            if len(scores_detail) >= 2:
                gap = scores_detail[0][1] - scores_detail[1][1]
                logger.info(f"[枪械图标] {slot_key} 置信度差距: Top1-Top2 = {gap:.4f} ({'明显' if gap > 0.1 else '接近'})")
        
        if results[slot_key] != "none":
            logger.info(f"枪械图标 {slot_key}={results[slot_key]}({best_score:.4f})")
    
    # ✅ 多帧共识投票：当前帧识别与历史不一致时，用共识结果兜底
    # 目的：拒绝单帧误识导致压枪数据错乱，唯有近 N 帧达成共识才切枪
    for slot_key in ("Gun_1", "Gun_2"):
        hist = _hud_slot_history[slot_key]
        hist.append(results[slot_key])
        if len(hist) > _HUD_CONSENSUS_WINDOW:
            hist.pop(0)
        
        # 共识投票：窗口内最高频结果
        if len(hist) >= _HUD_CONSENSUS_MIN_VOTES:
            top, count = Counter(hist).most_common(1)[0]
            # 当前帧与共识结果不一致 且 共识达成最小票数 → 用共识结果覆盖
            if count >= _HUD_CONSENSUS_MIN_VOTES and top != results[slot_key]:
                if debug_mode:
                    logger.info(f"[HUD CONSENSUS] {slot_key} {results[slot_key]}→{top} (窗口{_HUD_CONSENSUS_WINDOW}帧中{count}票)")
                results[slot_key] = top
    
    # 6. 调试模式：保存 HUD 截图和匹配结果分析（按类型分组）
    if debug_mode:
        try:
            from datetime import datetime
            base_debug_dir = res_path('logs', 'roi_debug')
            os.makedirs(base_debug_dir, exist_ok=True)
            
            # 时间戳格式：精确到秒，可读格式
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            
            # 按类型创建子目录
            gun1_dir = os.path.join(base_debug_dir, 'Gun_1_ROI')
            gun2_dir = os.path.join(base_debug_dir, 'Gun_2_ROI')
            result_dir = os.path.join(base_debug_dir, 'Recognition_Results')
            
            os.makedirs(gun1_dir, exist_ok=True)
            os.makedirs(gun2_dir, exist_ok=True)
            os.makedirs(result_dir, exist_ok=True)
            
            # 保存原始 ROI 截图（按类型分组）
            cv2.imwrite(os.path.join(gun1_dir, f"{timestamp}.png"), gun1_color)
            cv2.imwrite(os.path.join(gun2_dir, f"{timestamp}.png"), gun2_color)
            
            # 保存匹配结果摘要
            result_summary = (
                f"时间: {timestamp}\n"
                f"分辨率: {current_res}\n"
                f"HUD 包围框: {hud_roi}\n"
                f"Gun_1 ROI: {gun1_roi_rel} -> 识别: {results.get('Gun_1', 'none')}\n"
                f"Gun_2 ROI: {gun2_roi_rel} -> 识别: {results.get('Gun_2', 'none')}\n"
                f"当前枪械: 由按键驱动（HUD 不再判活）\n"
                f"亮度(仅调试): Gun_1={brightness_1:.1f}, Gun_2={brightness_2:.1f}"
            )
            summary_file = os.path.join(result_dir, f"{timestamp}.txt")
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(result_summary)
            
            logger.info(f"[枪械图标] 调试信息已保存: {base_debug_dir}")
            logger.info(f"[枪械图标]   - Gun_1 ROI: {gun1_dir}")
            logger.info(f"[枪械图标]   - Gun_2 ROI: {gun2_dir}")
            logger.info(f"[枪械图标]   - 识别结果: {result_dir}")
        except Exception as e:
            logger.debug(f"保存枪械图标调试图失败: {e}")
    
    return results

