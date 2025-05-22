import cv2
import mss
import os
import time
import asyncio
from resolution_setting import RESOLUTION_SETTINGS, GUNS_REOLUTION_SETTINGS, Click, Zishi
import numpy as np
from PIL import ImageGrab

def MSS_Img(Values):
    x1, y1, x2, y2 = Values
    with mss.mss() as sct:
        monitor = {"top": x1, "left": y1, "width": x2, "height": y2}
        img = sct.grab(monitor)
        img_np = np.array(img)  # 转换为numpy数组
        # # 创建或确保 test 文件夹存在
        # if not os.path.exists('test'):
        #     os.makedirs('test')
        # # # 保存ROI图像
        # roi_filename = f"test/captured_roi_zishi_{x1}_{y1}_{x2}_{y2}.png"
        # cv2.imwrite(roi_filename, img_np)
        # print(f"Saved captured ROI image to: {roi_filename}")
        img_gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)  # 转换为灰度图
    return img_gray

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
    # 创建sift检测器
    sift = cv2.SIFT_create()
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

    return 0

async def capture_and_compare(Data, imgs):
    Keys = list(Data.keys())[0]
    Values = list(Data.values())[0]
    x1, y1, x2, y2 = Values
    roi = imgs[y1:y2, x1:x2]

    # 创建或确保 test 文件夹存在
    # if not os.path.exists('test'):
    #     os.makedirs('test')
    # 保存ROI图像
    # roi_filename = f"test/captured_roi_{Keys}_{x1}_{y1}_{x2}_{y2}.png"
    # cv2.imwrite(roi_filename, roi)
    # print(f"Saved captured ROI image to: {roi_filename}")

    return Keys, roi

async def capture_all_guns(pathData):
    ReturnData = {}
    for mode, img1 in pathData.items():
        match_Path = f"_internal/data/firearms/{mode[:-2]}/"
        content = os.listdir(match_Path)
        MatchValue = 0.0
        MatchName = ""
        for each in content:
            demo_dir = match_Path + each
            img2 = cv2.imread(demo_dir, cv2.IMREAD_GRAYSCALE)  # 以灰度模式读取图像
            part = match_sift(img1, img2)
            if part > MatchValue:
                MatchName = each[:-4]
                MatchValue = part
        if MatchValue <= 0.0 and not MatchName:
            MatchName = "None"
        ReturnData[mode[:-2]] = MatchName
    return ReturnData

async def capture_all_positions_thread(current_res):
    start_time = time.time()  # 记录开始时间

    Guns_imgs = GUNS_REOLUTION_SETTINGS[current_res]
    Guns_img = RESOLUTION_SETTINGS[current_res]
    # 捕获完整图像
    Images = MSS_Img(Guns_imgs)
    # 创建异步任务来直接在内存中捕获和处理图像
    tasks = [capture_and_compare({k: v}, Images) for k, v in Guns_img.items()]
    captured_images = await asyncio.gather(*tasks)

    # 将捕获的图像数据分组
    Guns1 = {k: img for k, img in captured_images[0:5]}
    Guns2 = {k: img for k, img in captured_images[5:10]}

    # 对这些图像进行进一步处理
    ReturnData = await asyncio.gather(
        capture_all_guns(Guns1),
        capture_all_guns(Guns2)
    )

    elapsed_time = time.time() - start_time  # 计算总耗时
    print(f"Time from capture to recognition: {elapsed_time:.2f} seconds")  # 打印总耗时

    return ReturnData


# 新增函数：检测姿势区域像素变化是否稳定
def is_pose_area_stable(current_res, max_attempts=10, threshold=0.95, delay=0.1):
    """
    检测姿势区域像素是否稳定，通过连续截图比较判断

    参数:
    current_res - 当前分辨率
    max_attempts - 最大尝试次数
    threshold - 相似度阈值，超过此值认为稳定
    delay - 每次截图间隔时间

    返回:
    bool - 区域是否稳定
    """
    zishi_img = Zishi[current_res]

    # 第一次截图
    prev_img_gray, _ = MSS_Img(zishi_img)

    for attempt in range(max_attempts):
        # 等待一小段时间
        time.sleep(delay)

        # 再次截图
        curr_img_gray, _ = MSS_Img(zishi_img)

        # 计算两次截图的相似度
        similarity = cv2.matchTemplate(prev_img_gray, curr_img_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(similarity)

        print(f"姿势区域稳定性检测 - 尝试 {attempt + 1}/{max_attempts}, 相似度: {max_val:.4f}")

        # 如果相似度高于阈值，认为区域稳定
        if max_val > threshold:
            print(f"姿势区域已稳定，相似度: {max_val:.4f}")
            return True

        # 更新上一次截图
        prev_img_gray = curr_img_gray

    print(f"姿势区域未能在{max_attempts}次尝试内稳定")
    return False


# 新增函数：等待姿势区域像素变化
def wait_for_pose_area_change(current_res, timeout=2.0, check_interval=0.05, change_threshold=0.8):
    """
    等待姿势区域发生变化，通过检测像素变化判断

    参数:
    current_res - 当前分辨率
    timeout - 最大等待时间（秒）
    check_interval - 检查间隔时间（秒）
    change_threshold - 变化阈值，低于此值认为发生变化

    返回:
    bool - 是否检测到变化
    """
    zishi_img = Zishi[current_res]

    # 获取初始截图
    initial_img_gray, _ = MSS_Img(zishi_img)

    start_time = time.time()
    while time.time() - start_time < timeout:
        # 等待一小段时间
        time.sleep(check_interval)

        # 再次截图
        current_img_gray, _ = MSS_Img(zishi_img)

        # 计算与初始截图的相似度
        similarity = cv2.matchTemplate(initial_img_gray, current_img_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(similarity)

        # 如果相似度低于阈值，认为发生了变化
        if max_val < change_threshold:
            print(f"检测到姿势区域变化，相似度: {max_val:.4f}")
            return True

    print(f"等待超时，未检测到姿势区域变化")
    return False
async def capture_zishi_positions_thread(current_res, firstPerson=False):
    start_time = time.time()  # 记录开始时间

    # 如果是第三人称模式，需要等待屏幕渲染
    if not firstPerson:
        print("第三人称模式，等待姿势区域渲染...")

        # 方法1：固定延迟（简单但不够智能）
        # time.sleep(0.3)  # 等待300毫秒让屏幕渲染

        # 方法2：自适应等待（推荐）
        # 先等待姿势区域发生变化（表示切换视角后屏幕开始更新）
        change_detected = wait_for_pose_area_change(current_res)

        # 然后等待姿势区域稳定（表示渲染完成）
        if change_detected:
            is_stable = is_pose_area_stable(current_res)
            if not is_stable:
                # 如果未能稳定，使用固定延迟作为备选方案
                print("未能检测到姿势区域稳定，使用固定延迟...")
                time.sleep(0.3)

    # 获取姿势区域截图
    zishi_img = Zishi[current_res]
    img_gray, img_color = MSS_Img(zishi_img)

    # 调试：保存截图
    if not os.path.exists('test'):
        os.makedirs('test')
    debug_filename = f"test/zishi_capture_{time.time()}.png"
    cv2.imwrite(debug_filename, img_color)
    print(f"保存姿势区域截图: {debug_filename}")

    zishi = {"zishi_c": img_gray}
    ReturnData = await asyncio.gather(capture_all_guns(zishi))
    elapsed_time = time.time() - start_time  # 计算总耗时
    print(f"解析姿势耗时: {elapsed_time:.2f} seconds，结果：{ReturnData}")
    return ReturnData


# 获取姿势模板图像
def get_pose_templates(current_res):
    """
    获取姿势模板图像

    参数:
    current_res - 当前分辨率

    返回:
    dict - 姿势模板图像字典 {姿势名称: 模板图像}
    """
    templates = {}
    template_dir = "_internal/data/pose_templates/"

    # 确保模板目录存在
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)
        print(f"创建姿势模板目录: {template_dir}")
        print("请将姿势模板图像放入此目录")
        return templates

    # 读取所有模板图像
    try:
        for filename in os.listdir(template_dir):
            if filename.endswith(".png") or filename.endswith(".jpg"):
                pose_name = os.path.splitext(filename)[0]
                template_path = os.path.join(template_dir, filename)
                template_img = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
                if template_img is not None:
                    templates[pose_name] = template_img
                    print(f"已加载姿势模板: {pose_name}")
    except Exception as e:
        print(f"加载姿势模板出错: {e}")

    return templates


# 与姿势模板比较相似度
def compare_with_pose_templates(img_gray, templates, threshold=0.3):
    """
    将截图与姿势模板比较，返回最匹配的姿势

    参数:
    img_gray - 灰度截图
    templates - 姿势模板字典
    threshold - 最小匹配阈值

    返回:
    tuple - (最匹配姿势名称, 匹配度)
    """
    best_match = "None"
    best_match_value = 0.0

    for pose_name, template in templates.items():
        match_value = match_sift(img_gray, template)
        print(f"与模板 {pose_name} 的匹配度: {match_value:.4f}")

        if match_value > best_match_value:
            best_match_value = match_value
            best_match = pose_name

    # 如果最佳匹配低于阈值，认为没有匹配到姿势
    if best_match_value < threshold:
        return "None", best_match_value

    return best_match, best_match_value


# 等待姿势区域与模板匹配
def wait_for_pose_template_match(current_res, templates, timeout=2.0, check_interval=0.05, match_threshold=0.3):
    """
    等待姿势区域与模板匹配

    参数:
    current_res - 当前分辨率
    templates - 姿势模板字典
    timeout - 最大等待时间（秒）
    check_interval - 检查间隔时间（秒）
    match_threshold - 匹配阈值

    返回:
    tuple - (是否匹配成功, 灰度图像, 彩色图像, 匹配的姿势, 匹配度)
    """
    if not templates:
        print("没有可用的姿势模板，跳过模板匹配")
        return False, None, None, "None", 0.0

    zishi_img = Zishi[current_res]
    start_time = time.time()

    while time.time() - start_time < timeout:
        # 截图
        img_gray, img_color = MSS_Img(zishi_img)

        # 与模板比较
        pose, match_value = compare_with_pose_templates(img_gray, templates, match_threshold)

        print(f"当前匹配: {pose}, 匹配度: {match_value:.4f}")

        # 如果匹配成功
        if pose != "None":
            print(f"成功匹配到姿势: {pose}, 匹配度: {match_value:.4f}")
            return True, img_gray, img_color, pose, match_value

        # 等待一小段时间
        time.sleep(check_interval)

    # 超时，返回最后一次截图
    print(f"等待超时，未能匹配到姿势模板")
    pose, match_value = compare_with_pose_templates(img_gray, templates, 0)  # 使用0阈值获取最佳匹配
    return False, img_gray, img_color, pose, match_value


# 修改后的姿势识别函数，使用模板匹配
async def capture_zishi_positions_thread(current_res, firstPerson=False):
    start_time = time.time()  # 记录开始时间

    # 获取姿势模板
    pose_templates = get_pose_templates(current_res)

    # 如果是第三人称模式，需要等待屏幕渲染
    if not firstPerson:
        print("第三人称模式，等待姿势区域渲染...")

        # 方法1：固定延迟（简单但不够智能）
        # time.sleep(0.3)  # 等待300毫秒让屏幕渲染

        # 方法2：等待与姿势模板匹配（推荐）
        if pose_templates:
            match_success, img_gray, img_color, matched_pose, match_value = wait_for_pose_template_match(
                current_res, pose_templates)

            if match_success:
                print(f"成功匹配到姿势模板: {matched_pose}, 匹配度: {match_value:.4f}")

                # 调试：保存截图
                if not os.path.exists('test'):
                    os.makedirs('test')
                debug_filename = f"test/zishi_capture_matched_{time.time()}.png"
                cv2.imwrite(debug_filename, img_color)
                print(f"保存匹配成功的姿势区域截图: {debug_filename}")

                # 直接使用匹配结果
                zishi = {"zishi_c": img_gray}
                ReturnData = [{"zishi": matched_pose}]

                elapsed_time = time.time() - start_time  # 计算总耗时
                print(f"解析姿势耗时: {elapsed_time:.2f} seconds，结果：{ReturnData}")
                return ReturnData
            else:
                print("未能成功匹配到姿势模板，使用传统SIFT识别")
        else:
            # 如果没有模板，使用固定延迟
            print("没有可用的姿势模板，使用固定延迟...")
            time.sleep(0.3)

    # 获取姿势区域截图
    zishi_img = Zishi[current_res]
    img_gray, img_color = MSS_Img(zishi_img)

    # 调试：保存截图
    if not os.path.exists('test'):
        os.makedirs('test')
    debug_filename = f"test/zishi_capture_{time.time()}.png"
    cv2.imwrite(debug_filename, img_color)
    print(f"保存姿势区域截图: {debug_filename}")

    zishi = {"zishi_c": img_gray}
    ReturnData = await asyncio.gather(capture_all_guns(zishi))

    elapsed_time = time.time() - start_time  # 计算总耗时
    print(f"解析姿势耗时: {elapsed_time:.2f} seconds，结果：{ReturnData}")
    return ReturnData


# 创建姿势模板函数
def create_pose_template(current_res, pose_name, firstPerson=True):
    """
    创建姿势模板

    参数:
    current_res - 当前分辨率
    pose_name - 姿势名称
    firstPerson - 是否第一人称模式

    返回:
    bool - 是否成功创建模板
    """
    print(f"开始创建姿势模板: {pose_name}")

    # 确保模板目录存在
    template_dir = "_internal/data/pose_templates/"
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)

    # 在第一人称模式下截图（通常更稳定）
    if not firstPerson:
        print("警告: 建议在第一人称模式下创建模板以获得更好的质量")
        time.sleep(0.5)  # 给一些时间让屏幕渲染

    # 获取姿势区域截图
    zishi_img = Zishi[current_res]
    img_gray, img_color = MSS_Img(zishi_img)

    # 保存模板
    template_path = f"{template_dir}{pose_name}.png"
    cv2.imwrite(template_path, img_gray)

    # 同时保存彩色版本用于参考
    color_template_path = f"{template_dir}{pose_name}_color.png"
    cv2.imwrite(color_template_path, img_color)

    print(f"姿势模板已保存: {template_path}")
    print(f"彩色参考图已保存: {color_template_path}")

    return True
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

