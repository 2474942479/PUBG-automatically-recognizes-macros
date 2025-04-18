import numpy as np
import matplotlib.pyplot as plt
import os

class BulletPatternVisualizer:
    """
    PUBG弹痕分布可视化工具
    用于生成弹痕分布图、后坐力曲线和压枪效果对比图
    """
    
    def __init__(self, save_dir="./visualizations"):
        """
        初始化可视化工具
        
        参数:
            save_dir: 可视化结果保存目录
        """
        self.save_dir = save_dir
        
        # 创建保存目录
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
    
    def visualize_bullet_pattern(self, bullet_holes, title="弹痕分布图"):
        """
        生成原始弹痕分布图
        
        参数:
            bullet_holes: 弹痕数据列表，每个元素为 (x, y, time)
            title: 图表标题
            
        返回:
            图表保存路径
        """
        if not bullet_holes:
            print("错误: 没有弹痕数据可供可视化")
            return None
        
        print("生成原始弹痕分布图...")
        
        # 创建图表
        plt.figure(figsize=(10, 8))
        
        # 提取弹痕坐标和时间
        x_coords = [hole[0] for hole in bullet_holes]
        y_coords = [hole[1] for hole in bullet_holes]
        times = [hole[2] for hole in bullet_holes]
        
        # 绘制散点图，颜色表示时间
        scatter = plt.scatter(x_coords, y_coords, c=times, cmap='viridis', 
                             s=100, alpha=0.7)
        
        # 添加颜色条，表示时间
        cbar = plt.colorbar(scatter)
        cbar.set_label('时间 (秒)')
        
        # 反转Y轴，使坐标系与屏幕坐标系一致
        plt.gca().invert_yaxis()
        
        # 添加标题和标签
        plt.title(title, fontsize=16)
        plt.xlabel('水平位置 (像素)', fontsize=12)
        plt.ylabel('垂直位置 (像素)', fontsize=12)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 添加弹痕序号
        for i, (x, y, _) in enumerate(bullet_holes):
            plt.annotate(str(i+1), (x, y), 
                        xytext=(5, 5), textcoords='offset points',
                        fontsize=8, color='black', weight='bold')
        
        # 连接弹痕点，显示弹道轨迹
        sorted_holes = sorted(bullet_holes, key=lambda x: x[2])
        sorted_x = [hole[0] for hole in sorted_holes]
        sorted_y = [hole[1] for hole in sorted_holes]
        plt.plot(sorted_x, sorted_y, 'r--', alpha=0.5, linewidth=1)
        
        # 保存图表
        pattern_path = f"{self.save_dir}/bullet_pattern.png"
        plt.savefig(pattern_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"弹痕分布图已保存至: {pattern_path}")
        return pattern_path
    
    def visualize_bullet_pattern_heatmap(self, bullet_holes, title="弹痕热力图"):
        """
        生成弹痕分布热力图
        
        参数:
            bullet_holes: 弹痕数据列表，每个元素为 (x, y, time)
            title: 图表标题
            
        返回:
            图表保存路径
        """
        if not bullet_holes or len(bullet_holes) < 3:
            print("错误: 没有足够的弹痕数据可供热力图可视化")
            return None
        
        print("生成弹痕分布热力图...")
        
        # 创建图表
        plt.figure(figsize=(10, 8))
        
        # 提取弹痕坐标
        x_coords = [hole[0] for hole in bullet_holes]
        y_coords = [hole[1] for hole in bullet_holes]
        
        # 计算热力图的范围
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)
        
        # 扩展范围以确保所有点都在内
        x_range = max(100, x_max - x_min + 100)
        y_range = max(100, y_max - y_min + 100)
        x_min = max(0, x_min - 50)
        y_min = max(0, y_min - 50)
        
        # 创建网格
        x_grid = np.linspace(x_min, x_min + x_range, 100)
        y_grid = np.linspace(y_min, y_min + y_range, 100)
        X, Y = np.meshgrid(x_grid, y_grid)
        
        # 计算每个网格点的密度
        positions = np.vstack([X.ravel(), Y.ravel()])
        values = np.vstack([x_coords, y_coords])
        kernel = stats.gaussian_kde(values)
        Z = np.reshape(kernel(positions), X.shape)
        
        # 绘制热力图
        plt.imshow(Z, extent=[x_min, x_min + x_range, y_min + y_range, y_min],
                  aspect='auto', cmap='hot')
        
        # 添加弹痕点
        plt.scatter(x_coords, y_coords, c='cyan', s=30, alpha=0.6, edgecolors='white')
        
        # 添加颜色条
        plt.colorbar(label='密度')
        
        # 添加标题和标签
        plt.title(title, fontsize=16)
        plt.xlabel('水平位置 (像素)', fontsize=12)
        plt.ylabel('垂直位置 (像素)', fontsize=12)
        
        # 添加网格线
        plt.grid(True, linestyle='--', alpha=0.3)
        
        # 保存图表
        heatmap_path = f"{self.save_dir}/bullet_heatmap.png"
        plt.savefig(heatmap_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"弹痕热力图已保存至: {heatmap_path}")
        return heatmap_path
    
    def visualize_recoil_curve(self, vertical_pattern, optimal_param=None, title="后坐力曲线分析"):
        """
        生成后坐力曲线图
        
        参数:
            vertical_pattern: 垂直后坐力模式列表
            optimal_param: 计算得到的最佳压枪参数
            title: 图表标题
            
        返回:
            图表保存路径
        """
        if not vertical_pattern:
            print("错误: 没有后坐力数据可供可视化")
            return None
        
        print("生成后坐力曲线图...")
        
        # 创建图表
        plt.figure(figsize=(12, 6))
        
        # 创建时间轴
        times = [i * 0.05 for i in range(len(vertical_pattern))]
        
        # 绘制后坐力曲线
        plt.plot(times, vertical_pattern, 'b-', linewidth=2, label='垂直位移')
        
        # 计算累积后坐力
        cumulative_recoil = np.cumsum(vertical_pattern)
        
        # 绘制累积后坐力曲线
        plt.plot(times, cumulative_recoil, 'r-', linewidth=2, label='累积后坐力')
        
        # 绘制零线
        plt.axhline(y=0, color='k', linestyle='--', alpha=0.5)
        
        # 添加标题和标签
        plt.title(title, fontsize=16)
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
        
        # 添加统计信息
        avg_recoil = np.mean(vertical_pattern)
        max_recoil = np.max(vertical_pattern)
        min_recoil = np.min(vertical_pattern)
        
        stats_text = f"平均后坐力: {avg_recoil:.2f}\n最大上跳: {min_recoil:.2f}\n最大下压: {max_recoil:.2f}"
        plt.annotate(stats_text, 
                    xy=(0.75, 0.05), xycoords='axes fraction',
                    bbox=dict(boxstyle="round,pad=0.3", fc="lightblue", alpha=0.3),
                    fontsize=10)
        
        # 保存图表
        curve_path = f"{self.save_dir}/recoil_curve.png"
        plt.savefig(curve_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"后坐力曲线图已保存至: {curve_path}")
        return curve_path
    
    def visualize_recoil_pattern_3d(self, bullet_holes, title="3D弹道轨迹"):
        """
        生成3D弹道轨迹图
        
        参数:
            bullet_holes: 弹痕数据列表，每个元素为 (x, y, time)
            title: 图表标题
            
        返回:
            图表保存路径
        """
        if not bullet_holes or len(bullet_holes) < 3:
            print("错误: 没有足够的弹痕数据可供3D可视化")
            return None
        
        try:
            from mpl_toolkits.mplot3d import Axes3D
        except ImportError:
            print("错误: 缺少3D绘图所需的库")
            return None
        
        print("生成3D弹道轨迹图...")
        
        # 创建3D图表
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # 提取弹痕坐标和时间
        x_coords = [hole[0] for hole in bullet_holes]
        y_coords = [hole[1] for hole in bullet_holes]
        times = [hole[2] for hole in bullet_holes]
        
        # 绘制3D散点图
        scatter = ax.scatter(x_coords, times, y_coords, c=times, cmap='viridis', 
                           s=50, alpha=0.8)
        
        # 连接点以显示轨迹
        sorted_holes = sorted(bullet_holes, key=lambda x: x[2])
        sorted_x = [hole[0] for hole in sorted_holes]
        sorted_y = [hole[1] for hole in sorted_holes]
        sorted_t = [hole[2] for hole in sorted_holes]
        ax.plot(sorted_x, sorted_t, sorted_y, 'r-', alpha=0.7, linewidth=2)
        
        # 添加颜色条
        cbar = fig.colorbar(scatter, ax=ax, pad=0.1)
        cbar.set_label('时间 (秒)')
        
        # 设置轴标签
        ax.set_xlabel('水平位置 (像素)')
        ax.set_ylabel('时间 (秒)')
        ax.set_zlabel('垂直位置 (像素)')
        
        # 反转Z轴，使坐标系与屏幕坐标系一致
        ax.invert_zaxis()
        
        # 添加标题
        ax.set_title(title, fontsize=16)
        
        # 设置视角
        ax.view_init(elev=30, azim=-60)
        
        # 保存图表
        path_3d = f"{self.save_dir}/recoil_3d.png"
        plt.savefig(path_3d, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"3D弹道轨迹图已保存至: {path_3d}")
        return path_3d
    
    def visualize_compensation_effect(self, vertical_pattern, optimal_param, title="压枪效果对比"):
        """
        生成压枪效果对比图
        
        参数:
            vertical_pattern: 垂直后坐力模式列表
            optimal_param: 计算得到的最佳压枪参数
            title: 图表标题
            
        返回:
            图表保存路径
        """
        if not vertical_pattern:
            print("错误: 没有后坐力数据可供可视化")
            return None
        
        print("生成压枪效果对比图...")
        
        # 创建图表
        plt.figure(figsize=(12, 6))
        
        # 创建时间轴
        times = [i * 0.05 for i in range(len(vertical_pattern))]
        
        # 计算原始累积后坐力
        original_recoil = np.cumsum(vertical_pattern)
        
        # 计算应用最佳参数后的累积后坐力
        compensated_recoil = original_recoil * (1 - optimal_param)
        
        # 计算完美压枪效果(理想情况)
        perfect_compensation = np.zeros_like(original_recoil)
        
        # 绘制三条曲线
        plt.plot(times, original_recoil, 'r-', linewidth=2, label='无压枪')
        plt.plot(times, compensated_recoil, 'g-', linewidth=2, label=f'使用参数 {optimal_param:.2f}')
        plt.plot(times, perfect_compensation, 'b--', linewidth=1, label='理想压枪')
        
        # 添加标题和标签
        plt.title(title, fontsize=16)
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
        
        # 添加不同压枪参数的效果比较
        param_values = [0.2, 0.4, 0.6, 0.8]
        for param in param_values:
            if abs(param - optimal_param) > 0.1:  # 避免与最佳参数太接近
                comp_recoil = original_recoil * (1 - param)
                plt.plot(times, comp_recoil, '--', linewidth=1, alpha=0.5, 
                        label=f'参数 {param:.1f}')
        
        # 更新图例
        plt.legend(fontsize=10, loc='best')
        
        # 保存图表
        effect_path = f"{self.save_dir}/compensation_effect.png"
        plt.savefig(effect_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        print(f"压枪效果对比图已保存至: {effect_path}")
        return effect_path
    
    def create_visualization_dashboard(self, analysis_result):
        """
        创建可视化仪表板，将所有图表组合到一个图像中
        
        参数:
            analysis_result: 分析结果字典，包含bullet_holes, vertical_pattern, optimal_param等
            
        返回:
            仪表板图像保存路径
        """
        if not analysis_result:
            print("错误: 没有分析结果可供可视化")
            return None
        
        bullet_holes = analysis_result.get("bullet_holes", [])
        vertical_pattern = analysis_result.get("vertical_pattern", [])
        optimal_param = analysis_result.get("optimal_param", 0.6)
        
        if not bullet_holes or not vertical_pattern:
            print("错误: 分析结果中缺少必要数据")
            return None
        
        print("创建可视化仪表板...")
        
        # 创建大图表
        plt.figure(figsize=(18, 12))
        
        # 设置子图布局
        gs = plt.GridSpec(2, 2, figure=plt.gcf())
        
        # 弹痕分布图
        ax1 = plt.subplot(gs[0, 0])
        x_coords = [hole[0] for hole in bullet_holes]
        y_coords = [hole[1] for hole in bullet_holes]
        times = [hole[2] for hole in bullet_holes]
        scatter = ax1.scatter(x_coords, y_coords, c=times, cmap='viridis', s=80, alpha=0.7)
        ax1.invert_yaxis()
        ax1.set_title('弹痕分布图', fontsize=14)
        ax1.set_xlabel('水平位置 (像素)', fontsize=10)
        ax1.set_ylabel('垂直位置 (像素)', fontsize=10)
        ax1.grid(True, linestyle='--', alpha=0.7)
        plt.colorbar(scatter, ax=ax1, label='时间 (秒)')
        
        # 后坐力曲线图
        ax2 = plt.subplot(gs[0, 1])
        times_curve = [i * 0.05 for i in range(len(vertical_pattern))]
        ax2.plot(times_curve, vertical_pattern, 'b-', linewidth=2, label='垂直位移')
        ax2.plot(times_curve, np.cumsum(vertical_pattern), 'r-', linewidth=2, label='累积后坐力')
        ax2.axhline(y=0, color='k', linestyle='--', alpha=0.5)
        ax2.set_title('后坐力曲线分析', fontsize=14)
        ax2.set_xlabel('时间 (秒)', fontsize=10)
        ax2.set_ylabel('垂直位移 (像素)', fontsize=10)
        ax2.legend(fontsize=10)
        ax2.grid(True, linestyle='--', alpha=0.7)
        ax2.annotate(f'最佳压枪参数: {optimal_param:.2f}', 
                    xy=(0.05, 0.95), xycoords='axes fraction',
                    bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.3),
                    fontsize=10)
        
        # 压枪效果对比图
        ax3 = plt.subplot(gs[1, :])
        original_recoil = np.cumsum(vertical_pattern)
        compensated_recoil = original_recoil * (1 - optimal_param)
        perfect_compensation = np.zeros_like(original_recoil)
        ax3.plot(times_curve, original_recoil, 'r-', linewidth=2, label='无压枪')
        ax3.plot(times_curve, compensated_recoil, 'g-', linewidth=2, label=f'使用参数 {optimal_param:.2f}')
        ax3.plot(times_curve, perfect_compensation, 'b--', linewidth=1, label='理想压枪')
        ax3.set_title('压枪效果对比', fontsize=14)
        ax3.set_xlabel('时间 (秒)', fontsize=10)
        ax3.set_ylabel('累积垂直位移 (像素)', fontsize=10)
        ax3.legend(fontsize=10)
        ax3.grid(True, linestyle='--', alpha=0.7)
        
        if np.max(np.abs(original_recoil)) > 0:
            improvement = (1 - np.max(np.abs(compensated_recoil)) / np.max(np.abs(original_recoil))) * 100
            ax3.annotate(f'压枪效果改善: {improvement:.1f}%', 
                        xy=(0.05, 0.05), xycoords='axes fraction',
                        bbox=dict(boxstyle="round,pad=0.3", fc="lightgreen", alpha=0.3),
                        fontsize=10)
        
        # 添加总标题
        plt.suptitle('PUBG弹痕分析与压枪参数优化', fontsize=18)
        
        # 调整布局
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        # 保存仪表板
        dashboard_path = f"{self.save_dir}/analysis_dashboard.png"
        plt.savefig(dashboard_path, dpi=120, bbox_inches='tight')
        plt.close()
        
        print(f"可视化仪表板已保存至: {dashboard_path}")
        return dashboard_path


# 使用示例
if __name__ == "__main__":
    # 创建示例数据
    import random
    
    # 模拟弹痕数据
    bullet_holes = []
    x_base, y_base = 500, 300
    for i in range(20):
        # 模拟向上的后坐力模式
        x = x_base + random.gauss(0, 10) + i * random.uniform(-2, 2)
        y = y_base - i * 5 + random.gauss(0, 3)  # 向上移动(屏幕坐标系中y减小)
        time = i * 0.05
        bullet_holes.append((x, y, time))
    
    # 模拟垂直后坐力模式
    vertical_pattern = []
    for i in range(19):
        # 计算相邻弹痕之间的垂直位移
        displacement = bullet_holes[i+1][1] - bullet_holes[i][1]
        vertical_pattern.append(displacement)
    
    # 模拟最佳压枪参数
    optimal_param = 0.65
    
    # 创建可视化工具
    visualizer = BulletPatternVisualizer(save_dir="./example_visualizations")
    
    # 生成各种可视化
    visualizer.visualize_bullet_pattern(bullet_holes)
    visualizer.visualize_recoil_curve(vertical_pattern, optimal_param)
    visualizer.visualize_compensation_effect(vertical_pattern, optimal_param)
    
    # 创建仪表板
    analysis_result = {
        "bullet_holes": bullet_holes,
        "vertical_pattern": vertical_pattern,
        "optimal_param": optimal_param
    }
    visualizer.create_visualization_dashboard(analysis_result)
    
    print("示例可视化已完成，请查看 ./example_visualizations 目录")
