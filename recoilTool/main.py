import os
import sys
import argparse
from bullet_pattern_analyzer import BulletPatternAnalyzer
from bullet_pattern_visualizer import BulletPatternVisualizer
from recoil_curve_visualizer import RecoilCurveVisualizer

def main():
    """
    PUBG弹痕分析与压枪参数计算工具主程序
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='PUBG弹痕分析与压枪参数计算工具')
    parser.add_argument('--region', type=str, help='截图区域 (left,top,right,bottom)')
    parser.add_argument('--frames', type=int, default=30, help='要捕获的帧数')
    parser.add_argument('--interval', type=float, default=0.05, help='帧间隔时间(秒)')
    parser.add_argument('--output', type=str, default='./results', help='结果保存目录')
    parser.add_argument('--mode', type=str, default='full', 
                        choices=['full', 'analyze', 'visualize'], 
                        help='运行模式: full=完整分析, analyze=仅分析, visualize=仅可视化')
    
    args = parser.parse_args()
    
    # 创建输出目录
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    
    # 解析截图区域
    capture_region = None
    if args.region:
        try:
            region_parts = args.region.split(',')
            if len(region_parts) == 4:
                capture_region = tuple(map(int, region_parts))
        except:
            print("错误: 截图区域格式不正确，应为'left,top,right,bottom'")
            return
    
    # 创建分析器和可视化工具
    analyzer = BulletPatternAnalyzer(capture_region=capture_region, save_dir=args.output)
    pattern_visualizer = BulletPatternVisualizer(save_dir=args.output)
    curve_visualizer = RecoilCurveVisualizer(save_dir=args.output)
    
    # 根据运行模式执行相应操作
    if args.mode in ['full', 'analyze']:
        print("\n===== PUBG弹痕分析与压枪参数计算工具 =====")
        print("准备开始弹痕分析，请在训练场中准备好武器...")
        print(f"3秒后开始捕获，将捕获{args.frames}帧，间隔{args.interval}秒")
        print("请对准墙壁连续射击...")
        
        import time
        time.sleep(3)
        
        # 运行完整分析
        result = analyzer.run_complete_analysis(num_frames=args.frames, interval=args.interval)
        
        if not result:
            print("分析失败，请检查截图捕获是否正常。")
            return
        
        print("\n===== 分析结果 =====")
        print(f"识别到的弹痕数量: {len(result['bullet_holes'])}")
        print(f"计算得到的最佳压枪参数: {result['optimal_param']:.2f}")
        print(f"可视化结果已保存至: {args.output}")
    
    if args.mode == 'visualize':
        # 仅可视化模式需要从文件加载数据
        # 这里简化处理，使用示例数据
        import random
        import numpy as np
        
        print("\n===== PUBG弹痕可视化工具 =====")
        print("使用示例数据生成可视化结果...")
        
        # 创建示例数据
        bullet_holes = []
        x_base, y_base = 500, 300
        for i in range(20):
            x = x_base + random.gauss(0, 10) + i * random.uniform(-2, 2)
            y = y_base - i * 5 + random.gauss(0, 3)
            time = i * 0.05
            bullet_holes.append((x, y, time))
        
        vertical_pattern = []
        for i in range(19):
            displacement = bullet_holes[i+1][1] - bullet_holes[i][1]
            vertical_pattern.append(displacement)
        
        optimal_param = 0.65
        
        # 生成可视化
        pattern_visualizer.visualize_bullet_pattern(bullet_holes)
        curve_visualizer.visualize_basic_recoil_curve(vertical_pattern, optimal_param)
        curve_visualizer.visualize_detailed_recoil_analysis(vertical_pattern, optimal_param)
        
        # 创建仪表板
        analysis_result = {
            "bullet_holes": bullet_holes,
            "vertical_pattern": vertical_pattern,
            "optimal_param": optimal_param
        }
        pattern_visualizer.create_visualization_dashboard(analysis_result)
        
        print(f"示例可视化已完成，请查看 {args.output} 目录")
    
    print("\n分析和可视化完成！")

if __name__ == "__main__":
    main()
