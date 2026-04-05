#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弹痕分析工具 (GUI)
用法:
1. 截图放 calibration_results/ 目录:
   screenshot_base.png   <- 空白墙
   screenshot_result.png <- 打完的墙
2. python calibrate_gui.py
3. 选枪械信息 -> 点分析 -> 出结果
"""

import sys, os, json, time, cv2, numpy as np
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFileDialog,
    QFrame, QMessageBox, QSpinBox, QTextEdit
)
from PyQt5.QtGui import QPixmap, QImage, QFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.fire_data import KEY_DATA

# 配件中文名映射
MUZZLE_CN = {
    'none':'无','eliuquan':'扼流圈','yazuiqiangkou':'鸭嘴枪口',
    'jujiqiangbuchang':'狙击补偿','jujiqiangxiaoyan':'狙击消焰',
    'buqiangbuchang':'步枪补偿','buqiangxiaoyan':'步枪消焰','xiaoyin':'消音器',
    'chongfengqiangxiaoyan':'冲锋消焰','chongfengqiangbuchang':'冲锋补偿',
}
GRIP_CN = {
    'none':'无','banjieshi':'半截式','muzhi':'拇指','zhijiao':'直角','chuizhi':'垂直',
}
STOCK_CN = {
    'none':'无','zhanshuqiangtuo':'战术枪托','zhongxinqiangtuo':'重型枪托',
    'tuosaiban':'托腮板','zidandai':'子弹袋','zhedieshiqiangtuo':'折叠枪托',
}

# ── 检测参数 ──
MIN_AREA, MAX_AREA, MIN_CIRC, COLOR_TH = 20, 800, 0.25, 15

SAVE_DIR = Path("./calibration_results")
SAVE_DIR.mkdir(exist_ok=True)


def _filter_line(holes, max_dx=50):
    """弹痕应该大致在一条竖线上，排除远离主线的孤立噪点
    算法：按 X 分组，取最多的组（弹道主线）"""
    if len(holes) < 4: return holes
    holes = sorted(holes, key=lambda h: h['x'])
    max_group = []
    for i in range(len(holes)):
        group = [h for h in holes if abs(h['x'] - holes[i]['x']) <= max_dx]
        if len(group) > len(max_group): max_group = group
    return max_group if len(max_group) >= 3 else holes


def detect_holes(base, result):
    if base.shape != result.shape:
        result = cv2.resize(result, (base.shape[1], base.shape[0]))
    bg = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    rg = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(bg, rg)
    _, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = np.ones((5,5), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k, iterations=2)
    thresh = cv2.dilate(thresh, k, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    holes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if not (MIN_AREA < area < MAX_AREA): continue
        peri = cv2.arcLength(cnt, True)
        if peri == 0: continue
        if 4*np.pi*(area/(peri*peri)) < MIN_CIRC: continue
        M = cv2.moments(cnt)
        if M["m00"] == 0: continue
        cx, cy = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])
        mask = np.zeros(bg.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)
        cd = abs(cv2.mean(bg, mask=mask)[0] - cv2.mean(rg, mask=mask)[0])
        if cd < COLOR_TH: continue
        holes.append({'x':cx, 'y':cy, 'area':area})
    holes = _filter_line(holes)
    return holes


def sort_holes(holes):
    """
    PUBG 后坐力子弹从下往上飞，先打的弹痕在下面（Y值大）。
    从下往上排：shot_num=1 是最下面的弹痕。
    """
    if not holes: return holes
    s = sorted(holes, key=lambda h: h['y'], reverse=True)  # Y 大的在前
    for i, h in enumerate(s): h['shot_num'] = i+1
    return s


def compare_with_json(holes, gun_name, acc_code, scope_val, pose_val):
    if len(holes) < 2: return None
    s = sorted(holes, key=lambda h: h['shot_num'])
    gp = Path(f"./_internal/GunData/{gun_name}.json")
    if not gp.exists(): return None
    with open(gp, encoding='utf-8') as f:
        gun = json.load(f)
    raw = gun.get(acc_code, gun.get("A0B0C0", []))
    if not raw: return None
    # shot_num=1在最下面(Y大)，shot_num=2在上面(Y小)，所以间距是前一个减后一个
    actual = [s[i-1]['y'] - s[i]['y'] for i in range(1, len(s))]
    jd = [raw[j] for j in range(0, min(len(actual)*2, len(raw)), 2)]
    theory = [j*scope_val*pose_val for j in jd if j != 0]
    av = [d for d in actual if d > 0]
    ratios = [av[i]/theory[i] for i in range(min(len(av), len(theory))) if theory[i] > 0]
    if not ratios: return None
    avg, std = float(np.mean(ratios)), float(np.std(ratios))
    suggested = round(scope_val * avg, 2)
    details = []
    for i in range(min(len(av), len(theory))):
        r = av[i]/theory[i] if theory[i] > 0 else 0
        st = "⚠偏大" if r>1.3 else "⚠偏小" if r<0.7 else "✅正常"
        details.append(f"  {'发数':>4}{'实际':>8}{'理论':>8}{'比值':>8}  {st}\n" \
                      if i==0 else f"  {i:>4}{av[i-1]:>8.1f}{theory[i-1]:>8.1f}{r:>8.2f}  {st}\n")
    return {
        'avg_ratio': round(avg,3), 'std_ratio': round(std,3),
        'suggested': suggested, 'current': scope_val,
        'shots': len(av)+1, 'details': details,
    }


def make_vis(holes, img):
    s = sort_holes(holes)
    v = img.copy()
    for hv in s:
        n = hv['shot_num']
        c = (0,0,255) if n<=5 else (0,165,255) if n<=15 else (0,255,0)
        cv2.circle(v,(hv['x'],hv['y']),10,c,2)
        cv2.circle(v,(hv['x'],hv['y']),3,c,-1)
        cv2.putText(v,str(n),(hv['x']+14,hv['y']-10),cv2.FONT_HERSHEY_SIMPLEX,0.7,(255,255,255),2)
    for i in range(len(s)-1):
        cv2.line(v,(s[i]['x'],s[i]['y']),(s[i+1]['x'],s[i+1]['y']),(100,255,100),2)
    return v


def combo_style():
    return "color:#FFF;background:#2a2a2a;border:1px solid #555;border-radius:4px;padding:4px 8px;font-size:13px;"

def btn_style(color="#FFBA08"):
    return f"color:#FFF;background:#1a1a1a;border:1px solid {color};border-radius:6px;padding:8px 20px;font-size:14px;font-weight:bold;"


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PUBG 弹痕分析")
        self.setStyleSheet("background:#1a1a1a;color:#FFF;font-family:'Microsoft YaHei';")
        self.base_path = None
        self.result_path = None

        self._build()
        self._find_defaults()

    def _build(self):
        main = QVBoxLayout(self)
        main.setSpacing(12)

        # ── 图片选择 ──
        self._section(main, "📷 图片")

        img_row = QHBoxLayout()
        self.base_lb = QLabel("基线: 未选择")
        self.base_lb.setStyleSheet("color:#888;font-size:12px;")
        self.btn_base = QPushButton("选择基线图")
        self.btn_base.setStyleSheet(btn_style("#4AE54A"))
        self.btn_base.setFixedHeight(32)
        self.btn_base.clicked.connect(self._pick_base)
        self.btn_base_auto = QPushButton("自动检测")
        self.btn_base_auto.setStyleSheet(btn_style("#666"))
        self.btn_base_auto.setFixedHeight(32)
        self.btn_base_auto.setFixedWidth(90)
        self.btn_base_auto.clicked.connect(self._auto_base)
        img_row.addWidget(self.base_lb); img_row.addWidget(self.btn_base); img_row.addWidget(self.btn_base_auto)

        img_row2 = QHBoxLayout()
        self.result_lb = QLabel("结果图: 未选择")
        self.result_lb.setStyleSheet("color:#888;font-size:12px;")
        self.btn_res = QPushButton("选择结果图")
        self.btn_res.setStyleSheet(btn_style("#4AE54A"))
        self.btn_res.setFixedHeight(32)
        self.btn_res.clicked.connect(self._pick_result)
        self.btn_res_auto = QPushButton("自动检测")
        self.btn_res_auto.setStyleSheet(btn_style("#666"))
        self.btn_res_auto.setFixedHeight(32)
        self.btn_res_auto.setFixedWidth(90)
        self.btn_res_auto.clicked.connect(self._auto_result)
        img_row2.addWidget(self.result_lb); img_row2.addWidget(self.btn_res); img_row2.addWidget(self.btn_res_auto)

        main.addLayout(img_row); main.addLayout(img_row2)

        # ── 枪械配置 ──
        self._section(main, "🔧 枪械配置")

        row1 = QHBoxLayout()
        self.c_gun = self._cbox({"m762":"M762","akm":"AKM","m416":"M416","scar-l":"SCAR-L","aug":"AUG",
            "groza":"Groza","dp28":"DP28","m249":"M249","uzi":"UZI","vector":"Vector","mp5k":"MP5K",
            "ump45":"UMP45","mini14":"Mini14","sks":"SKS","qbz":"QBZ","g36c":"G36C",
            "mk12":"MK12","mk14":"MK14","mk47":"MK47","qbu":"QBU","vss":"VSS","mg3":"MG3",
            "js9":"JS9","k2":"K2","p90":"P90","pp19":"PP-19","famas":"FAMAS","ace32":"ACE32"})
        row1.addWidget(QLabel("枪械:")); row1.addWidget(self.c_gun); row1.addSpacing(10)
        self.c_scope = self._cbox({"none":"机瞄","hongdian":"红点","quanxi":"全息",
            "2bei":"2倍","3bei":"3倍","4bei":"4倍","6bei":"6倍","8bei":"8倍",
            "15bei":"15倍","renchengxiang4bei":"热成像4x"})
        row1.addWidget(QLabel("倍镜:")); row1.addWidget(self.c_scope)
        main.addLayout(row1)

        row2 = QHBoxLayout()
        self.c_muzz = self._cbox(MUZZLE_CN)
        row2.addWidget(QLabel("枪口:")); row2.addWidget(self.c_muzz); row2.addSpacing(10)
        self.c_grip = self._cbox(GRIP_CN)
        row2.addWidget(QLabel("握把:")); row2.addWidget(self.c_grip); row2.addSpacing(10)
        self.c_stk = self._cbox(STOCK_CN)
        row2.addWidget(QLabel("枪托:")); row2.addWidget(self.c_stk); row2.addSpacing(10)
        self.c_pose = self._cbox({"none":"站立","c":"蹲下","z":"趴下"})
        row2.addWidget(QLabel("姿势:")); row2.addWidget(self.c_pose)
        main.addLayout(row2)

        row3 = QHBoxLayout()
        self.shot_sp = QSpinBox()
        self.shot_sp.setRange(5, 40); self.shot_sp.setValue(10)
        self.shot_sp.setStyleSheet("color:#FFF;background:#2a2a2a;border:1px solid #555;border-radius:4px;padding:4px 8px;font-size:13px;")
        self.shot_sp.setFixedWidth(70)
        row3.addWidget(QLabel("发数:")); row3.addWidget(self.shot_sp); row3.addStretch()
        self.acc_code_lb = QLabel("配件码: A0B0C0")
        self.acc_code_lb.setStyleSheet("color:#FFBA08;font-size:12px;")
        row3.addWidget(self.acc_code_lb)
        main.addLayout(row3)

        # 倍镜系数
        self.scope_val_lb = QLabel("倍镜系数: 1.00")
        self.scope_val_lb.setStyleSheet("color:#888;font-size:11px;")
        main.addWidget(self.scope_val_lb)
        self.progress_lb = QLabel("")
        self.progress_lb.setStyleSheet("color:#FFBA08;font-size:12px;font-weight:bold;")
        main.addWidget(self.progress_lb)

        # ── 结果图预览 ──
        self._section(main, "🖼️ 结果预览")
        self.img_label = QLabel("  分析后将在此显示标注弹痕的图片")
        self.img_label.setStyleSheet("background:#111;color:#555;border:1px solid #333;border-radius:6px;")
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setFixedHeight(260)
        main.addWidget(self.img_label)

        # ── 数据结果 ──
        self._section(main, "📊 分析结果")
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("background:#111;color:#4AE54A;border:1px solid #333;border-radius:6px;font-size:13px;")
        self.result_text.setFixedHeight(180)
        main.addWidget(self.result_text)

        self.resize(520, 850)

        btn_row = QHBoxLayout()
        self.btn_go = QPushButton("🔍 开始分析")
        self.btn_go.setStyleSheet(btn_style("#FFBA08"))
        self.btn_go.setFixedHeight(44)
        self.btn_go.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        self.btn_go.clicked.connect(self._analyze)
        btn_row.addWidget(self.btn_go)
        btn_open = QPushButton("📂 打开标注图")
        btn_open.setStyleSheet(btn_style("#4AE54A"))
        btn_open.setFixedHeight(44)
        btn_open.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        btn_open.clicked.connect(self._open_result_img)
        btn_row.addWidget(btn_open)
        main.addLayout(btn_row)
        self._vis_path = None

    def _open_result_img(self):
        if self._vis_path and os.path.exists(self._vis_path):
            import subprocess
            subprocess.Popen(["start", "", self._vis_path], shell=True)

    def _section(self, parent, title):
        lb = QLabel(title)
        lb.setStyleSheet("color:#FFBA08;font-size:14px;font-weight:bold;padding:4px 0;")
        parent.addWidget(lb)

    def _cbox(self, items):
        c = QComboBox()
        for k,v in items.items(): c.addItem(v, userData=k)
        c.setStyleSheet(combo_style())
        c.setFixedHeight(30)
        return c

    def _find_defaults(self):
        base_candidates = sorted(SAVE_DIR.glob("*base*"))
        result_candidates = sorted(SAVE_DIR.glob("*result*"))
        if base_candidates:
            self.base_path = str(base_candidates[0])
            self.base_lb.setText(f"基线: {os.path.basename(self.base_path)}")
            self.base_lb.setStyleSheet("color:#4AE54A;font-size:12px;")
        if result_candidates:
            self.result_path = str(result_candidates[0])
            self.result_lb.setText(f"结果图: {os.path.basename(self.result_path)}")
            self.result_lb.setStyleSheet("color:#4AE54A;font-size:12px;")

    def _pick_base(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择基线图", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if f:
            self.base_path = f
            self.base_lb.setText(f"基线: {os.path.basename(f)}")
            self.base_lb.setStyleSheet("color:#4AE54A;font-size:12px;")

    def _pick_result(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择结果图", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if f:
            self.result_path = f
            self.result_lb.setText(f"结果图: {os.path.basename(f)}")
            self.result_lb.setStyleSheet("color:#4AE54A;font-size:12px;")

    def _auto_base(self):
        files = sorted(SAVE_DIR.glob("*base*"))
        if files:
            self.base_path = str(files[0])
            self.base_lb.setText(f"基线: {os.path.basename(self.base_path)}")
            self.base_lb.setStyleSheet("color:#4AE54A;font-size:12px;")
        else:
            QMessageBox.warning(self, "提示", f"calibration_results/ 下没找到 base 图片")

    def _auto_result(self):
        files = sorted(SAVE_DIR.glob("*result*"))
        if files:
            self.result_path = str(files[0])
            self.result_lb.setText(f"结果图: {os.path.basename(self.result_path)}")
            self.result_lb.setStyleSheet("color:#4AE54A;font-size:12px;")
        else:
            QMessageBox.warning(self, "提示", f"calibration_results/ 下没找到 result 图片")

    def _acc(self):
        m = KEY_DATA['Muzzle'].get(self._ck(self.c_muzz), '0')
        g = KEY_DATA['Grip'].get(self._ck(self.c_grip), '0')
        s = KEY_DATA['Stock'].get(self._ck(self.c_stk), '0')
        return f"A{m}B{g}C{s}"

    def _ck(self, c): return c.itemData(c.currentIndex()) or c.currentText().lower()

    def _analyze(self):
        if not self.base_path or not self.result_path:
            QMessageBox.warning(self, "错误", "请先选择基线和结果图")
            return
        try:
            base = cv2.imread(self.base_path)
            result = cv2.imread(self.result_path)
            if base is None or result is None:
                QMessageBox.warning(self, "错误", "图片加载失败，请检查路径")
                return
            if result.shape != base.shape:
                result = cv2.resize(result, (base.shape[1], base.shape[0]))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取图片失败: {e}")
            return

        gun_name = self._ck(self.c_gun)
        scope_name = self._ck(self.c_scope)
        acc_code = self._acc()
        pose = self._ck(self.c_pose)

        # 读倍镜系数 (简化: 默认 1.0, 如果有配置文件则读取)
        scope_val = 1.0
        try:
            from core.process import ProcessClass
            pc = ProcessClass()
            cfg = pc.get_config_data('a')
            scope_val = cfg.get('sensitivity', {}).get(scope_name, 1.0)
        except: pass

        pose_val = 1.0
        gp = Path(f"./_internal/GunData/{gun_name}.json")
        if gp.exists():
            with open(gp, encoding='utf-8') as f:
                pose_val = json.load(f).get(pose, 1)

        self.scope_val_lb.setText(f"倍镜系数: {scope_val:.2f}  姿势系数: {pose_val:.2f}")

        # 检测
        holes = detect_holes(base, result)
        if not holes:
            self.result_text.setStyleSheet("background:#111;color:#FF4444;border:1px solid #333;border-radius:6px;font-size:13px;")
            self.result_text.setText("❌ 未检测到弹痕\n\n请检查:\n1. 两张图是否对准了同一面墙\n2. 弹痕是否清晰可见\n3. 截图范围是否包含弹痕区域")
            return

        s = sort_holes(holes)
        self.scope_val_lb.setText(f"倍镜系数: {scope_val:.2f}  姿势系数: {pose_val:.2f}  |  检测到 {len(s)} 个弹痕")

        self.progress_lb.setText("⏳ 绘制标注图...")
        QApplication.processEvents()

        # 可视化
        vis = make_vis(s, result)
        ts = time.strftime('%Y%m%d_%H%M%S')
        vis_path = SAVE_DIR / f"{ts}_result_marked.png"
        cv2.imwrite(str(vis_path), vis)
        self._vis_path = str(vis_path)

        # 在窗口显示标注图
        h, w = vis.shape[:2]
        fmt = QImage.Format_BGR888 if len(vis.shape)==3 and vis.shape[2]==3 else QImage.Format_Grayscale8
        qimg = QImage(vis.data, w, h, vis.strides[0], fmt)
        px = QPixmap.fromImage(qimg)
        scaled = px.scaled(self.img_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img_label.setPixmap(scaled)

        self.progress_lb.setText("⏳ 对比分析...")
        QApplication.processEvents()

        # 对比
        res = compare_with_json(s, gun_name, acc_code, scope_val, pose_val)

        text = f"{'='*42}\n"
        text += f"  弹痕分析结果\n"
        text += f"{'='*42}\n\n"
        text += f"  枪械: {gun_name}\n"
        text += f"  倍镜: {scope_name}  系数={scope_val:.2f}\n"
        text += f"  枪口: {self._ck(self.c_muzz)}  握把: {self._ck(self.c_grip)}  枪托: {self._ck(self.c_stk)}\n"
        text += f"  姿势: {pose}  系数={pose_val:.2f}\n"
        text += f"  配件码: {acc_code}\n\n"
        text += f"  检测到 {len(s)} 个弹痕\n"
        text += f"  标注图: {vis_path}\n\n"

        if res:
            d = res['suggested'] - res['current']
            sign = "+" if d >= 0 else ""
            text += f"  ─ 对比分析 ─\n"
            text += f"  平均比值 : {res['avg_ratio']:.3f}\n"
            text += f"  标准差   : {res['std_ratio']:.3f}\n"
            text += f"  当前系数 : {res['current']}\n"
            text += f"  建议系数 : {res['suggested']}\n"
            text += f"  差值     : {sign}{d:.2f}\n\n"

            # 逐发
            s2 = sorted(s, key=lambda h: h['shot_num'])
            gp2 = Path(f"./_internal/GunData/{gun_name}.json")
            with open(gp2, encoding='utf-8') as f:
                gun2 = json.load(f)
            raw2 = gun2.get(acc_code, gun2.get("A0B0C0", []))
            actual2 = [s2[i-1]['y'] - s2[i]['y'] for i in range(1, len(s2))]
            jd2 = [raw2[j] for j in range(0, min(len(actual2)*2, len(raw2)), 2)]
            theory2 = [j*scope_val*pose_val for j in jd2 if j != 0]
            av2 = [d2 for d2 in actual2 if d2 > 0]

            text += f"  {'发数':>4} {'实际':>8} {'理论':>8} {'比值':>8} {'状态'}\n"
            text += f"  {'-'*46}\n"
            for i in range(min(len(av2), len(theory2))):
                r = av2[i]/theory2[i] if theory2[i]>0 else 0
                st = "⚠偏大" if r>1.3 else "⚠偏小" if r<0.7 else "✅正常"
                text += f"  {i+1:>4} {av2[i]:>8.1f} {theory2[i]:>8.1f} {r:>8.2f}  {st}\n"
        else:
            text += f"  没有找到 JSON 数据 (_internal/GunData/{gun_name}.json)\n"
            text += f"  或没有配件码 {acc_code} 的弹道数据\n"

        self.result_text.setStyleSheet("background:#111;color:#4AE54A;border:1px solid #333;border-radius:6px;font-size:13px;")
        self.result_text.setText(text)

        # 保存 JSON
        if res:
            out = {'gun':gun_name, 'acc_code':acc_code, 'scope':scope_name,
                   'pose':pose, 'scope_val':scope_val, 'pose_val':pose_val,
                   'suggested':res['suggested'], 'avg_ratio':res['avg_ratio'],
                   'detected_holes':len(s), 'vis_file':str(vis_path)}
            jp = SAVE_DIR / f"{ts}_result.json"
            with open(jp, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    import traceback
    def excepthook(etype, value, tb):
        err = ''.join(traceback.format_exception(etype, value, tb))
        try:
            QMessageBox.critical(None, '程序崩溃', f'出错了:\n\n{err}')
        except Exception:
            print(err)
    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
