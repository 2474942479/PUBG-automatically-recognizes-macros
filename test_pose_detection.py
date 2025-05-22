import sys
import os
import time
import cv2
import numpy as np
import mss
from PIL import Image

# 添加项目根目录到路径，以便导入项目模块
sys.path.append('/home/ubuntu/pubg_refactor')
from resolution_setting import Zishi


def test_template_matching(resolution, save_images=True):
    """
    测试基于模板匹配的姿势检测方法

    参数:
    resolution - 测试的分辨率
    save_images - 是否保存截图用于分析

    返回:
    dict - 测试结果统计
    """
    print(f"\n===== 测试 {resolution} 分辨率下的基于模板匹配的姿势检测 =====")

    # 确保测试目录存在
    test_dir = f"test_results/template_matching/{resolution}"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)

    # 获取姿势区域坐标
    zishi_coords = Zishi.get(resolution)
    if not zishi_coords:
        print(f"错误: 未找到 {resolution} 分辨率的姿势区域坐标")
        return {"error": "未找到分辨率坐标"}

    # 加载姿势模板
    templates = load_pose_templates()
    if not templates:
        print("错误: 未找到姿势模板，请先创建模板")
        return {"error": "未找到姿势模板"}

    # 模拟第三人称切换后的截图
    results = {
        "total_tests": 5,
        "successful_matches": 0,
        "failed_matches": 0,
        "avg_match_time": 0,
        "match_times": [],
        "match_scores": []
    }

    for i in range(results["total_tests"]):
        print(f"\n测试 #{i + 1}")

        # 模拟切换到第三人称
        print("模拟切换到第三人称...")

        # 使用模板匹配方法
        start_time = time.time()

        match_success, img_gray, img_color, matched_pose, match_score = wait_for_pose_template_match(
            resolution, zishi_coords, templates)

        elapsed_time = time.time() - start_time
        results["match_times"].append(elapsed_time)
        results["match_scores"].append(match_score)

        # 保存截图用于分析
        if save_images:
            img_path = f"{test_dir}/test_{i + 1}_{matched_pose}_{match_score:.2f}.png"
            cv2.imwrite(img_path, img_color)
            print(f"截图已保存到: {img_path}")

        # 判断匹配是否成功
        if match_success:
            print(f"姿势匹配成功! 匹配到: {matched_pose}, 匹配度: {match_score:.4f}")
            results["successful_matches"] += 1
        else:
            print(f"姿势匹配失败! 最佳匹配: {matched_pose}, 匹配度: {match_score:.4f}")
            results["failed_matches"] += 1

        print(f"匹配耗时: {elapsed_time:.3f}秒")

        # 等待一段时间再进行下一次测试
        if i < results["total_tests"] - 1:
            time.sleep(1)

    # 计算平均匹配时间
    results["avg_match_time"] = sum(results["match_times"]) / len(results["match_times"])
    results["avg_match_score"] = sum(results["match_scores"]) / len(results["match_scores"])

    # 打印测试结果摘要
    print(f"\n===== {resolution} 模板匹配测试结果摘要 =====")
    print(f"总测试次数: {results['total_tests']}")
    print(f"成功匹配次数: {results['successful_matches']}")
    print(f"失败匹配次数: {results['failed_matches']}")
    print(f"成功率: {results['successful_matches'] / results['total_tests'] * 100:.1f}%")
    print(f"平均匹配时间: {results['avg_match_time']:.3f}秒")
    print(f"平均匹配分数: {results['avg_match_score']:.4f}")

    return results


def load_pose_templates():
    """加载姿势模板"""
    templates = {}
    template_dir = "_internal/data/pose_templates/"

    # 确保模板目录存在
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)
        print(f"创建姿势模板目录: {template_dir}")
        return templates

    # 读取所有模板图像
    try:
        for filename in os.listdir(template_dir):
            if filename.endswith(".png") and not filename.endswith("_color.png"):
                pose_name = os.path.splitext(filename)[0]
                template_path = os.path.join(template_dir, filename)
                template_img = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
                if template_img is not None:
                    templates[pose_name] = template_img
                    print(f"已加载姿势模板: {pose_name}")
    except Exception as e:
        print(f"加载姿势模板出错: {e}")

    return templates


def capture_screenshot(x1, y1, x2, y2):
    """简单截图函数"""
    with mss.mss() as sct:
        monitor = {"top": x1, "left": y1, "width": x2, "height": y2}
        img = sct.grab(monitor)
        img_np = np.array(img)
        img_gray = cv2.cvtColor(img_np, cv2.COLOR_BGRA2GRAY)
        img_color = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
        return img_gray, img_color


def match_sift(img1, img2):
    """使用SIFT算法计算两个图像的匹配度"""
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
        matchesMask = np.zeros((len(matches), 2), dtype=np.int32)
        matchedPoints1 = 0

        for i in range(len(matches)):
            m, n = matches[i]
            if m.distance < 0.7 * n.distance:
                matchesMask[i, 0] = 1
                matchedPoints1 += 1

        totalPoints = len(kp1)
        matchRate = matchedPoints1 / (totalPoints + 0.1)

        return matchRate

    return 0


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


def wait_for_pose_template_match(resolution, zishi_coords, templates, timeout=2.0, check_interval=0.05,
                                 match_threshold=0.3):
    """
    等待姿势区域与模板匹配

    参数:
    resolution - 当前分辨率
    zishi_coords - 姿势区域坐标
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

    x1, y1, x2, y2 = zishi_coords
    start_time = time.time()

    while time.time() - start_time < timeout:
        # 截图
        img_gray, img_color = capture_screenshot(x1, y1, x2, y2)

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


def create_pose_template(resolution, pose_name):
    """
    创建姿势模板

    参数:
    resolution - 当前分辨率
    pose_name - 姿势名称

    返回:
    bool - 是否成功创建模板
    """
    print(f"开始创建姿势模板: {pose_name}")

    # 确保模板目录存在
    template_dir = "_internal/data/pose_templates/"
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)

    # 获取姿势区域坐标
    zishi_coords = Zishi.get(resolution)
    if not zishi_coords:
        print(f"错误: 未找到 {resolution} 分辨率的姿势区域坐标")
        return False

    x1, y1, x2, y2 = zishi_coords

    # 获取姿势区域截图
    img_gray, img_color = capture_screenshot(x1, y1, x2, y2)

    # 保存模板
    template_path = f"{template_dir}{pose_name}.png"
    cv2.imwrite(template_path, img_gray)

    # 同时保存彩色版本用于参考
    color_template_path = f"{template_dir}{pose_name}_color.png"
    cv2.imwrite(color_template_path, img_color)

    print(f"姿势模板已保存: {template_path}")
    print(f"彩色参考图已保存: {color_template_path}")

    return True


def main():
    """主测试函数"""
    # 确保测试结果目录存在
    if not os.path.exists("test_results/template_matching"):
        os.makedirs("test_results/template_matching")

    # 检查是否有命令行参数
    if len(sys.argv) > 1:
        # 创建模板模式
        if sys.argv[1] == "create_template" and len(sys.argv) >= 4:
            resolution = sys.argv[2]
            pose_name = sys.argv[3]
            create_pose_template(resolution, pose_name)
            return

    # 测试的分辨率列表
    resolutions = ["2304x1440"]  # 可以添加更多分辨率进行测试

    # 存储所有测试结果
    all_results = {}

    # 执行测试
    for resolution in resolutions:
        all_results[resolution] = test_template_matching(resolution)

    # 生成报告
    generate_report(all_results)


def generate_report(results):
    """生成报告"""
    report_path = "test_results/template_matching/report.txt"

    with open(report_path, "w") as f:
        f.write("===== PUBG姿势模板匹配测试报告 =====\n\n")

        for resolution, data in results.items():
            f.write(f"分辨率: {resolution}\n")
            f.write("-" * 50 + "\n")

            if "error" in data:
                f.write(f"错误: {data['error']}\n")
            else:
                f.write(f"总测试次数: {data['total_tests']}\n")
                f.write(f"成功匹配次数: {data['successful_matches']}\n")
                f.write(f"失败匹配次数: {data['failed_matches']}\n")
                f.write(f"成功率: {data['successful_matches'] / data['total_tests'] * 100:.1f}%\n")
                f.write(f"平均匹配时间: {data['avg_match_time']:.3f}秒\n")
                f.write(f"平均匹配分数: {data['avg_match_score']:.4f}\n")

            f.write("\n\n")

        f.write("===== 使用说明 =====\n")
        f.write("1. 创建姿势模板:\n")
        f.write("   python test_template_matching.py create_template 2304x1440 standing\n")
        f.write("   python test_template_matching.py create_template 2304x1440 crouching\n")
        f.write("   python test_template_matching.py create_template 2304x1440 prone\n\n")
        f.write("2. 测试模板匹配:\n")
        f.write("   python test_template_matching.py\n\n")
        f.write("注意: 创建模板时最好在第一人称模式下进行，以获得更稳定的模板图像\n")

    print(f"\n测试报告已生成: {report_path}")


if __name__ == "__main__":
    main()
