import cv2
import numpy as np
import time
import matplotlib.pyplot as plt
from PIL import ImageGrab
import os

class BulletPatternAnalyzer:
    """
    PUBG弹痕分析与压枪参数计算工具的核心类
    用于捕获屏幕截图、识别弹痕、分析后坐力模式并计算最佳压枪参数
    """
    
    def __init__(self, capture_region=None, save_dir="./captures"):
        """
        初始化弹痕分析器
        
        参数:
            capture_region: 截图区域 (left, top, right, bottom)，默认为全屏
            save_dir: 截图和结果保存目录
        """
        self.capture_region = capture_region
        self.save_dir = save_dir
        self.screenshots = []
        self.bullet_holes = []
        self.vertical_pattern = []
        self.optimal_param = 0.0
        
        # 创建保存目录
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
    
    def capture_bullet_patterns(self, num_frames=30, interval=0.05):
        """
        捕获训练场射击的屏幕截图序列
        
        参数:
            num_frames: 要捕获的帧数
            interval: 帧间隔时间(秒)
            
        返回:
            截图列表
        """
        print(f"开始捕获弹痕序列，将捕获{num_frames}帧，间隔{interval}秒...")
        self.screenshots = []
        
        for i in range(num_frames):
            # 捕获屏幕截图
            if self.capture_region:
                screenshot = ImageGrab.grab(bbox=self.capture_region)
            else:
                screenshot = ImageGrab.grab()
            
            # 转换为numpy数组
            screenshot = np.array(screenshot)
            # 转换为BGR格式(OpenCV使用BGR)
            screenshot = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
            
            # 保存截图
            self.screenshots.append(screenshot)
            
            # 保存第一帧和最后一帧用于调试
            if i == 0 or i == num_frames - 1:
                cv2.imwrite(f"{self.save_dir}/frame_{i}.png", screenshot)
            
            # 等待指定的间隔时间
            time.sleep(interval)
            
            # 打印进度
            print(f"已捕获 {i+1}/{num_frames} 帧")
        
        print("弹痕序列捕获完成")
        return self.screenshots
    
    def analyze_patterns(self):
        """
        分析截图序列，识别弹痕并计算后坐力模式
        
        返回:
            分析结果字典
        """
        if not self.screenshots or len(self.screenshots) < 2:
            print("错误: 没有足够的截图用于分析")
            return None
        
        print("开始分析弹痕分布...")
        self.bullet_holes = []
        base_image = self.screenshots[0]
        
        # 遍历截图序列
        for i, screenshot in enumerate(self.screenshots[1:], 1):
            # 计算与基准图像的差异
            diff = cv2.absdiff(base_image, screenshot)
            
            # 转换为灰度图
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            
            # 应用阈值处理
            _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
            
            # 应用形态学操作以减少噪点
            kernel = np.ones((3, 3), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            
            # 查找轮廓
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 保存处理后的图像用于调试
            if i == 1 or i == len(self.screenshots) - 1:
                debug_image = screenshot.copy()
                cv2.drawContours(debug_image, contours, -1, (0, 255, 0), 2)
                cv2.imwrite(f"{self.save_dir}/contours_{i}.png", debug_image)
            
            # 过滤并记录弹痕位置
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 10 and area < 500:  # 过滤太小和太大的轮廓
                    # 获取轮廓的中心点
                    M = cv2.moments(contour)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        # 记录弹痕位置和时间
                        self.bullet_holes.append((cx, cy, i * 0.05))
            
            # 更新基准图像为当前图像
            base_image = screenshot
        
        # 分析垂直分布
        self._analyze_vertical_distribution()
        
        # 计算最佳压枪参数
        self._calculate_optimal_parameter()
        
        print(f"弹痕分析完成，识别到{len(self.bullet_holes)}个弹痕")
        
        return {
            "bullet_holes": self.bullet_holes,
            "vertical_pattern": self.vertical_pattern,
            "optimal_param": self.optimal_param
        }
    
    def _analyze_vertical_distribution(self):
        """
        分析弹痕的垂直分布，计算后坐力模式
        """
        if not self.bullet_holes:
            self.vertical_pattern = []
            return
        
        # 按时间排序弹痕
        sorted_holes = sorted(self.bullet_holes, key=lambda x: x[2])
        
        # 初始化垂直位置列表
        y_positions = [hole[1] for hole in sorted_holes]
        
        # 计算相邻弹痕之间的垂直位移
        self.vertical_pattern = []
        for i in range(1, len(y_positions)):
            # 注意：屏幕坐标系中，y轴向下为正，所以后坐力向上为负位移
            vertical_displacement = y_positions[i] - y_positions[i-1]
            self.vertical_pattern.append(vertical_displacement)
        
        # 应用平滑处理以减少噪声影响
        if len(self.vertical_pattern) > 3:
            self.vertical_pattern = self._smooth_pattern(self.vertical_pattern)
    
    def _smooth_pattern(self, pattern, window_size=3):
        """
        使用滑动窗口平均法平滑数据
        
        参数:
            pattern: 要平滑的数据列表
            window_size: 滑动窗口大小
            
        返回:
            平滑后的数据列表
        """
        smoothed = []
        for i in range(len(pattern)):
            # 计算窗口的起始和结束索引
            start = max(0, i - window_size // 2)
            end = min(len(pattern), i + window_size // 2 + 1)
            # 计算窗口内的平均值
            window_avg = sum(pattern[start:end]) / (end - start)
            smoothed.append(window_avg)
        return smoothed
    
    def _calculate_optimal_parameter(self):
        """
        根据垂直后坐力模式计算最佳压枪参数
        """
        if not self.vertical_pattern:
            self.optimal_param = 0.6  # 默认值
            return
        
        # 计算平均垂直位移
        avg_displacement = sum(self.vertical_pattern) / len(self.vertical_pattern)
        
        # 根据平均位移计算压枪参数
        # 注意：这里的逻辑需要根据实际游戏中的压枪机制进行调整
        # 假设位移为正(向下)时不需要压枪，位移为负(向上)时需要压枪
        if avg_displacement >= 0:
            self.optimal_param = 0.1  # 几乎不需要压枪
        else:
            # 位移越大(负值越大)，参数越大
            # 这里使用一个简单的映射函数，可以根据实际需求调整
            self.optimal_param = min(0.9, 0.6 - avg_displacement / 20)
        
        print(f"计算得到的最佳压枪参数: {self.optimal_param:.2f}")
    
    def visualize_bullet_pattern(self):
        """
        生成原始弹痕分布图
        
        返回:
            图表保存路径
        """
        if not self.bullet_holes:
            print("错误: 没有弹痕数据可供可视化")
            return None
        
        print("生成原始弹痕分布图...")
        
        # 创建图表
        plt.figure(figsize=(10, 8))
        
        # 提取弹痕坐标和时间
        x_coords = [hole[0] for hole in self.bullet_holes]
        y_coords = [hole[1] for hole in self.bullet_holes]
        times = [hole[2] for hole in self.bullet_holes]
        
        # 绘制散点图，颜色表示时间
        scatter = plt.scatter(x_coords, y_coords, c=times, cmap='viridis', 
                             s=100, alpha=0.7)
        
        # 添加颜色条，表示时间
        cbar = plt.colorbar(scatter)
        cbar.set_label('时间 (秒)')
        
        # 反转Y轴，使坐标系与屏幕坐标系一致
        plt.gca().invert_yaxis()
        
        # 添加标题和标签
        plt.title('弹痕分布图', fontsize=16)
        plt.xlabel('水平位置 (像素)', fontsize=12)
        plt.ylabel('垂直位置 (像素)', fontsize=12)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 保存图表
        pattern_path = f"{self.save_dir}/bullet_pattern.png"
        plt.savefig(pattern_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"弹痕分布图已保存至: {pattern_path}")
        return pattern_path
    
    def visualize_recoil_curve(self):
        """
        生成后坐力曲线图
        
        返回:
            图表保存路径
        """
        if not self.vertical_pattern:
            print("错误: 没有后坐力数据可供可视化")
            return None
        
        print("生成后坐力曲线图...")
        
        # 创建图表
        plt.figure(figsize=(12, 6))
        
        # 创建时间轴
        times = [i * 0.05 for i in range(len(self.vertical_pattern))]
        
        # 绘制后坐力曲线
        plt.plot(times, self.vertical_pattern, 'b-', linewidth=2, label='垂直位移')
        
        # 计算累积后坐力
        cumulative_recoil = np.cumsum(self.vertical_pattern)
        
        # 绘制累积后坐力曲线
        plt.plot(times, cumulative_recoil, 'r-', linewidth=2, label='累积后坐力')
        
        # 绘制零线
        plt.axhline(y=0, color='k', linestyle='--', alpha=0.5)
        
        # 添加标题和标签
        plt.title('后坐力曲线分析', fontsize=16)
        plt.xlabel('时间 (秒)', fontsize=12)
        plt.ylabel('垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=12)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 添加最佳压枪参数标注
        plt.annotate(f'最佳压枪参数: {self.optimal_param:.2f}', 
                    xy=(0.05, 0.95), xycoords='axes fraction',
                    bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.3),
                    fontsize=12)
        
        # 保存图表
        curve_path = f"{self.save_dir}/recoil_curve.png"
        plt.savefig(curve_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"后坐力曲线图已保存至: {curve_path}")
        return curve_path
    
    def visualize_compensation_effect(self):
        """
        生成压枪效果对比图
        
        返回:
            图表保存路径
        """
        if not self.vertical_pattern:
            print("错误: 没有后坐力数据可供可视化")
            return None
        
        print("生成压枪效果对比图...")
        
        # 创建图表
        plt.figure(figsize=(12, 6))
        
        # 创建时间轴
        times = [i * 0.05 for i in range(len(self.vertical_pattern))]
        
        # 计算原始累积后坐力
        original_recoil = np.cumsum(self.vertical_pattern)
        
        # 计算应用最佳参数后的累积后坐力
        compensated_recoil = original_recoil * (1 - self.optimal_param)
        
        # 计算完美压枪效果(理想情况)
        perfect_compensation = np.zeros_like(original_recoil)
        
        # 绘制三条曲线
        plt.plot(times, original_recoil, 'r-', linewidth=2, label='无压枪')
        plt.plot(times, compensated_recoil, 'g-', linewidth=2, label=f'使用参数 {self.optimal_param:.2f}')
        plt.plot(times, perfect_compensation, 'b--', linewidth=1, label='理想压枪')
        
        # 添加标题和标签
        plt.title('压枪效果对比', fontsize=16)
        plt.xlabel('时间 (秒)', fontsize=12)
        plt.ylabel('累积垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=12)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 计算压枪效果改善百分比
        if np.max(np.abs(original_recoil)) > 0:
            improvement = (1 - np.max(np.abs(compensated_recoil)) / np.max(np.abs(original_recoil))) * 100
            plt.annotate(f'压枪效果改善: {improvement:.1f}%', 
                        xy=(0.05, 0.05), xycoords='axes fraction',
                        bbox=dict(boxstyle="round,pad=0.3", fc="lightgreen", alpha=0.3),
                        fontsize=12)
        
        # 保存图表
        effect_path = f"{self.save_dir}/compensation_effect.png"
        plt.savefig(effect_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"压枪效果对比图已保存至: {effect_path}")
        return effect_path
    
    def run_complete_analysis(self, num_frames=30, interval=0.05):
        """
        运行完整的弹痕分析流程
        
        参数:
            num_frames: 要捕获的帧数
            interval: 帧间隔时间(秒)
            
        返回:
            分析结果字典
        """
        # 捕获弹痕序列
        self.capture_bullet_patterns(num_frames, interval)
        
        # 分析弹痕分布
        analysis_result = self.analyze_patterns()
        
        if analysis_result:
            # 生成可视化结果
            pattern_path = self.visualize_bullet_pattern()
            curve_path = self.visualize_recoil_curve()
            effect_path = self.visualize_compensation_effect()
            
            # 添加可视化路径到结果
            analysis_result["visualization_paths"] = {
                "bullet_pattern": pattern_path,
                "recoil_curve": curve_path,
                "compensation_effect": effect_path
            }
        
        return analysis_result


# 使用示例
if __name__ == "__main__":
    # 创建弹痕分析器实例
    analyzer = BulletPatternAnalyzer(save_dir="./recoil_analysis_results")
    
    # 运行完整分析
    print("准备开始弹痕分析，请在训练场中准备好武器...")
    print("3秒后开始捕获，请对准墙壁连续射击...")
    time.sleep(3)
    
    result = analyzer.run_complete_analysis(num_frames=30, interval=0.05)
    
    if result:
        print("\n分析完成！")
        print(f"识别到的弹痕数量: {len(result['bullet_holes'])}")
        print(f"计算得到的最佳压枪参数: {result['optimal_param']:.2f}")
        print(f"可视化结果已保存至: {analyzer.save_dir}")
    else:
        print("分析失败，请检查截图捕获是否正常。")
