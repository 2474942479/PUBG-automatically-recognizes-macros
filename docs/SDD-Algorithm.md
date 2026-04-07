# SDD：算法规格说明

本文档给出与实现一致的公式推导，对应代码见 `calibration/bullet_analysis.py` 与 `core/process.py`。

---

## 1. 符号约定

| 符号 | 含义 |
|------|------|
| \(T\) | 单发射击间隔（秒），来自武器元数据 `fire_interval` |
| \(T_{ms}\) | \(T \times 1000\)（毫秒） |
| \(\Delta_{tick}\) | 宏时间步长，固定为 \(9\,\text{ms}\)（全自动 `FIRE`） |
| \(chunk_f\) | 每发子弹在 GunData 数组中占用的**平均**元素个数（浮点，用于分段与对比） |
| \(chunk_{int}\) | \(\max(1, \mathrm{round}(chunk_f))\)，生成数组时重复填充的 tick 数 |
| \(v_i\) | GunData 数组第 \(i\) 个元素（单 tick 的「标量」补偿） |
| \(S,\,P\) | 倍镜灵敏度系数 `scope`、姿势倍率 `posture`（来自 config 与 GunData 的 `none`/`c`/`z`） |

---

## 2. 射速、RPM 与 chunk 大小

### 2.1 由射击间隔反推 RPM

\[
\text{RPM} = \frac{60}{T}
\]

实现中当存在 `fire_interval` 时，用其计算展示用 `rpm`（见 `BulletComparator` / `BulletParamGenerator` 返回值）。

### 2.2 每发对应的 tick 数（chunk\_f）

全自动武器下，优先使用：

\[
chunk_f = \frac{T_{ms}}{\Delta_{tick}} = \frac{T \times 1000}{9}
\]

即「一发子弹持续时间内，包含多少个 9ms 步」。与注释 **「chunk\_f = fire\_interval\_ms / 9ms」** 一致。

半自动武器列表（如 SKS、Mini14 等）在比较器中 **\(chunk_f = 1\)**，且 `FIRE1` 使用 100ms 步长；与全自动的 `chunk_f` 语义不同，需注意区分。

### 2.3 无 `fire_interval` 时的回退

若元数据中无 `fire_interval`，则用有效数组长度与弹夹容量等估算 `chunk_f`（见 `BulletComparator.compare` 中分支），避免除零并保持与「每发占用若干元素」的假设一致。

---

## 3. Round 1：从弹痕直接生成参数（`BulletParamGenerator`）

### 3.1 像素间距

对按开火顺序排序的弹孔 \(s_0,\ldots,s_{n-1}\)，相邻间隔：

\[
\Delta y_i = \left| s_{i-1}.y - s_i.y \right|,\quad i=1,\ldots,n-1
\]

（取绝对值以兼容标注方向。）

### 3.2 每 tick 标量值

希望：**在一发对应的时间窗口内**，宏累计下移量（在「游戏单位」与像素之间存在未知比例时，Round 1 用配置显式拆开）与像素间距一致。实现中定义：

\[
factor = \max(0.01,\, S \cdot P)
\]

\[
v_{\text{per\_tick}} = \mathrm{round}\left( \frac{\Delta y_i}{chunk_f \cdot factor},\, 2 \right)
\]

对 \(i\) 的每一发间隔，向 `result_array` 连续追加 `chunk_int` 个相同的 `v_per_tick`（`chunk_int = max(1, round(chunk_f))`）。

### 3.3 直观校验

若忽略舍入，且宏每步移动近似为 `round(P × (v × S))`，在分析侧与 `factor` 一致时有：

\[
chunk_{int} \times v_{\text{per\_tick}} \cdot factor \approx \Delta y_i
\]

即一发内的总「标量×灵敏度×姿势」与像素间距对齐。首次生成仍可能因分辨率、DPI、游戏内灵敏度与 `S` 不完全一致而偏差，故需 **Round 2 迭代修正**。

---

## 4. 理论对比（`BulletComparator`）

对第 \(i\) 个发间隔（\(i=0,\ldots,n_{compare}-1\)），取数组下标区间：

\[
[start_i,\, end_i) = \left[\left\lfloor i\cdot chunk_f\right\rceil,\; \min\left(\left\lfloor (i+1)\cdot chunk_f\right\rceil,\, |raw|\right)\right)
\]

（实现用 `int(round(i * chunk_f))` 等，与浮点 `chunk_f` 一致。）

**原始 chunk 内元素和**（先对数组做 `round(posture * (v * scope), 2)` 再累加）记为 \(raw\_sum_i\)，则展示用理论像素位移取：

\[
theory_i = raw\_sum_i \cdot S \cdot P
\]

（与 `compare` 中 `theo = raw_sum * scope_val * posture_val` 一致。）

**比值**：

\[
ratio_i = \frac{actual\_dy_i}{theory_i}
\]

用于判断补偿偏弱（\(ratio>1\)）或偏强（\(ratio<1\)）。多组 \(ratio\) 可做 IQR 去极值后取平均，得到 `avg_ratio`，并给出 `suggested_scope ≈ S × avg_ratio`。

---

## 5. Round 2+：比例迭代修正（`IterativeCorrector`）

### 5.1 残差

对每条轨迹、每个间隔 \(i\)，在相邻两弹孔间取**有符号**纵向差（代码中为 `dy = s[i+1].y - s[i].y`）。在同一间隔上，对多轨迹的 `dy` 取平均。

设当前间隔对应 GunData 片段上**绝对值之和**为 \(C_{sum} = \sum_j |v_j|\)（实现用 `abs(prev_params[j])` 累加）。

### 5.2 修正比例（核心公式）

当 \(C_{sum} > 0.01\) 时：

\[
\rho = \mathrm{clip}\left( \frac{C_{sum}}{C_{sum} + dy},\, 0.05,\, 20 \right)
\]

对该间隔覆盖的下标 \(j\)，更新：

\[
v_j' = \mathrm{round}(v_j \cdot \rho,\, 2)
\]

多轨迹时，先对每个轨迹算 \(\rho\)，再对 \(\rho\) 取平均后写回。

### 5.3 为何可消去未知像素/鼠标换算因子（直观推导）

设真实需要的补偿（像素）为 \(R\)，当前宏在该间隔产生的等效下移（像素）与 \(C_{sum}\) 成正比，记 \(R = k \cdot C_{sum}\)，其中 \(k\) 聚合了分辨率、灵敏度、游戏内与 `mouse_R` 单位等**未知**因子。观测残差在纵向上与「未压平的量」相关，理想情况下有 \(dy \approx R - k\cdot C_{sum}\)（符号与坐标系约定一致时）。若近似 \(dy \approx R - k\cdot C_{sum}\)，且一轮修正希望 \(k \cdot C_{sum}' \approx R\)，则取 \(\rho = C_{sum}/(C_{sum}+dy)\) 使得在 \(dy = R - k\cdot C_{sum}\) 时：

\[
k \cdot (C_{sum}\cdot\rho) = k\cdot \frac{C_{sum}^2}{C_{sum}+dy}
\]

在 \(dy \ll C_{sum}\) 或线性近似下，该比例修正**不依赖单独标定 \(k\)**，而把「差多少」直接反映到数组缩放中；因此文档与代码注释中表述为**比例修正**而非对像素做加法。实际游戏与标注噪声存在，故可能需多轮或配合 `ParameterCorrector`。

### 5.4 chunk\_sum 为零时的回退

若 \(C_{sum} \le 0.01\)，实现用平均 `dy` 在该 chunk 长度上均摊增量（见 `IterativeCorrector.correct` 中 `per_tick` 分支）。

---

## 6. 宏执行：余数累加（亚像素精度）

`process.py` 中每次循环：

```text
exact   = recoil + remainder
move    = int(round(exact))
remainder = exact - move
```

其中 `recoil = round(posture * (i * scope), 2)`。

**含义**：鼠标 API 多为整数像素移动；将每次舍入误差存入 `remainder`，下一发累加，使**长期平均**移动量接近浮点 `recoil` 序列之和，避免系统性偏小或偏大。

---

## 7. 与 `chunk_f` 实现细节相关的注意事项

- `chunk_f` 为浮点时，`int(round(chunk_f))` 可能与真实 `fire_interval` 略有舍入差异；对比与迭代均使用同一套 `chunk_f` 与边界计算，内部一致即可。
- 半自动：`chunk_f=1`，`FIRE1` 间隔 100ms，与 `_TICK_MS=9` 的 chunk 语义不同，分析时不要混用全自动公式。

---

## 8. 参考文献（代码内）

- 武器 `fire_interval` / `mag`：`_GUN_META`（`bullet_analysis.py`）
- 全自动循环：`ProcessClass.FIRE`
- 半自动循环：`ProcessClass.FIRE1`
