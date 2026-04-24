import cv2
import logging
import mss
import os
import threading
import time
import asyncio
import numpy as np
from PIL import ImageGrab

from core.paths import res_path
from data.resolution_setting import RESOLUTION_SETTINGS, GUNS_REOLUTION_SETTINGS, Click

logger = logging.getLogger(__name__)

# 多线程下并发 mss 抓屏可能导致帧错乱或驱动层阻塞，串行化避免「假死/压枪失效」
_mss_capture_lock = threading.RLock()


def _normalize_roi_ltrb(coords):
    """
    将 ROI 统一为 (left, top, right, bottom)。

    仅当按 (left, top, right, bottom) 解出的宽或高 <= 0 时，再按 (left, top, width, height) 解释。
    不得再用「宽和高都 < 100」等启发式：倍镜等合法区域常小于 100px，误当 w/h 会导致裁切错误、识别全崩。
    """
    if not isinstance(coords, (list, tuple)) or len(coords) != 4:
        return None
    left, top, c, d = coords
    left, top = int(left), int(top)
    c, d = int(c), int(d)
    right, bottom = c, d
    width = right - left
    height = bottom - top
    if width > 0 and height > 0:
        return left, top, right, bottom
    w, h = c, d
    if w > 0 and h > 0:
        return left, top, left + w, top + h
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
        logger.debug(f"模板匹配失败 {template_name}: {e}")
        return None

def MSS_Img(Values):
    """
    截取指定 ROI 区域
    :param Values: 坐标 (left, top, right, bottom)；若宽/高非正则按 (left, top, w, h) 解释
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
    
    # 创建sift检测器
    sift = cv2.SIFT_create()
    
    try:
        # 查找监测点和匹配符
        kp1, des1 = sift.detectAndCompute(img1, None)
        kp2, des2 = sift.detectAndCompute(img2, None)

        if des1 is not None and len(des1) > 2 and des2 is not None and len(des2) > 2:
            # 使用FlannBasedMatcher匹配
            FLANN_INDEX_KDTREE = 0
            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            flann = cv2.FlannBasedMatcher(index_params, search_params)

            # 使用knnMatch匹配处理，并返回匹配matches
            matches = flann.knnMatch(des1, des2, k=2)

            # 通过掩码方式计算有用的点
            matches_array = np.array([[m, n] for m, n in matches], dtype=object)

            matchesMask, matchedPoints1 = compute_matches_mask(matches_array, 0.7)

            totalPoints = len(kp1)
            matchRate = matchedPoints1 / (totalPoints + 0.1)

            return matchRate
        else:
            logger.debug(f"SIFT 特征点不足: kp1={len(kp1) if kp1 else 0}, kp2={len(kp2) if kp2 else 0}")
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

async def capture_all_guns(pathData):
    ReturnData = {}
    for mode, img1 in pathData.items():
        # ✅ 降低日志级别，减少 I/O 开销
        logger.debug(f"开始识别 {mode}")
        
        # 验证图像
        if img1 is None or img1.size == 0:
            logger.warning(f"{mode} 图像为空，跳过")
            ReturnData[mode[:-2]] = "None"
            continue
        
        match_Path = res_path('_internal', 'data', 'firearms', mode[:-2]) + os.sep
        
        if not os.path.exists(match_Path):
            logger.warning(f"模板目录不存在: {match_Path}")
            ReturnData[mode[:-2]] = "None"
            continue
        
        content = os.listdir(match_Path)
        logger.debug(f"{mode} 模板数量: {len(content)}")
        
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
                        
                        # 高置信度提前终止
                        if MatchValue > 0.5:
                            logger.debug(f"{mode} - 高置信度匹配: {MatchName} ({MatchValue:.4f})，提前终止")
                            break
        else:
            # 并行模式（4 个线程）
            max_workers = min(4, len(tasks))  # 最多 4 个线程
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                results = list(executor.map(_match_single_template, tasks))
                
                # 处理结果
                for result in results:
                    if result:
                        name, score = result
                        if score > MatchValue:
                            MatchName = name
                            MatchValue = score
                            
                            # 高置信度提前终止（并行模式下效果有限）
                            if MatchValue > 0.7:
                                logger.debug(f"{mode} - 高置信度匹配: {MatchName} ({MatchValue:.4f})")
                                break  # 注意：并行模式下无法真正中断
        
        # ✅ 设置最低阈值，避免误识别
        MATCH_THRESHOLD = 0.10
        
        if MatchValue < MATCH_THRESHOLD or not MatchName:
            MatchName = "none"
            logger.info(f"{mode} 识别结果: none (置信度 {MatchValue:.4f} < 阈值 {MATCH_THRESHOLD})")
        else:
            logger.info(f"{mode} 识别结果: {MatchName} (置信度: {MatchValue:.4f})")
        
        ReturnData[mode[:-2]] = MatchName
    
    return ReturnData

async def capture_all_positions_thread(current_res):
    start_time = time.time()  # 记录开始时间
    
    logger.info(f"🔍 开始枪械识别，分辨率: {current_res}")
    
    # 尝试发送日志到 UI（如果 PC 对象可用）
    try:
        from core.process import PC as ProcessPC
        if hasattr(ProcessPC, '_ui_log_callback') and ProcessPC._ui_log_callback:
            ProcessPC._ui_log_callback(f"🔍 开始枪械识别 [{current_res}]")
    except Exception:
        pass

    Guns_img = RESOLUTION_SETTINGS[current_res]
    
    # ✅ 恢复原方案：先截一张大图，然后从大图中裁剪 ROI（性能最优）
    try:
        # 根据当前分辨率截取整个屏幕
        res_parts = current_res.split('x')
        screen_width = int(res_parts[0])
        screen_height = int(res_parts[1])
        
        img_gray_full, img_np_full = MSS_Img((0, 0, screen_width, screen_height))
        
        # 从大图中裁剪各个 ROI
        captured_images = []
        for key, coords in Guns_img.items():
            try:
                if key == "posture_roi":
                    continue
                norm = _normalize_roi_ltrb(coords)
                if not norm:
                    logger.error(f"无效 ROI: {key}={coords}")
                    empty_img = np.zeros((50, 50), dtype=np.uint8)
                    captured_images.append((key, empty_img))
                    continue
                left, top, right, bottom = norm
                # 从大图中裁剪 ROI
                roi_gray = img_gray_full[top:bottom, left:right]
                captured_images.append((key, roi_gray))
                
            except Exception as e:
                logger.error(f"裁剪 ROI {key} 失败: {e}")
                empty_img = np.zeros((50, 50), dtype=np.uint8)
                captured_images.append((key, empty_img))
        
        logger.info(f"✅ 成功截取 {len(captured_images)} 个 ROI 区域")
    
    except Exception as e:
        logger.error(f"截图失败: {e}，降级为逐个截取")
        # 降级方案：逐个截取
        captured_images = []
        for key, coords in Guns_img.items():
            try:
                if key == "posture_roi":
                    continue
                norm = _normalize_roi_ltrb(coords)
                if not norm:
                    empty_img = np.zeros((50, 50), dtype=np.uint8)
                    captured_images.append((key, empty_img))
                    continue
                left, top, right, bottom = norm
                img_gray, _ = MSS_Img((left, top, right, bottom))
                captured_images.append((key, img_gray))
            except Exception as e2:
                logger.error(f"截取 ROI {key} 失败: {e2}")
                empty_img = np.zeros((50, 50), dtype=np.uint8)
                captured_images.append((key, empty_img))

    # 将捕获的图像数据分组
    Guns1 = {k: img for k, img in captured_images[0:5]}
    Guns2 = {k: img for k, img in captured_images[5:10]}

    # 对这些图像进行进一步处理
    ReturnData = await asyncio.gather(
        capture_all_guns(Guns1),
        capture_all_guns(Guns2)
    )
    
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
    logger.info("⏱️ 枪械识别耗时: %.2f 秒", elapsed_time)

    return ReturnData

def recogniseif_firearm(current_res):
    x1, x2 = Click.get(current_res, None)
    # 使用Pillow库获取屏幕像素颜色
    screenshot = ImageGrab.grab(bbox=(x1, x2, x1 + 1, x2 + 1))
    r, g, b = screenshot.getpixel((0, 0))
    S_Max, S_Min = 255, 200
    if S_Min <= g <= S_Max and S_Min <= r <= S_Max and S_Min <= b <= S_Max:
        return True
    else:
        return False

