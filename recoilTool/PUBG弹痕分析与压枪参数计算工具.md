# PUBG弹痕分析与压枪参数计算工具

## 使用说明

这个工具可以通过分析PUBG游戏中对墙壁射击的弹痕分布，自动计算出最佳的压枪参数值。工具包含以下主要功能：

1. **弹痕捕获与分析**：自动捕获屏幕截图，识别弹痕位置，分析后坐力模式
2. **最佳参数计算**：根据弹痕分布计算最佳的垂直压枪参数
3. **可视化分析**：生成多种可视化图表，帮助理解后坐力模式和压枪效果

## 文件说明

- `bullet_pattern_analyzer.py`: 核心弹痕分析算法，实现截图捕获、弹痕识别和参数计算
- `bullet_pattern_visualizer.py`: 弹痕分布可视化工具，提供多种弹痕分布图表
- `recoil_curve_visualizer.py`: 后坐力曲线可视化工具，专注于后坐力模式分析
- `main.py`: 主程序入口，整合所有功能，提供命令行界面

## 安装依赖

运行以下命令安装所需依赖：

```bash
pip install numpy matplotlib opencv-python pillow
```

## 使用方法

### 基本用法

```bash
python main.py
```

这将使用默认设置运行完整的弹痕分析流程。运行后，工具会：
1. 提示您准备好武器
2. 倒计时3秒后开始捕获屏幕
3. 捕获30帧屏幕截图（默认）
4. 分析弹痕分布并计算最佳压枪参数
5. 生成可视化结果并保存到`./results`目录

### 高级选项

```bash
python main.py --region=100,100,700,500 --frames=40 --interval=0.03 --output=./my_results
```

参数说明：
- `--region`: 截图区域，格式为"左,上,右,下"，默认为全屏
- `--frames`: 要捕获的帧数，默认为30
- `--interval`: 帧间隔时间(秒)，默认为0.05
- `--output`: 结果保存目录，默认为"./results"
- `--mode`: 运行模式，可选值：
  - `full`: 完整分析（默认）
  - `analyze`: 仅执行分析，不生成额外可视化
  - `visualize`: 仅生成可视化（使用示例数据）

## 集成到现有项目

要将此工具集成到现有的PUBG宏识别工具中，可以直接导入相关类：

```python
from bullet_pattern_analyzer import BulletPatternAnalyzer
from bullet_pattern_visualizer import BulletPatternVisualizer

# 创建分析器实例
analyzer = BulletPatternAnalyzer(save_dir="./analysis_results")

# 运行分析
result = analyzer.run_complete_analysis()

# 获取计算出的最佳压枪参数
optimal_param = result["optimal_param"]

# 更新配置文件中的压枪参数
# ...您的配置文件更新代码...
```

## 示例输出

工具会生成以下可视化结果：

1. **弹痕分布图**：显示墙壁上弹痕的空间分布，颜色表示时间
2. **后坐力曲线图**：显示垂直位移和累积后坐力随时间的变化
3. **压枪效果对比图**：比较无压枪、使用计算参数和理想压枪的效果
4. **分析仪表板**：综合以上图表的总览图

所有图表都会保存到指定的输出目录中。

## 注意事项

- 工具需要在训练场中使用，对着平整的墙壁射击效果最佳
- 确保截图区域正确包含了弹痕区域
- 连续射击一个完整弹匣可获得最准确的结果
- 不同武器和配件组合需要单独分析
