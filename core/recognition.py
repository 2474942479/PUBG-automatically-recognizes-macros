import cv2
import json
import logging
import mss
import os
import threading
import time
import asyncio
import numpy as np
from PIL import ImageGrab

from core.paths import res_path
# ✅ 不再从 data.resolution_setting 导入，由调用方传入配置
# from data.resolution_setting import RESOLUTION_SETTINGS, GUNS_REOLUTION_SETTINGS, Click

logger = logging.getLogger(__name__)

# 全局 SIFT 检测器（避免重复创建）
_sift_detector = None
# ✅ 全局 FLANN 匹配器（避免重复创建）
_flann_matcher = None
# ✅ 全局 ROI 配置缓存
_roi_config_cache = None
_roi_config_cache_time = 0
_roi_config_cache_ttl = 60  # 缓存 60 秒

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
    :param args: (img1, template_path, template_name)
    :return: (template_name, score) 或 None
    """
    img1, template_path, template_name = args
    img2 = _load_template_cached(template_path)
    
    if img2 is None:
        return None
    
    try:
        score = match_sift(img1, img2)
        return (template_name, score)
    except Exception as e:
        # ✅ 只在调试模式下记录异常
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

def match_sift(img1, img2):
    """
    SIFT 特征匹配
    :param img1: 待匹配的图像（灰度图）
    :param img2: 模板图像（灰度图）
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
    # SIFT 在 62×65 的图标上特征点太少（0~29个），匹配不可靠
    # 模板匹配在同尺寸图上零特征提取、极快（1ms 10次）、100% 准确
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]
    if (h1 < 100 or w1 < 100) and (h2 < 100 or w2 < 100):
        if img1.shape == img2.shape:
            # ✅ CLAHE 自适应直方图均衡化，减少 PUBG 背包半透明背景透色差异
            clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4))
            img1 = clahe.apply(img1)
            img2 = clahe.apply(img2)
            result = cv2.matchTemplate(img1, img2, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            return float(score)
        # 尺寸不一致 → 降级到 SIFT（不同分辨率模板间用特征匹配）
    
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

async def capture_all_guns(pathData, current_res=None):
    """
    识别枪械配件
    :param pathData: {key: img} 待识别的 ROI 图像
    :param current_res: 当前分辨率（如 '2560x1440'）
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
        if debug_mode:
            logger.debug(f"[DEBUG] {mode} 模板目录: {match_Path}")
            logger.debug(f"[DEBUG] {mode} 模板数量: {len(content)}")
        
        # ✅ 并行化 SIFT 匹配（使用线程池）
        from concurrent.futures import ThreadPoolExecutor
        
        # 准备任务列表
        tasks = [
            (img1, match_Path + each, each[:-4])
            for each in content
        ]
        
        MatchValue = 0.0
        MatchName = ""
        
        # ✅ 根据模板数量选择串行或并行
        # 少于 10 个模板时，串行更快（避免线程开销）
        if len(tasks) < 10:
            # 串行模式
            for template_path, _, template_name in [(t[1], t[0], t[2]) for t in tasks]:
                result = _match_single_template((img1, template_path, template_name))
                if result:
                    name, score = result
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
                        if score > MatchValue:
                            MatchName = name
                            MatchValue = score
        
        # ✅ 提高最低阈值，避免误识别（0.10 → 0.18）
        MATCH_THRESHOLD = 0.18
        
        if MatchValue < MATCH_THRESHOLD or not MatchName:
            MatchName = "none"
            if debug_mode:
                logger.info(f"[DEBUG] {mode} 识别结果: none (置信度 {MatchValue:.4f} < 阈值 {MATCH_THRESHOLD})")
        else:
            logger.info(f"{mode} 识别结果: {MatchName} (置信度: {MatchValue:.4f})")
        
        ReturnData[mode[:-2]] = MatchName
    
    return ReturnData

async def capture_all_positions_thread(current_res, resolution_settings=None, guns_resolution_settings=None):
    """
    捕获所有位置的图像并进行识别
    :param current_res: 当前分辨率
    :param resolution_settings: ROI 配置字典（未使用，直接读取JSON）
    :param guns_resolution_settings: 背包区域配置字典（未使用，直接读取JSON）
    """
    start_time = time.time()
    
    # ✅ 提前检查调试模式，避免重复查询
    from core.process import ProcessClass
    pc = ProcessClass._instance if hasattr(ProcessClass, '_instance') else ProcessClass()
    debug_mode = getattr(pc, 'debug_input_trace', False)
    
    if debug_mode:
        logger.info(f"🔍 [DEBUG] 开始枪械识别，分辨率: {current_res}")
    
    # ✅ 使用缓存的 ROI 配置（避免重复读取 JSON）
    user_config = _load_roi_config()
    
    if not user_config:
        logger.error(f"❌ ROI 配置为空")
        return [{}, {}]
    
    # 提取当前分辨率的 ROI 配置
    Guns_img = user_config.get(current_res, {})
    
    # 提取背包区域配置（✅ 用于截取大图）
    backpack_roi = user_config.get('_GUNS_REOLUTION_SETTINGS', {}).get(current_res)
    
    if not backpack_roi:
        logger.warning(f"⚠️  未找到分辨率 {current_res} 的背包区域配置（必需）")
        return [{}, {}]
    
    # ✅ 性能优化：先截取背包大图（1次 mss.grab）
    norm_backpack = _normalize_roi_ltrb(backpack_roi)
    if not norm_backpack:
        logger.error(f"无效的背包 ROI: {backpack_roi}")
        return [{}, {}]
    
    try:
        backpack_gray, backpack_color = MSS_Img(norm_backpack)
        logger.debug(f"✅ 截取背包大图成功: {backpack_gray.shape}")
    except Exception as e:
        logger.error(f"截取背包大图失败: {e}")
        return [{}, {}]
    
    # ✅ 从大图中裁剪各个 ROI（numpy 切片，零开销）
    captured_images = []
    for key, coords in Guns_img.items():
        try:
            if key == "posture_roi":
                continue
            
            # 解析 ROI 坐标（相对于背包大图的相对坐标）
            norm = _normalize_roi_ltrb(coords)
            if not norm:
                logger.error(f"无效 ROI: {key}={coords}")
                empty_img = np.zeros((50, 50), dtype=np.uint8)
                captured_images.append((key, empty_img))
                continue
            
            left, top, right, bottom = norm
            
            # ✅ 从背包大图中裁剪 ROI（numpy 切片，极快）
            roi_gray = backpack_gray[top:bottom, left:right]
            roi_color = backpack_color[top:bottom, left:right]
            
            # 验证裁剪结果
            if roi_gray.size == 0:
                logger.warning(f"裁剪 ROI {key} 为空: ({left},{top},{right},{bottom})")
                empty_img = np.zeros((50, 50), dtype=np.uint8)
                captured_images.append((key, empty_img))
                continue
            
            captured_images.append((key, roi_gray))
            
            if debug_mode:
                width = right - left
                height = bottom - top
                logger.debug(f"🔄 [DEBUG] {key}: 相对坐标({left},{top},{right},{bottom}), 尺寸: {width}x{height}, 截图尺寸: {roi_gray.shape}")
                
                # ✅ 调试模式：保存截取的 ROI 图片
                try:
                    from datetime import datetime
                    debug_dir = res_path('logs', 'roi_debug')
                    os.makedirs(debug_dir, exist_ok=True)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    save_path = os.path.join(debug_dir, f"{key}_{timestamp}.png")
                    cv2.imwrite(save_path, roi_color)
                    logger.debug(f"💾 [DEBUG] 已保存 ROI 图: {save_path}")
                except Exception as e:
                    logger.debug(f"保存 ROI 调试图失败: {e}")
            
        except Exception as e:
            logger.error(f"裁剪 ROI {key} 失败: {e}")
            empty_img = np.zeros((50, 50), dtype=np.uint8)
            captured_images.append((key, empty_img))
    
    t_capture = time.time() - start_time
    logger.info(f"✅ 成功截取 {len(captured_images)} 个 ROI 区域 (耗时: {t_capture:.3f}s)")

    # 将捕获的图像数据分组
    Guns1 = {k: img for k, img in captured_images[0:5]}
    Guns2 = {k: img for k, img in captured_images[5:10]}

    # 对这些图像进行进一步处理
    t_match = time.time()
    ReturnData = await asyncio.gather(
        capture_all_guns(Guns1, current_res),  # ✅ 传入分辨率
        capture_all_guns(Guns2, current_res)   # ✅ 传入分辨率
    )
    match_time = time.time() - t_match
    
    # 发送识别结果到 UI
    try:
        from core.process import PC as ProcessPC
        if hasattr(ProcessPC, '_ui_log_callback') and ProcessPC._ui_log_callback:
            result_summary = []
            for data in ReturnData:
                for key, value in data.items():
                    result_summary.append(f"{key}: {value}")
            ProcessPC._ui_log_callback(f"✅ 识别完成: {', '.join(result_summary)}")
    except Exception:
        pass

    elapsed_time = time.time() - start_time  # 计算总耗时
    logger.info("⏱️ 枪械识别耗时: %.2f 秒 [截图: %.3fs, 匹配: %.3fs]", 
                elapsed_time, t_capture if 't_capture' in locals() else 0, match_time if 'match_time' in locals() else 0)

    return ReturnData

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

