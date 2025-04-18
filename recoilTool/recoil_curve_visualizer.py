import numpy as np
import matplotlib.pyplot as plt
import os

class RecoilCurveVisualizer:
    """
    PUBG后坐力曲线可视化工具
    专注于生成详细的后坐力曲线分析图表
    """
    
    def __init__(self, save_dir="./recoil_curves"):
        """
        初始化后坐力曲线可视化工具
        
        参数:
            save_dir: 可视化结果保存目录
        """
        self.save_dir = save_dir
        
        # 创建保存目录
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
    
    def visualize_basic_recoil_curve(self, vertical_pattern, optimal_param=None):
        """
        生成基本后坐力曲线图
        
        参数:
            vertical_pattern: 垂直后坐力模式列表
            optimal_param: 计算得到的最佳压枪参数
            
        返回:
            图表保存路径
        """
        if not vertical_pattern:
            print("错误: 没有后坐力数据可供可视化")
            return None
        
        print("生成基本后坐力曲线图...")
        
        # 创建图表
        plt.figure(figsize=(10, 6))
        
        # 创建时间轴
        times = [i * 0.05 for i in range(len(vertical_pattern))]
        
        # 绘制后坐力曲线
        plt.plot(times, vertical_pattern, 'b-', linewidth=2, label='垂直位移')
        
        # 添加标题和标签
        plt.title('后坐力曲线', fontsize=16)
        plt.xlabel('时间 (秒)', fontsize=12)
        plt.ylabel('垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=12)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 添加最佳压枪参数标注
        if optimal_param is not None:
            plt.annotate(f'最佳压枪参数: {optimal_param:.2f}', 
                        xy=(0.05, 0.95), xycoords='axes fraction',
                        bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.3),
                        fontsize=12)
        
        # 保存图表
        basic_curve_path = f"{self.save_dir}/basic_recoil_curve.png"
        plt.savefig(basic_curve_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"基本后坐力曲线图已保存至: {basic_curve_path}")
        return basic_curve_path
    
    def visualize_cumulative_recoil(self, vertical_pattern):
        """
        生成累积后坐力曲线图
        
        参数:
            vertical_pattern: 垂直后坐力模式列表
            
        返回:
            图表保存路径
        """
        if not vertical_pattern:
            print("错误: 没有后坐力数据可供可视化")
            return None
        
        print("生成累积后坐力曲线图...")
        
        # 创建图表
        plt.figure(figsize=(10, 6))
        
        # 创建时间轴
        times = [i * 0.05 for i in range(len(vertical_pattern))]
        
        # 计算累积后坐力
        cumulative_recoil = np.cumsum(vertical_pattern)
        
        # 绘制累积后坐力曲线
        plt.plot(times, cumulative_recoil, 'r-', linewidth=2, label='累积后坐力')
        
        # 添加标题和标签
        plt.title('累积后坐力曲线', fontsize=16)
        plt.xlabel('时间 (秒)', fontsize=12)
        plt.ylabel('累积垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=12)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 添加最大累积后坐力标注
        max_recoil = np.max(np.abs(cumulative_recoil))
        max_index = np.argmax(np.abs(cumulative_recoil))
        plt.annotate(f'最大累积后坐力: {cumulative_recoil[max_index]:.2f}', 
                    xy=(times[max_index], cumulative_recoil[max_index]),
                    xytext=(times[max_index] + 0.1, cumulative_recoil[max_index] + 5),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1.5),
                    fontsize=10)
        
        # 保存图表
        cumulative_path = f"{self.save_dir}/cumulative_recoil.png"
        plt.savefig(cumulative_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"累积后坐力曲线图已保存至: {cumulative_path}")
        return cumulative_path
    
    def visualize_detailed_recoil_analysis(self, vertical_pattern, optimal_param=None):
        """
        生成详细的后坐力分析图
        
        参数:
            vertical_pattern: 垂直后坐力模式列表
            optimal_param: 计算得到的最佳压枪参数
            
        返回:
            图表保存路径
        """
        if not vertical_pattern:
            print("错误: 没有后坐力数据可供可视化")
            return None
        
        print("生成详细后坐力分析图...")
        
        # 创建图表
        plt.figure(figsize=(12, 8))
        
        # 创建时间轴
        times = [i * 0.05 for i in range(len(vertical_pattern))]
        
        # 计算累积后坐力
        cumulative_recoil = np.cumsum(vertical_pattern)
        
        # 创建两个子图
        plt.subplot(2, 1, 1)
        
        # 绘制后坐力曲线
        plt.plot(times, vertical_pattern, 'b-', linewidth=2, label='垂直位移')
        
        # 添加移动平均线
        window_size = min(5, len(vertical_pattern))
        if window_size > 1:
            weights = np.ones(window_size) / window_size
            smoothed = np.convolve(vertical_pattern, weights, mode='valid')
            smoothed_times = times[window_size-1:]
            plt.plot(smoothed_times, smoothed, 'g-', linewidth=1.5, label=f'{window_size}点移动平均')
        
        # 添加标题和标签
        plt.title('后坐力模式分析', fontsize=14)
        plt.ylabel('垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=10)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 标记最大和最小后坐力点
        max_index = np.argmax(vertical_pattern)
        min_index = np.argmin(vertical_pattern)
        
        plt.annotate(f'最大下压: {vertical_pattern[max_index]:.2f}', 
                    xy=(times[max_index], vertical_pattern[max_index]),
                    xytext=(times[max_index] + 0.1, vertical_pattern[max_index] + 2),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1),
                    fontsize=8)
        
        plt.annotate(f'最大上跳: {vertical_pattern[min_index]:.2f}', 
                    xy=(times[min_index], vertical_pattern[min_index]),
                    xytext=(times[min_index] + 0.1, vertical_pattern[min_index] - 2),
                    arrowprops=dict(facecolor='black', shrink=0.05, width=1),
                    fontsize=8)
        
        # 第二个子图：累积后坐力
        plt.subplot(2, 1, 2)
        
        # 绘制累积后坐力曲线
        plt.plot(times, cumulative_recoil, 'r-', linewidth=2, label='累积后坐力')
        
        # 如果有最佳压枪参数，绘制压枪效果
        if optimal_param is not None:
            compensated_recoil = cumulative_recoil * (1 - optimal_param)
            plt.plot(times, compensated_recoil, 'g-', linewidth=2, 
                    label=f'压枪后 (参数={optimal_param:.2f})')
            
            # 绘制理想压枪效果
            plt.plot(times, np.zeros_like(times), 'k--', linewidth=1, alpha=0.5, label='理想压枪')
        
        # 添加标题和标签
        plt.title('累积后坐力与压枪效果', fontsize=14)
        plt.xlabel('时间 (秒)', fontsize=12)
        plt.ylabel('累积垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=10)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 添加统计信息
        stats_text = (f"样本数: {len(vertical_pattern)}\n"
                     f"平均后坐力: {np.mean(vertical_pattern):.2f}\n"
                     f"标准差: {np.std(vertical_pattern):.2f}\n"
                     f"最大累积后坐力: {np.max(np.abs(cumulative_recoil)):.2f}")
        
        plt.annotate(stats_text, 
                    xy=(0.75, 0.05), xycoords='axes fraction',
                    bbox=dict(boxstyle="round,pad=0.3", fc="lightblue", alpha=0.3),
                    fontsize=9)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图表
        detailed_path = f"{self.save_dir}/detailed_recoil_analysis.png"
        plt.savefig(detailed_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"详细后坐力分析图已保存至: {detailed_path}")
        return detailed_path
    
    def visualize_recoil_comparison(self, vertical_patterns, labels, title="后坐力模式比较"):
        """
        比较多个后坐力模式
        
        参数:
            vertical_patterns: 多个垂直后坐力模式列表的列表
            labels: 每个后坐力模式的标签
            title: 图表标题
            
        返回:
            图表保存路径
        """
        if not vertical_patterns or len(vertical_patterns) == 0:
            print("错误: 没有后坐力数据可供比较")
            return None
        
        if len(vertical_patterns) != len(labels):
            print("错误: 后坐力模式数量与标签数量不匹配")
            return None
        
        print("生成后坐力模式比较图...")
        
        # 创建图表
        plt.figure(figsize=(12, 10))
        
        # 创建两个子图
        plt.subplot(2, 1, 1)
        
        # 为每个后坐力模式绘制曲线
        for i, pattern in enumerate(vertical_patterns):
            # 创建时间轴
            times = [j * 0.05 for j in range(len(pattern))]
            
            # 绘制后坐力曲线
            plt.plot(times, pattern, linewidth=1.5, label=labels[i])
        
        # 添加标题和标签
        plt.title('后坐力模式比较', fontsize=14)
        plt.ylabel('垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=10)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 第二个子图：累积后坐力比较
        plt.subplot(2, 1, 2)
        
        # 为每个后坐力模式绘制累积曲线
        for i, pattern in enumerate(vertical_patterns):
            # 创建时间轴
            times = [j * 0.05 for j in range(len(pattern))]
            
            # 计算累积后坐力
            cumulative_recoil = np.cumsum(pattern)
            
            # 绘制累积后坐力曲线
            plt.plot(times, cumulative_recoil, linewidth=1.5, label=labels[i])
        
        # 添加标题和标签
        plt.title('累积后坐力比较', fontsize=14)
        plt.xlabel('时间 (秒)', fontsize=12)
        plt.ylabel('累积垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=10)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 添加总标题
        plt.suptitle(title, fontsize=16)
        
        # 调整布局
        plt.tight_layout(rect=[0, 0, 1, 0.95])
        
        # 保存图表
        comparison_path = f"{self.save_dir}/recoil_comparison.png"
        plt.savefig(comparison_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"后坐力模式比较图已保存至: {comparison_path}")
        return comparison_path
    
    def visualize_recoil_segments(self, vertical_pattern, segment_size=5):
        """
        将后坐力曲线分段分析
        
        参数:
            vertical_pattern: 垂直后坐力模式列表
            segment_size: 每段的样本数
            
        返回:
            图表保存路径
        """
        if not vertical_pattern or len(vertical_pattern) < segment_size:
            print(f"错误: 没有足够的后坐力数据进行分段分析 (需要至少{segment_size}个样本)")
            return None
        
        print("生成后坐力分段分析图...")
        
        # 创建图表
        plt.figure(figsize=(12, 8))
        
        # 计算段数
        num_segments = len(vertical_pattern) // segment_size
        
        # 分段后坐力数据
        segments = []
        segment_labels = []
        
        for i in range(num_segments):
            start_idx = i * segment_size
            end_idx = start_idx + segment_size
            segment = vertical_pattern[start_idx:end_idx]
            segments.append(segment)
            segment_labels.append(f"段 {i+1}")
        
        # 创建时间轴
        segment_times = [j * 0.05 for j in range(segment_size)]
        
        # 绘制每段后坐力
        for i, segment in enumerate(segments):
            plt.plot(segment_times, segment, linewidth=1.5, label=segment_labels[i])
        
        # 添加标题和标签
        plt.title(f'后坐力分段分析 (每段{segment_size}个样本)', fontsize=16)
        plt.xlabel('段内时间 (秒)', fontsize=12)
        plt.ylabel('垂直位移 (像素)', fontsize=12)
        
        # 添加图例
        plt.legend(fontsize=10, loc='best')
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 添加段间统计比较
        avg_values = [np.mean(segment) for segment in segments]
        std_values = [np.std(segment) for segment in segments]
        
        stats_text = "段间统计比较:\n"
        for i, (avg, std) in enumerate(zip(avg_values, std_values)):
            stats_text += f"段 {i+1}: 平均={avg:.2f}, 标准差={std:.2f}\n"
        
        plt.annotate(stats_text, 
                    xy=(0.02, 0.02), xycoords='figure fraction',
                    bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", alpha=0.5),
                    fontsize=9)
        
        # 保存图表
        segments_path = f"{self.save_dir}/recoil_segments.png"
        plt.savefig(segments_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"后坐力分段分析图已保存至: {segments_path}")
        return segments_path


# 使用示例
if __name__ == "__main__":
    # 创建示例数据
    import random
    
    # 模拟垂直后坐力模式
    vertical_pattern = []
    for i in range(30):
        # 模拟上跳后坐力(负值)
        if i < 5:
            # 开始射击时后坐力较小
            recoil = -random.uniform(1, 3)
        elif i < 15:
            # 中间阶段后坐力增大
            recoil = -random.uniform(3, 7)
        else:
            # 后期后坐力稳定
            recoil = -random.uniform(4, 6)
        
        # 添加随机波动
        recoil += random.gauss(0, 1)
        vertical_pattern.append(recoil)
    
    # 模拟最佳压枪参数
    optimal_param = 0.65
    
    # 创建后坐力曲线可视化工具
    visualizer = RecoilCurveVisualizer(save_dir="./recoil_curve_examples")
    
    # 生成各种后坐力曲线可视化
    visualizer.visualize_basic_recoil_curve(vertical_pattern, optimal_param)
    visualizer.visualize_cumulative_recoil(vertical_pattern)
    visualizer.visualize_detailed_recoil_analysis(vertical_pattern, optimal_param)
    
    # 创建多个后坐力模式进行比较
    patterns = []
    labels = []
    
    # 原始模式
    patterns.append(vertical_pattern)
    labels.append("原始模式")
    
    # 模拟不同配件的后坐力模式
    with_grip = [v * 0.8 + random.gauss(0, 0.5) for v in vertical_pattern]
    patterns.append(with_grip)
    labels.append("使用握把")
    
    with_compensator = [v * 0.7 + random.gauss(0, 0.5) for v in vertical_pattern]
    patterns.append(with_compensator)
    labels.append("使用补偿器")
    
    with_both = [v * 0.6 + random.gauss(0, 0.5) for v in vertical_pattern]
    patterns.append(with_both)
    labels.append("握把+补偿器")
    
    # 生成比较图
    visualizer.visualize_recoil_comparison(patterns, labels, "不同配件的后坐力比较")
    
    # 生成分段分析
    visualizer.visualize_recoil_segments(vertical_pattern, 6)
    
    print("示例后坐力曲线可视化已完成，请查看 ./recoil_curve_examples 目录")
