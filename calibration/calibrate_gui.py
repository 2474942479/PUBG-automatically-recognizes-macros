#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弹痕分析工具 GUI (v3 重构)
═══════════════════════════
交互式弹痕标注 + 实时对比分析 + 迭代修正 + 多组比对

用法: python -m calibration.calibrate_gui
"""

import sys, os, json, time, copy, cv2, numpy as np
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFileDialog,
    QMessageBox, QTextEdit, QMenu, QSplitter, QScrollArea,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QGridLayout,
    QGroupBox, QInputDialog,
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QPainter, QColor, QPen, QBrush

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.fire_data import KEY_DATA
from calibration.bullet_analysis import (
    BulletDetector, BulletSorter, BulletComparator, BulletVisualizer,
    ParameterCorrector, MultiGroupAnalyzer, ProjectData, IterativeCorrector,
    _find_gun_data_dir, _load_sensitivity_config,
)

MUZZLE_CN = {
    'none': '无', 'eliuquan': '扼流圈', 'yazuiqiangkou': '鸭嘴枪口',
    'jujiqiangbuchang': '狙击补偿', 'jujiqiangxiaoyan': '狙击消焰',
    'buqiangbuchang': '步枪补偿', 'buqiangxiaoyan': '步枪消焰', 'xiaoyin': '消音器',
    'chongfengqiangxiaoyan': '冲锋枪消焰', 'chongfengqiangbuchang': '冲锋枪补偿',
}
GRIP_CN = {'none': '无', 'banjieshi': '半截式', 'muzhi': '拇指', 'zhijiao': '直角', 'chuizhi': '垂直'}
STOCK_CN = {
    'none': '无', 'zhanshuqiangtuo': '战术枪托', 'zhongxinqiangtuo': '重型枪托',
    'tuosaiban': '托腮板', 'zidandai': '子弹袋', 'zhedieshiqiangtuo': '折叠式枪托',
}
POSE_CN = {'none': ('站立', 1.0), 'c': ('蹲下', None), 'z': ('趴下', None)}
SCOPE_CN = {
    'none': ('机瞄', None), 'hongdian': ('红点', None), 'quanxi': ('全息', None),
    '2bei': ('2倍', None), '3bei': ('3倍', None), '4bei': ('4倍', None),
    '6bei': ('6倍', None), '8bei': ('8倍', None), '15bei': ('15倍', None),
}


# ═══════════════════════════════════════════
# 交互式画布
# ═══════════════════════════════════════════

class BulletCanvas(QWidget):
    """可缩放/拖拽的弹孔标注画布

    操作说明:
      滚轮  — 缩放
      中键拖  — 平移画布
      左键拖  — 移动弹孔 (标注模式) / 画 ROI 框 (选区模式)
      右键   — 添加/删除弹孔 (标注模式) / 清除选区 (选区模式)
    """
    holes_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._holes = []
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._pan_start = None
        self._selected = -1
        self._drag_start = None

        # ROI 选区
        self._roi_mode = False
        self._roi = None            # (x,y,w,h) in image coords
        self._roi_draw_start = None  # in image coords

        self.setMinimumSize(400, 400)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self._roi = None
        self._selected = -1
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self.update()

    def set_data(self, holes, pixmap=None):
        self._holes = holes or []
        self._selected = -1
        if pixmap:
            self._pixmap = pixmap
        self.update()

    def get_holes(self):
        return self._holes

    def set_roi_mode(self, enabled):
        self._roi_mode = enabled
        self._roi_draw_start = None

    def get_roi(self):
        return self._roi

    def clear_roi(self):
        self._roi = None
        self.update()

    def save_annotation_image(self, path):
        if self._pixmap is None:
            return False
        pm = self._pixmap.copy()
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        for h in self._holes:
            n = h.get('shot_num', 0)
            col = QColor(255, 0, 0) if n <= 5 else QColor(255, 165, 0) if n <= 15 else QColor(0, 200, 0)
            p.setPen(QPen(col, 3))
            p.drawEllipse(QPointF(h['x'], h['y']), 10, 10)
            p.setPen(QPen(Qt.white, 2))
            fnt = p.font()
            fnt.setPointSize(10)
            p.setFont(fnt)
            p.drawText(h['x'] + 14, h['y'] - 10, str(n))
        p.end()
        return pm.save(str(path))

    # ─── 坐标转换 ───

    def _to_widget(self, ix, iy):
        return QPointF(ix * self._zoom + self._offset.x(), iy * self._zoom + self._offset.y())

    def _to_image(self, wx, wy):
        return ((wx - self._offset.x()) / self._zoom, (wy - self._offset.y()) / self._zoom)

    def _find_hole_at(self, wx, wy, radius=15):
        for i, h in enumerate(self._holes):
            wp = self._to_widget(h['x'], h['y'])
            if (wp.x() - wx) ** 2 + (wp.y() - wy) ** 2 < (radius * self._zoom + 5) ** 2:
                return i
        return -1

    # ─── 事件处理 ───

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 30, 30))
        if self._pixmap is None:
            p.setPen(Qt.white)
            p.drawText(self.rect(), Qt.AlignCenter,
                       "加载弹痕截图后在此标注\n右键: 添加弹孔    左键拖: 移动    滚轮: 缩放")
            return

        p.setRenderHint(QPainter.SmoothPixmapTransform)
        tgt = QRectF(self._offset.x(), self._offset.y(),
                     self._pixmap.width() * self._zoom, self._pixmap.height() * self._zoom)
        p.drawPixmap(tgt, self._pixmap, QRectF(self._pixmap.rect()))

        # 绘制弹孔
        for i, h in enumerate(self._holes):
            wp = self._to_widget(h['x'], h['y'])
            n = h.get('shot_num', 0)
            col = QColor(255, 0, 0) if n <= 5 else QColor(255, 165, 0) if n <= 15 else QColor(0, 200, 0)
            pen = QPen(col, 3 if i != self._selected else 4)
            p.setPen(pen)
            r = 10 * self._zoom
            p.drawEllipse(wp, r, r)
            p.setBrush(col)
            p.drawEllipse(wp, 3 * self._zoom, 3 * self._zoom)
            p.setBrush(Qt.NoBrush)

            if i == self._selected:
                p.setPen(QPen(QColor(255, 255, 0), 2, Qt.DashLine))
                p.drawEllipse(wp, r + 4, r + 4)

            p.setPen(QPen(Qt.white, 2))
            fnt = QFont("Arial", max(8, int(10 * self._zoom)))
            p.setFont(fnt)
            p.drawText(int(wp.x() + 14 * self._zoom), int(wp.y() - 10 * self._zoom), str(n))

        # 绘制连线
        if len(self._holes) >= 2:
            s = sorted(self._holes, key=lambda h: h.get('shot_num', 0))
            for i in range(len(s) - 1):
                p.setPen(QPen(QColor(100, 200, 255, 120), 1, Qt.DashLine))
                p.drawLine(self._to_widget(s[i]['x'], s[i]['y']),
                           self._to_widget(s[i + 1]['x'], s[i + 1]['y']))

        # 绘制 ROI
        if self._roi:
            x, y, rw, rh = self._roi
            tl = self._to_widget(x, y)
            br = self._to_widget(x + rw, y + rh)
            p.setPen(QPen(QColor(0, 255, 0), 2, Qt.DashLine))
            p.drawRect(QRectF(tl, br))

        # 模式提示
        if self._roi_mode:
            p.setPen(QColor(0, 255, 0))
            p.drawText(10, 20, "选区模式: 左键拖画框, 右键取消")

    def wheelEvent(self, e):
        old_zoom = self._zoom
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.1, min(10, self._zoom * factor))
        mx, my = e.pos().x(), e.pos().y()
        self._offset = QPointF(
            mx - (mx - self._offset.x()) * self._zoom / old_zoom,
            my - (my - self._offset.y()) * self._zoom / old_zoom,
        )
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan_start = e.pos()
            return

        if self._pixmap is None:
            return

        ix, iy = self._to_image(e.x(), e.y())

        if e.button() == Qt.LeftButton:
            if self._roi_mode:
                self._roi_draw_start = (int(ix), int(iy))
                self._roi = None
            else:
                idx = self._find_hole_at(e.x(), e.y())
                if idx >= 0:
                    self._selected = idx
                    self._drag_start = (e.x(), e.y())
                else:
                    self._selected = -1
                self.update()

        elif e.button() == Qt.RightButton:
            if self._roi_mode:
                self._roi = None
                self.update()
                return
            menu = QMenu(self)
            add_act = menu.addAction("在此添加弹孔")
            del_act = None
            if self._selected >= 0:
                del_act = menu.addAction("删除选中弹孔")
            act = menu.exec_(e.globalPos())
            if act == add_act:
                self._holes.append({'x': int(ix), 'y': int(iy), 'area': 100,
                                    'circularity': 1.0, 'color_diff': 50})
                BulletSorter.sort(self._holes)
                self.holes_changed.emit()
                self.update()
            elif del_act and act == del_act:
                self._holes.pop(self._selected)
                self._selected = -1
                BulletSorter.sort(self._holes)
                self.holes_changed.emit()
                self.update()

    def mouseMoveEvent(self, e):
        if self._pan_start:
            delta = e.pos() - self._pan_start
            self._offset += QPointF(delta)
            self._pan_start = e.pos()
            self.update()
            return

        if self._roi_mode and self._roi_draw_start:
            ix, iy = self._to_image(e.x(), e.y())
            sx, sy = self._roi_draw_start
            self._roi = (min(sx, int(ix)), min(sy, int(iy)),
                         abs(int(ix) - sx), abs(int(iy) - sy))
            self.update()
            return

        if self._drag_start and self._selected >= 0:
            ix, iy = self._to_image(e.x(), e.y())
            self._holes[self._selected]['x'] = int(ix)
            self._holes[self._selected]['y'] = int(iy)
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan_start = None
        elif e.button() == Qt.LeftButton:
            if self._roi_mode and self._roi_draw_start:
                self._roi_draw_start = None
                self._roi_mode = False
                self.update()
            elif self._drag_start and self._selected >= 0:
                self._drag_start = None
                BulletSorter.sort(self._holes)
                self.holes_changed.emit()
                self.update()


# ═══════════════════════════════════════════
# 检测调试对话框
# ═══════════════════════════════════════════

class DebugDialog(QDialog):
    def __init__(self, debug_info, debug_images, parent=None):
        super().__init__(parent)
        self.setWindowTitle("检测过程 (Debug)")
        self.resize(900, 600)
        layout = QVBoxLayout(self)

        info_text = QTextEdit()
        info_text.setReadOnly(True)
        lines = ["<h3>检测参数</h3><pre>"]
        for k, v in debug_info.items():
            if k in ('blob_params',):
                lines.append(f"  {k}: {json.dumps(v)}")
            else:
                lines.append(f"  {k}: {v}")
        lines.append("</pre>")
        info_text.setHtml("\n".join(lines))
        layout.addWidget(QLabel("参数信息:"))
        layout.addWidget(info_text, 1)

        if debug_images:
            layout.addWidget(QLabel("中间图像:"))
            scroll = QScrollArea()
            container = QWidget()
            grid = QGridLayout(container)
            for i, (name, img) in enumerate(debug_images.items()):
                lbl = QLabel(name)
                lbl.setStyleSheet("color: white; font-weight: bold;")
                pm = _cv2_to_pixmap(img)
                if pm:
                    pm = pm.scaledToWidth(min(350, pm.width()), Qt.SmoothTransformation)
                    img_lbl = QLabel()
                    img_lbl.setPixmap(pm)
                    grid.addWidget(lbl, i // 3, (i % 3) * 2)
                    grid.addWidget(img_lbl, i // 3, (i % 3) * 2 + 1)
            scroll.setWidget(container)
            layout.addWidget(scroll, 2)


# ═══════════════════════════════════════════
# 帮助对话框
# ═══════════════════════════════════════════

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用帮助")
        self.resize(800, 700)
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml("""
<h2>弹痕分析工具 v3 使用指南</h2>

<h3>一、截图要求</h3>
<ul>
  <li>找一面<b>干净平整</b>的墙壁 (颜色浅、纹理少)</li>
  <li>站在适当距离, 整个弹匣打完后截图</li>
  <li>截图分辨率应与游戏分辨率一致 (工具自动适配任意分辨率)</li>
</ul>

<h3>二、首次分析 (Round 1: 不开宏)</h3>
<ol>
  <li>不开启宏, 正常射击一整个弹匣</li>
  <li>截图保存为 PNG</li>
  <li>打开本工具 → 选择枪械/配件/倍镜/姿势</li>
  <li>点击"加载弹痕图"</li>
  <li><b>推荐</b>: 点击"框选区域"用鼠标框出弹痕所在区域, 过滤无关干扰</li>
  <li>点击"分析" → 自动检测弹孔</li>
  <li>如果检测不准: 右键手动添加/删除弹孔, 左键拖动调整位置</li>
  <li>确认标注后, 右侧面板显示对比结果和修正参数</li>
  <li>点击"保存项目"保存 .calibration.json</li>
  <li>复制修正参数 → 粘贴到对应 GunData JSON</li>
</ol>

<h3>三、迭代修正 (Round 2+: 开宏后微调)</h3>
<ol>
  <li>使用 Round 1 的修正参数开启宏</li>
  <li>用同样的枪/配件/倍镜/姿势射击一整个弹匣, 截图</li>
  <li>点击"迭代修正" → 选择上一轮保存的 .calibration.json</li>
  <li>再选择本轮截图 → 自动检测 + 计算残差 → 输出微调后参数</li>
</ol>

<h3>四、多组比对</h3>
<ol>
  <li>可用"添加到比对组"按钮收集多组数据 (同一枪械/配件)</li>
  <li>或用"批量加载"加载多个 .calibration.json</li>
  <li>点击"交叉比对" → 统计分析, 给出最优参数</li>
</ol>

<h3>五、检测技巧</h3>
<ul>
  <li><b>灵敏度</b>: 高 = 检出多但可能误检, 低 = 精准但可能漏检</li>
  <li><b>模板</b>: 从截图中裁剪一个弹孔 (15~50px方形), 用作模板能显著提高准确率</li>
  <li><b>ROI选区</b>: 框选弹痕区域后分析, 大幅减少误检</li>
  <li><b>调试</b>: 检测不理想时点击"查看检测过程", 查看中间步骤</li>
</ul>

<h3>六、概念解释</h3>
<ul>
  <li><b>比值 (ratio)</b>: 实际弹孔间距 / 理论补偿间距; >1 表示补偿不足, &lt;1 表示补偿过多</li>
  <li><b>chunk_size</b>: 原始数组中每发子弹占的元素数; 自动从弹孔数反推</li>
  <li><b>scope_val</b>: 倍镜灵敏度系数, 来自 Config/config.json</li>
  <li><b>pose_val</b>: 姿势倍率 (来自 GunData 文件中的 none/c/z 值)</li>
</ul>
""")
        layout.addWidget(text)


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _cv2_to_pixmap(img):
    if img is None:
        return None
    if img.ndim == 2:
        h, w = img.shape
        return QPixmap.fromImage(QImage(img.data, w, h, w, QImage.Format_Grayscale8))
    h, w, c = img.shape
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return QPixmap.fromImage(QImage(rgb.data, w, h, w * c, QImage.Format_RGB888))


def _build_result_html(comparison, correction):
    """生成直观的 HTML 结果展示"""
    if not comparison:
        return "<p style='color:gray;'>暂无分析结果</p>"

    avg = comparison.get('avg_ratio', 1.0)
    diff_pct = round(abs(avg - 1.0) * 100, 1)

    if avg > 1.05:
        verdict_color = '#ff4444'
        verdict = f'补偿偏弱 {diff_pct}%'
        advice = '实际后坐力大于宏的补偿量, 需要<b>增大</b>压枪参数'
    elif avg < 0.95:
        verdict_color = '#ff8800'
        verdict = f'补偿偏强 {diff_pct}%'
        advice = '宏的补偿量大于实际后坐力, 需要<b>减小</b>压枪参数'
    else:
        verdict_color = '#44cc44'
        verdict = f'补偿基本准确 (±{diff_pct}%)'
        advice = '参数已接近最优, 可微调或保持不变'

    chunk_info = f"chunk: {comparison.get('chunk_size_f', comparison.get('chunk_size', '?'))}"
    meta_parts = []
    mag = comparison.get('magazine_size', 0)
    if mag > 0:
        meta_parts.append(f"弹夹: {mag}发")
    rpm = comparison.get('rpm')
    fi_ms = comparison.get('fire_interval_ms')
    if rpm:
        meta_parts.append(f"射速: {rpm}RPM ({fi_ms}ms/发)")
    meta_info = (" | " + " | ".join(meta_parts)) if meta_parts else ""

    html = f"""
    <div style="margin:8px;">
      <h3 style="color:{verdict_color}; font-size:18px;">{verdict}</h3>
      <p>{advice}</p>
      <p>平均比值: <b>{avg:.4f}</b> | 偏差: {comparison.get('std_ratio', 0):.4f}</p>
      <p>弹孔数: {comparison.get('shot_count', 0)} | 有效对比: {comparison.get('valid_pairs', 0)} | {chunk_info}{meta_info}</p>
    """

    # 水平漂移
    avg_dx = comparison.get('avg_horizontal_drift', 0)
    max_dx = comparison.get('max_horizontal_drift', 0)
    std_dx = comparison.get('std_horizontal_drift', 0)
    html += f"""
      <p style="color:#aaa;">水平漂移: 均值{avg_dx:.1f} 最大{max_dx:.1f} 标准差{std_dx:.1f}
        {'(偏移较大, 可能需要水平补偿)' if abs(avg_dx) > 5 else '(正常)'}</p>
    """

    # 逐发明细表
    details = comparison.get('details', [])
    if details:
        html += """
        <table style="border-collapse:collapse; margin-top:8px; font-size:13px;" width="100%">
          <tr style="background:#444; color:white;">
            <th style="padding:4px;">发</th>
            <th>实际(px)</th>
            <th>理论(px)</th>
            <th>比值</th>
            <th>X漂移</th>
            <th>状态</th>
          </tr>
        """
        for d in details:
            ratio = d.get('ratio')
            if ratio and ratio > 1.1:
                row_color = '#ff444433'
                r_text = f'<span style="color:#ff4444">{ratio:.3f}</span>'
            elif ratio and ratio < 0.9:
                row_color = '#ff880033'
                r_text = f'<span style="color:#ff8800">{ratio:.3f}</span>'
            elif ratio:
                row_color = '#44cc4433'
                r_text = f'<span style="color:#44cc44">{ratio:.3f}</span>'
            else:
                row_color = '#ffffff11'
                r_text = 'N/A'
            html += f"""
            <tr style="background:{row_color};">
              <td style="padding:3px; text-align:center;">{d['shot']}</td>
              <td style="text-align:center;">{d['actual_dy']:.0f}</td>
              <td style="text-align:center;">{d['theory_dy']:.0f}</td>
              <td style="text-align:center;">{r_text}</td>
              <td style="text-align:center;">{d.get('x_drift', 0):.0f}</td>
              <td style="text-align:center;">{d['status']}</td>
            </tr>"""
        html += "</table>"

    # 修正参数
    if correction:
        patch = ParameterCorrector.generate_patch_json(correction, 'uniform')
        if patch:
            html += f"""
            <h3 style="margin-top:12px;">修正参数 (均匀模式)</h3>
            <p style="color:#aaa;">复制以下内容替换 GunData JSON 中对应条目:</p>
            <pre style="background:#222; padding:8px; overflow-x:auto; font-size:11px; color:#8f8;">{patch}</pre>
            """

    html += "</div>"
    return html


def _build_iteration_html(iter_result):
    """迭代修正结果 HTML"""
    if not iter_result:
        return "<p style='color:gray;'>迭代修正失败</p>"

    residuals = iter_result.get('residuals', [])
    avg_dy = iter_result.get('avg_residual_dy', 0)
    max_dy = iter_result.get('max_residual_dy', 0)

    if abs(avg_dy) < 3:
        color = '#44cc44'
        verdict = '残差极小, 参数已非常准确!'
    elif abs(avg_dy) < 8:
        color = '#ffcc00'
        verdict = '残差较小, 参数接近最优'
    else:
        color = '#ff4444'
        verdict = '残差较大, 建议继续迭代'

    html = f"""
    <div style="margin:8px;">
      <h3 style="color:{color}; font-size:18px;">{verdict}</h3>
      <p>平均残差: {avg_dy:.1f}px | 最大残差: {max_dy:.1f}px</p>
      <table style="border-collapse:collapse; margin-top:8px; font-size:13px;" width="100%">
        <tr style="background:#444; color:white;">
          <th style="padding:4px;">发</th><th>Y残差(px)</th><th>X残差(px)</th><th>调整量</th>
        </tr>
    """
    for r in residuals:
        html += f"""
        <tr>
          <td style="padding:3px; text-align:center;">{r['shot']}</td>
          <td style="text-align:center;">{r['dy']:.1f}</td>
          <td style="text-align:center;">{r['dx']:.1f}</td>
          <td style="text-align:center;">{r['adjustment_raw']:.2f}</td>
        </tr>"""
    html += "</table>"

    patch = ParameterCorrector.generate_patch_json(iter_result, 'uniform')
    if patch:
        html += f"""
        <h3 style="margin-top:12px;">迭代修正参数</h3>
        <pre style="background:#222; padding:8px; overflow-x:auto; font-size:11px; color:#8f8;">{patch}</pre>
        """
    html += "</div>"
    return html


# ═══════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PUBG 弹痕分析 v3")
        self.resize(1400, 900)

        self._gun_data_dir = _find_gun_data_dir()
        self._sens_cfg = _load_sensitivity_config()
        self._result_img = None
        self._result_path = None
        self._template_img = None
        self._template_path = None

        # 配置缓存
        self._gun_name = ''
        self._acc_code = 'A0B0C0'
        self._scope_key = 'none'
        self._scope_val = 1.0
        self._pose_key = 'none'
        self._pose_val = 1.0

        # 分析结果缓存
        self._last_comparison = None
        self._last_correction = None
        self._last_detector = None
        self._current_project_path = None

        # 多组比对
        self._multi = MultiGroupAnalyzer()

        self._init_ui()
        self._connect_signals()
        self._read_config()

    # ═══ UI 构建 ═══

    def _init_ui(self):
        main = QHBoxLayout(self)

        # ─── 左侧: 画布 ───
        left = QVBoxLayout()

        # 画布
        self.canvas = BulletCanvas()
        left.addWidget(self.canvas, 1)

        # 画布按钮栏
        cv_bar = QHBoxLayout()
        self.btn_roi = QPushButton("框选区域")
        self.btn_roi.setCheckable(True)
        self.btn_clear_roi = QPushButton("清除选区")
        cv_bar.addWidget(self.btn_roi)
        cv_bar.addWidget(self.btn_clear_roi)
        cv_bar.addStretch()
        left.addLayout(cv_bar)

        # ─── 右侧: 配置 + 结果 ───
        right = QVBoxLayout()

        # 枪械配置区
        cfg_group = QGroupBox("枪械配置")
        cfg_layout = QGridLayout(cfg_group)

        cfg_layout.addWidget(QLabel("枪械:"), 0, 0)
        self.c_gun = QComboBox()
        self._populate_guns()
        cfg_layout.addWidget(self.c_gun, 0, 1)

        cfg_layout.addWidget(QLabel("倍镜:"), 0, 2)
        self.c_scope = QComboBox()
        for k, (cn, _) in SCOPE_CN.items():
            self.c_scope.addItem(cn, k)
        cfg_layout.addWidget(self.c_scope, 0, 3)

        cfg_layout.addWidget(QLabel("枪口:"), 1, 0)
        self.c_muzzle = QComboBox()
        for k, cn in MUZZLE_CN.items():
            self.c_muzzle.addItem(cn, k)
        cfg_layout.addWidget(self.c_muzzle, 1, 1)

        cfg_layout.addWidget(QLabel("握把:"), 1, 2)
        self.c_grip = QComboBox()
        for k, cn in GRIP_CN.items():
            self.c_grip.addItem(cn, k)
        cfg_layout.addWidget(self.c_grip, 1, 3)

        cfg_layout.addWidget(QLabel("枪托:"), 2, 0)
        self.c_stock = QComboBox()
        for k, cn in STOCK_CN.items():
            self.c_stock.addItem(cn, k)
        cfg_layout.addWidget(self.c_stock, 2, 1)

        cfg_layout.addWidget(QLabel("姿势:"), 2, 2)
        self.c_pose = QComboBox()
        for k, (cn, _) in POSE_CN.items():
            self.c_pose.addItem(cn, k)
        cfg_layout.addWidget(self.c_pose, 2, 3)

        cfg_layout.addWidget(QLabel("灵敏度:"), 3, 0)
        self.c_sens = QComboBox()
        self.c_sens.addItems(["低 (精准)", "中 (推荐)", "高 (灵敏)"])
        self.c_sens.setCurrentIndex(1)
        cfg_layout.addWidget(self.c_sens, 3, 1)

        right.addWidget(cfg_group)

        # 操作按钮区
        btn_layout = QGridLayout()

        self.btn_load = QPushButton("加载弹痕图")
        self.btn_detect = QPushButton("检测弹孔")
        self.btn_detect.setStyleSheet("background:#2266aa; color:white; padding:6px;")
        self.btn_analyze = QPushButton("分析参数")
        self.btn_analyze.setStyleSheet("font-weight:bold; background:#22aa44; color:white; padding:6px;")

        btn_layout.addWidget(self.btn_load, 0, 0)
        btn_layout.addWidget(self.btn_detect, 0, 1)
        btn_layout.addWidget(self.btn_analyze, 0, 2)

        self.btn_save = QPushButton("保存项目")
        self.btn_load_proj = QPushButton("加载项目")
        self.btn_iterate = QPushButton("迭代修正")
        self.btn_iterate.setStyleSheet("background:#886622; color:white; padding:6px;")
        self.btn_debug = QPushButton("检测过程")

        btn_layout.addWidget(self.btn_save, 0, 3)
        btn_layout.addWidget(self.btn_load_proj, 1, 0)
        btn_layout.addWidget(self.btn_iterate, 1, 1)
        btn_layout.addWidget(self.btn_debug, 1, 2)

        right.addLayout(btn_layout)

        # 状态标签
        self.info_lb = QLabel("就绪")
        self.info_lb.setWordWrap(True)
        self.info_lb.setStyleSheet("color: #aaa; font-size: 12px; padding: 4px;")
        right.addWidget(self.info_lb)

        # 结果区
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("background:#1a1a1a; color:#ddd; font-size:13px;")
        right.addWidget(self.result_text, 1)

        # 复制+帮助
        bot = QHBoxLayout()
        self.btn_copy = QPushButton("复制修正参数")
        self.btn_help = QPushButton("使用帮助")
        bot.addWidget(self.btn_copy)
        bot.addWidget(self.btn_help)
        right.addLayout(bot)

        # 多组比对区
        multi_group = QGroupBox("多组比对")
        mg_layout = QVBoxLayout(multi_group)
        self.group_list = QListWidget()
        self.group_list.setMaximumHeight(120)
        mg_layout.addWidget(self.group_list)

        mg_btn = QHBoxLayout()
        self.btn_add_group = QPushButton("添加到组")
        self.btn_load_multi = QPushButton("批量加载")
        self.btn_del_group = QPushButton("删除选中")
        self.btn_clear_groups = QPushButton("清空")
        self.btn_cross = QPushButton("交叉比对")
        self.btn_cross.setStyleSheet("background:#228844; color:white;")
        mg_btn.addWidget(self.btn_add_group)
        mg_btn.addWidget(self.btn_load_multi)
        mg_btn.addWidget(self.btn_del_group)
        mg_btn.addWidget(self.btn_clear_groups)
        mg_btn.addWidget(self.btn_cross)
        mg_layout.addLayout(mg_btn)
        right.addWidget(multi_group)

        # 组装
        splitter = QSplitter(Qt.Horizontal)
        lw = QWidget()
        lw.setLayout(left)
        rw = QWidget()
        rw.setLayout(right)
        splitter.addWidget(lw)
        splitter.addWidget(rw)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main.addWidget(splitter)

    def _populate_guns(self):
        gd = Path(self._gun_data_dir)
        guns = []
        if gd.is_dir():
            for f in sorted(gd.glob("*.json")):
                guns.append(f.stem)
        if not guns:
            guns = ["m762", "akm", "m416", "groza", "ump45"]
        for g in guns:
            self.c_gun.addItem(g, g)

    # ═══ 信号连接 ═══

    def _connect_signals(self):
        self.btn_load.clicked.connect(self._pick_result)
        self.btn_detect.clicked.connect(self._detect)
        self.btn_analyze.clicked.connect(self._analyze_only)
        self.btn_save.clicked.connect(self._save_project)
        self.btn_load_proj.clicked.connect(self._load_project)
        self.btn_iterate.clicked.connect(self._iterate)
        self.btn_debug.clicked.connect(self._show_debug)
        self.btn_copy.clicked.connect(self._copy_output)
        self.btn_help.clicked.connect(lambda: HelpDialog(self).exec_())

        self.btn_roi.toggled.connect(self.canvas.set_roi_mode)
        self.btn_clear_roi.clicked.connect(self._clear_roi)

        self.btn_add_group.clicked.connect(self._add_to_group)
        self.btn_load_multi.clicked.connect(self._load_multi)
        self.btn_del_group.clicked.connect(self._del_group)
        self.btn_clear_groups.clicked.connect(self._clear_groups)
        self.btn_cross.clicked.connect(self._cross_compare)

        self.canvas.holes_changed.connect(self._on_holes_changed)

        # 配置 combo 变更 → 即时刷新 (Phase 5)
        for combo in [self.c_gun, self.c_scope, self.c_muzzle, self.c_grip, self.c_stock, self.c_pose]:
            combo.currentIndexChanged.connect(self._on_config_changed)

    def _on_config_changed(self):
        self._read_config()
        self._update_results()

    # ═══ 配置读取 ═══

    def _read_config(self):
        """从 UI combo 读取当前配置, 同步到成员变量"""
        self._gun_name = self.c_gun.currentData() or ''

        self._scope_key = self.c_scope.currentData() or 'none'
        self._scope_val = 1.0

        mk = self.c_muzzle.currentData() or 'none'
        gk = self.c_grip.currentData() or 'none'
        sk = self.c_stock.currentData() or 'none'
        m_code = KEY_DATA.get('Muzzle', {}).get(mk, '0')
        g_code = KEY_DATA.get('Grip', {}).get(gk, '0')
        s_code = KEY_DATA.get('Stock', {}).get(sk, '0')
        self._acc_code = f"A{m_code}B{g_code}C{s_code}"

        self._pose_key = self.c_pose.currentData() or 'none'
        self._pose_val = self._get_pose_val()

    def _get_pose_val(self):
        """从 GunData 文件读取当前姿势倍率"""
        if self._pose_key == 'none':
            return 1.0
        gp = Path(self._gun_data_dir) / f"{self._gun_name}.json"
        if not gp.exists():
            return 1.0
        try:
            with open(gp, encoding='utf-8') as f:
                data = json.load(f)
            return float(data.get(self._pose_key, 1.0))
        except Exception:
            return 1.0

    def _get_config_dict(self):
        """返回当前配置 dict (用于 ProjectData.save)"""
        return {
            'gun_name': self._gun_name, 'acc_code': self._acc_code,
            'scope_key': self._scope_key, 'scope_val': self._scope_val,
            'pose_key': self._pose_key, 'pose_val': self._pose_val,
            'muzzle_key': self.c_muzzle.currentData() or 'none',
            'grip_key': self.c_grip.currentData() or 'none',
            'stock_key': self.c_stock.currentData() or 'none',
        }

    def _sensitivity_name(self):
        idx = self.c_sens.currentIndex()
        return ['low', 'medium', 'high'][idx]

    # ═══ 图片加载 ═══

    def _pick_result(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择弹痕截图或项目文件", "",
            "所有支持格式 (*.png *.jpg *.bmp *.calibration.json);;图片 (*.png *.jpg *.bmp);;项目文件 (*.calibration.json)")
        if not path:
            return

        if path.endswith('.calibration.json') or path.endswith('.analysis.json'):
            self._load_project_file(path)
            return

        img = cv2.imread(path)
        if img is None:
            QMessageBox.warning(self, "错误", f"无法读取: {path}")
            return
        self._result_img = img
        self._result_path = path
        pm = _cv2_to_pixmap(img)
        self.canvas.set_image(pm)
        self.info_lb.setText(f"已加载: {Path(path).name} ({img.shape[1]}x{img.shape[0]})")

    def _pick_template(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择弹孔模板", "", "图片 (*.png *.jpg *.bmp)")
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            QMessageBox.warning(self, "错误", f"无法读取: {path}")
            return
        self._template_img = img
        self._template_path = path
        self.info_lb.setText(f"模板: {Path(path).name} ({img.shape[1]}x{img.shape[0]})")

    def _clear_template(self):
        self._template_img = None
        self._template_path = None
        self.info_lb.setText("模板已清除")

    def _clear_roi(self):
        self.canvas.clear_roi()
        self.btn_roi.setChecked(False)

    # ═══ 检测弹孔 (仅检测, 不分析) ═══

    def _detect(self):
        """在当前图片上自动检测弹孔位置, 不进行参数分析"""
        if self._result_img is None:
            QMessageBox.warning(self, "提示", "请先加载弹痕截图")
            return

        sens = self._sensitivity_name()
        detector = BulletDetector(sens)
        roi = self.canvas.get_roi()

        holes = detector.detect_single(self._result_img, roi=roi)
        self._last_detector = detector

        if not holes:
            self.canvas.set_data([], None)
            self.info_lb.setText("未检测到弹痕! 建议: ①调高灵敏度 ②框选弹痕区域 ③右键手动添加")
            self.result_text.setHtml(
                '<p style="color:#ff6666;">未检测到弹痕</p>'
                '<ul><li>检查灵敏度设置 (试试「高」)</li>'
                '<li>使用「框选区域」限定检测范围</li>'
                '<li>右键手动添加弹孔</li></ul>'
                '<p>点击「检测过程」查看中间步骤</p>')
            return

        BulletSorter.sort(holes)
        pm = _cv2_to_pixmap(self._result_img)
        self.canvas.set_data(holes, pm)

        n = len(holes)
        di = detector.debug_info
        self.info_lb.setText(
            f"检测完成 | 灵敏度:{sens} | "
            f"暗点:{di.get('dark_count', 0)} Blob:{di.get('blob_count', 0)} "
            f"中值:{di.get('median_count', 0)} → 最终:{n}个弹孔  "
            f"(确认无误后点击「分析参数」)")

    # ═══ 分析参数 (仅分析, 不检测) ═══

    def _analyze_only(self):
        """基于当前已标注的弹孔, 计算修正参数 (不重新检测)"""
        holes = self.canvas.get_holes()
        if not holes:
            QMessageBox.warning(self, "提示", "无弹孔数据。请先「检测弹孔」或从已保存项目加载")
            return
        self._read_config()
        if not self._gun_name:
            QMessageBox.warning(self, "提示", "请先选择枪械")
            return
        self._update_results()
        self.info_lb.setText(
            f"分析完成 | {self._gun_name} {self._acc_code} | "
            f"scope={self._scope_val} posture={self._pose_val} | "
            f"{len(holes)} 个弹孔")

    # ═══ 结果刷新 ═══

    def _on_holes_changed(self):
        self._update_results()

    def _update_results(self):
        holes = self.canvas.get_holes()
        if not holes or not self._gun_name:
            self.result_text.setHtml("<p style='color:gray;'>配置枪械并添加弹孔后显示结果</p>")
            return

        comp = BulletComparator(self._gun_data_dir).compare(
            holes, self._gun_name, self._acc_code,
            self._scope_val, self._pose_val)
        self._last_comparison = comp

        corr = None
        if comp:
            corr = ParameterCorrector(self._gun_data_dir).correct(
                comp, self._gun_name, self._acc_code)
        self._last_correction = corr

        html = _build_result_html(comp, corr)
        self.result_text.setHtml(html)

    # ═══ 保存项目 ═══

    def _save_project(self):
        holes = self.canvas.get_holes()
        if not holes:
            QMessageBox.warning(self, "提示", "无弹孔数据可保存")
            return

        default_name = f"{self._gun_name}_{self._acc_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.calibration.json"
        path, _ = QFileDialog.getSaveFileName(self, "保存项目", default_name,
                                               "项目文件 (*.calibration.json)")
        if not path:
            return

        img_size = None
        if self._result_img is not None:
            img_size = (self._result_img.shape[1], self._result_img.shape[0])

        saved = ProjectData.save(
            path, holes, self._get_config_dict(),
            comparison=self._last_comparison, correction=self._last_correction,
            image_path=self._result_path, image_size=img_size)
        self._current_project_path = saved

        # 同时保存标注图
        img_save_path = Path(saved).with_suffix('.annotated.png')
        self.canvas.save_annotation_image(str(img_save_path))

        self.info_lb.setText(f"已保存: {Path(saved).name}")

    # ═══ 加载项目 ═══

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "加载项目", "",
                                               "项目文件 (*.calibration.json *.analysis.json *.json)")
        if not path:
            return
        self._load_project_file(path)

    def _load_project_file(self, path):
        data, err = ProjectData.load(path)
        if err:
            QMessageBox.warning(self, "加载失败", err)
            return

        cfg = data.get('config', {})
        self._set_combo(self.c_gun, cfg.get('gun_name', ''))
        self._set_combo(self.c_scope, cfg.get('scope_key', 'none'))
        self._set_combo(self.c_muzzle, cfg.get('muzzle_key', 'none'))
        self._set_combo(self.c_grip, cfg.get('grip_key', 'none'))
        self._set_combo(self.c_stock, cfg.get('stock_key', 'none'))
        self._set_combo(self.c_pose, cfg.get('pose_key', 'none'))
        self._read_config()

        holes = data.get('holes', [])
        if not all('shot_num' in h for h in holes):
            BulletSorter.sort(holes)

        # 尝试加载原图
        img_path = data.get('image_path')
        pm = None
        if img_path and Path(img_path).exists():
            img = cv2.imread(img_path)
            if img is not None:
                self._result_img = img
                self._result_path = img_path
                pm = _cv2_to_pixmap(img)
        if pm is None:
            found = ProjectData.find_image(path)
            if found:
                img = cv2.imread(found)
                if img is not None:
                    self._result_img = img
                    self._result_path = found
                    pm = _cv2_to_pixmap(img)

        # 无图片时: 根据保存的 image_size 创建空白画布, 保证弹孔仍可见
        if pm is None and holes:
            img_size = data.get('image_size')
            if img_size and len(img_size) == 2:
                w, h = int(img_size[0]), int(img_size[1])
            else:
                xs = [hole['x'] for hole in holes]
                ys = [hole['y'] for hole in holes]
                w = max(xs) + 200
                h = max(ys) + 200
            blank = np.zeros((h, w, 3), dtype=np.uint8)
            blank[:] = (40, 40, 40)
            self._result_img = blank
            self._result_path = None
            pm = _cv2_to_pixmap(blank)

        self.canvas.set_data(holes, pm)
        self._current_project_path = path

        # 用当前 GunData 重新分析, 确保结果与最新数据一致
        self._update_results()

        status_parts = [f"已加载项目: {Path(path).name} ({len(holes)}个弹孔)"]
        if self._result_path:
            status_parts.append(f"图片: {Path(self._result_path).name}")
        elif pm is not None:
            status_parts.append("(无原图, 使用空白画布)")
        self.info_lb.setText(" | ".join(status_parts))

    def _set_combo(self, combo, key):
        """安全设置 combo 选中项, 按 userData 匹配"""
        for i in range(combo.count()):
            if combo.itemData(i) == key:
                combo.setCurrentIndex(i)
                return

    # ═══ 迭代修正 (Phase 3) ═══

    def _iterate(self):
        """迭代修正: 加载上轮项目文件 + 新弹痕截图 → 微调参数"""
        # Step 1: 选上轮项目文件
        prev_path, _ = QFileDialog.getOpenFileName(
            self, "选择上一轮项目文件", "",
            "项目文件 (*.calibration.json *.json)")
        if not prev_path:
            return

        prev_data, err = ProjectData.load(prev_path)
        if err:
            QMessageBox.warning(self, "加载失败", err)
            return

        prev_correction = prev_data.get('correction')
        if not prev_correction:
            QMessageBox.warning(self, "错误", "所选项目文件中没有修正参数, 请先完成 Round 1 分析")
            return

        # 恢复配置
        cfg = prev_data.get('config', {})
        self._set_combo(self.c_gun, cfg.get('gun_name', ''))
        self._set_combo(self.c_scope, cfg.get('scope_key', 'none'))
        self._set_combo(self.c_muzzle, cfg.get('muzzle_key', 'none'))
        self._set_combo(self.c_grip, cfg.get('grip_key', 'none'))
        self._set_combo(self.c_stock, cfg.get('stock_key', 'none'))
        self._set_combo(self.c_pose, cfg.get('pose_key', 'none'))
        self._read_config()

        # Step 2: 选新弹痕截图 (开宏后)
        new_path, _ = QFileDialog.getOpenFileName(
            self, "选择本轮弹痕截图 (开宏后)", "",
            "图片 (*.png *.jpg *.bmp)")
        if not new_path:
            return

        new_img = cv2.imread(new_path)
        if new_img is None:
            QMessageBox.warning(self, "错误", f"无法读取: {new_path}")
            return

        self._result_img = new_img
        self._result_path = new_path

        # Step 3: 检测
        sens = self._sensitivity_name()
        detector = BulletDetector(sens)
        roi = self.canvas.get_roi()
        if self._template_img is not None:
            holes = detector.detect_with_template(new_img, self._template_img, roi=roi)
        else:
            holes = detector.detect_single(new_img, roi=roi)
        self._last_detector = detector

        if not holes:
            pm = _cv2_to_pixmap(new_img)
            self.canvas.set_data([], pm)
            self.info_lb.setText("迭代检测: 未检测到弹痕, 请手动标注后结果会自动计算")
            return

        BulletSorter.sort(holes)
        pm = _cv2_to_pixmap(new_img)
        self.canvas.set_data(holes, pm)

        # Step 4: 迭代计算
        iter_result = IterativeCorrector.correct(
            holes, prev_correction, self._scope_val, self._pose_val)
        if not iter_result:
            self.result_text.setHtml("<p style='color:#ff6666;'>迭代修正计算失败</p>")
            return

        self._last_correction = iter_result
        self._last_comparison = None
        self.result_text.setHtml(_build_iteration_html(iter_result))

        # 自动保存
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        rd = prev_data.get('iteration_round', 1) + 1
        save_name = f"{self._gun_name}_round{rd}_{ts}.calibration.json"
        save_path = Path(prev_path).parent / save_name
        ProjectData.save(
            str(save_path), holes, self._get_config_dict(),
            correction=iter_result, iteration_round=rd,
            parent_project=prev_path, image_path=new_path,
            image_size=(new_img.shape[1], new_img.shape[0]))
        self._current_project_path = str(save_path)
        self.info_lb.setText(f"迭代 Round {rd} 完成, 已保存: {save_name}")

    # ═══ Debug ═══

    def _show_debug(self):
        if self._last_detector is None:
            QMessageBox.information(self, "提示", "请先执行一次分析")
            return
        DebugDialog(self._last_detector.debug_info,
                    self._last_detector.debug_images, self).exec_()

    # ═══ 复制 ═══

    def _copy_output(self):
        corr = self._last_correction
        if not corr:
            QMessageBox.information(self, "提示", "暂无修正参数")
            return
        patch = ParameterCorrector.generate_patch_json(corr, 'uniform')
        if patch:
            QApplication.clipboard().setText(patch)
            self.info_lb.setText("已复制到剪贴板")

    # ═══ 多组比对 (Phase 4) ═══

    def _add_to_group(self):
        if not self._last_comparison:
            QMessageBox.warning(self, "提示", "请先完成分析")
            return
        label = f"{self._gun_name}_{self._acc_code}_{self._multi.count + 1}"
        self._multi.add_group(self._last_comparison, label)
        self.group_list.addItem(label)

    def _load_multi(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "批量加载项目文件", "",
                                                  "项目文件 (*.calibration.json *.json)")
        if not paths:
            return
        loaded = 0
        for p in paths:
            data, err = ProjectData.load(p)
            if err or not data:
                continue
            comp = data.get('comparison')
            if not comp:
                continue
            label = f"{comp.get('gun', '')}_{Path(p).stem}"
            self._multi.add_group(comp, label)
            self.group_list.addItem(label)
            loaded += 1

        ok, warn = self._multi.validate_consistency()
        msg = f"加载了 {loaded} 组数据"
        if not ok:
            msg += f"\n⚠ {warn}"
        self.info_lb.setText(msg)

    def _del_group(self):
        row = self.group_list.currentRow()
        if row >= 0:
            self._multi.remove_group(row)
            self.group_list.takeItem(row)

    def _clear_groups(self):
        self._multi.clear()
        self.group_list.clear()

    def _cross_compare(self):
        if self._multi.count < 2:
            QMessageBox.warning(self, "提示", "至少需要 2 组数据")
            return

        ok, warn = self._multi.validate_consistency()
        if not ok:
            reply = QMessageBox.question(self, "警告", f"{warn}\n是否继续?",
                                          QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return

        analysis = self._multi.analyze()
        if not analysis:
            return

        html = "<h3>多组交叉比对结果</h3>"
        html += f"<p>组数: {analysis['n_groups']} | 置信度: {analysis['confidence']}</p>"
        html += f"<p>综合比值: <b>{analysis['overall_avg_ratio']:.4f}</b> ± {analysis['overall_std_ratio']:.4f}</p>"

        if analysis['n_outliers_removed'] > 0:
            html += f"<p style='color:orange;'>已排除 {analysis['n_outliers_removed']} 个异常值</p>"

        html += "<h4>各组比值:</h4><ul>"
        for label, ratio in zip(analysis['group_labels'], analysis['group_ratios']):
            html += f"<li>{label}: {ratio:.4f}</li>"
        html += "</ul>"

        # 生成最优修正
        opt = self._multi.generate_optimal_correction(self._gun_name, self._acc_code, self._gun_data_dir)
        if opt:
            self._last_correction = opt
            patch = ParameterCorrector.generate_patch_json(opt, 'uniform')
            html += f"""
            <h3>最优修正参数</h3>
            <pre style="background:#222; padding:8px; overflow-x:auto; font-size:11px; color:#8f8;">{patch}</pre>
            """

        self.result_text.setHtml(html)


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(palette.Window, QColor(45, 45, 45))
    palette.setColor(palette.WindowText, QColor(220, 220, 220))
    palette.setColor(palette.Base, QColor(30, 30, 30))
    palette.setColor(palette.Text, QColor(220, 220, 220))
    palette.setColor(palette.Button, QColor(55, 55, 55))
    palette.setColor(palette.ButtonText, QColor(220, 220, 220))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
