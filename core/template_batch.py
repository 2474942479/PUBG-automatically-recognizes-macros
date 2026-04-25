"""
批量模板生成工具
从 roi_config.json 读取所有背包 ROI 坐标，
实时截取游戏画面后批量裁剪、自动识别。
分两阶段：先收集候选结果，再由用户确认后写入文件。
"""

import os
import json
import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)

ROI_TYPE_TO_CATEGORY = {
    'Name_1': 'Name', 'Name_2': 'Name',
    'Scope_1': 'Scope', 'Scope_2': 'Scope',
    'Muzzle_1': 'Muzzle', 'Muzzle_2': 'Muzzle',
    'Grip_1': 'Grip', 'Grip_2': 'Grip',
    'Stock_1': 'Stock', 'Stock_2': 'Stock',
}

BACKPACK_ROI_TYPES = [
    'Name_1', 'Scope_1', 'Muzzle_1', 'Grip_1', 'Stock_1',
    'Name_2', 'Scope_2', 'Muzzle_2', 'Grip_2', 'Stock_2',
]

CATEGORY_LABELS = {
    'Name': '枪械名称', 'Scope': '倍镜', 'Muzzle': '枪口',
    'Grip': '握把', 'Stock': '枪托',
}


def _get_capture():
    """截取当前屏幕（全屏），返回 BGR 和灰度图。"""
    import mss
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
    img = np.array(shot)
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img, gray


def _find_best_match(roi_gray, category, resolution, threshold=0.18):
    """
    在 category 的所有现有模板中找最佳匹配。
    返回 (template_name, confidence, source_path) 或 (None, 0.0, None)。
    """
    from core.paths import res_path
    from core.recognition import match_sift

    search_dirs = [
        res_path('_internal', 'data', 'firearms', resolution, category),
        res_path('_internal', 'data', 'firearms', 'default', category),
        res_path('_internal', 'data', 'firearms', category),
    ]

    best_score = 0.0
    best_name = None
    best_source = None

    for sd in search_dirs:
        if not os.path.exists(sd):
            continue
        for fname in os.listdir(sd):
            if not fname.lower().endswith('.png'):
                continue
            fpath = os.path.join(sd, fname)
            tmpl = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
            if tmpl is None:
                continue
            score = match_sift(roi_gray, tmpl)
            if score > best_score:
                best_score = score
                best_name = os.path.splitext(fname)[0]
                best_source = fpath
        # 高置信度时不再继续降级搜索
        if best_score > 0.7:
            break

    if best_name and best_score >= threshold:
        return best_name, best_score, best_source
    return None, best_score, best_source


def collect_candidates(resolution, ui_log_callback=None):
    """
    第一阶段：截取屏幕，识别所有背包 ROI，返回候选结果列表。

    :param resolution: 分辨率字符串，如 '2560x1440'
    :param ui_log_callback: 可选日志回调
    :return: (candidates, error_msg)
        candidates: list[dict], 每项包含 roi_type, category, name, confidence, w, h, roi_image
        error_msg: 出错时非 None
    """
    lines = []
    def log(msg):
        lines.append(msg)
        logger.info(msg)
        if ui_log_callback:
            ui_log_callback(msg)

    try:
        from core.paths import res_path
        config_file = res_path('Config', 'roi_config.json')
        if not os.path.exists(config_file):
            return None, "❌ roi_config.json 不存在，请先使用 ROI 工具配置背包坐标"

        with open(config_file, 'r', encoding='utf-8') as f:
            roi_config = json.load(f)

        res_cfg = roi_config.get(resolution, {})
        backpack_roi = roi_config.get('_GUNS_REOLUTION_SETTINGS', {}).get(resolution)
        if not backpack_roi or len(backpack_roi) != 4:
            return None, f"❌ 未配置分辨率 {resolution} 的背包区域 (_GUNS_REOLUTION_SETTINGS)，请先用 ROI 工具配置"

        bx1, by1, bx2, by2 = backpack_roi

        log("📸 正在截取当前屏幕…")
        _, full_gray = _get_capture()
        log(f"✅ 截图成功: {full_gray.shape[::-1]}")
        log(f"📦 背包区域: ({bx1}, {by1}, {bx2}, {by2})")

        candidates = []

        for roi_type in BACKPACK_ROI_TYPES:
            rel_roi = res_cfg.get(roi_type)
            if not rel_roi or len(rel_roi) != 4:
                log(f"⏭️  {roi_type}: 未配置坐标，跳过")
                continue

            rl, rt, rr, rb = rel_roi
            abs_left = bx1 + rl
            abs_top = by1 + rt
            abs_right = bx1 + rr
            abs_bottom = by1 + rb

            w = abs_right - abs_left
            h = abs_bottom - abs_top
            if w <= 0 or h <= 0:
                log(f"⏭️  {roi_type}: 无效坐标 ({w}x{h})，跳过")
                continue

            roi_gray = full_gray[abs_top:abs_bottom, abs_left:abs_right]
            if roi_gray.size == 0:
                log(f"⏭️  {roi_type}: 裁剪区域为空，跳过")
                continue

            category = ROI_TYPE_TO_CATEGORY.get(roi_type)
            if not category:
                continue

            name, conf, source = _find_best_match(roi_gray, category, resolution)

            candidate = {
                'roi_type': roi_type,
                'category': category,
                'category_label': CATEGORY_LABELS.get(category, category),
                'name': name or '无法识别',
                'confidence': conf,
                'match_source': source,
                'w': w,
                'h': h,
                'roi_image': roi_gray,
                'recognized': name is not None,
            }
            candidates.append(candidate)

            if name:
                log(f"🔍  {roi_type} → {name} (置信度: {conf:.2%}, {w}x{h})")
            else:
                log(f"⚠️  {roi_type}: 无法识别 (最高置信度 {conf:.2%}), {w}x{h}")

        return candidates, None

    except Exception as e:
        import traceback
        err = f"❌ 批量模板收集异常: {e}\n{traceback.format_exc()}"
        log(err)
        return None, err


def save_selected(candidates, selected_indices, resolution, name_overrides=None, ui_log_callback=None):
    """
    第二阶段：将选中的候选结果写入文件。

    :param candidates: collect_candidates 返回的结果列表
    :param selected_indices: set[int] 或 list[int]，被选中的下标
    :param resolution: 分辨率字符串
    :param name_overrides: dict[int, str]，手动指定的文件名（不含扩展名）
    :param ui_log_callback: 可选日志回调
    :return: 保存结果字符串
    """
    lines = []
    def log(msg):
        lines.append(msg)
        logger.info(msg)
        if ui_log_callback:
            ui_log_callback(msg)

    from core.paths import res_path

    name_overrides = name_overrides or {}
    saved = 0
    skipped = 0
    for idx in selected_indices:
        c = candidates[idx]

        # 使用手动输入名称（如果提供了覆盖）
        save_name = name_overrides.get(idx) or c['name']

        if not save_name or save_name in ('无法识别', '') or (save_name == c['name'] and not c['recognized']):
            log(f"⏭️  {c['roi_type']}: 未识别且未手动输入名称，跳过保存")
            skipped += 1
            continue

        save_dir = res_path('_internal', 'data', 'firearms', resolution, c['category'])
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f"{save_name}.png")

        # 准备写入图像
        img_to_save = c['roi_image']

        # ✅ CLAHE 预处理：与运行时匹配保持对称
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4))
        img_to_save = clahe.apply(img_to_save)

        # 如果已存在同名模板，调整尺寸保持一致（解决槽1/槽2 ROI框大小不同的问题）
        if os.path.exists(save_path):
            existing = cv2.imread(save_path, cv2.IMREAD_GRAYSCALE)
            if existing is not None:
                eh, ew = existing.shape[:2]
                ih, iw = img_to_save.shape[:2]
                if (eh, ew) != (ih, iw):
                    img_to_save = cv2.resize(img_to_save, (ew, eh), interpolation=cv2.INTER_AREA)
                    log(f"📐  {c['roi_type']}: 缩放 {iw}x{ih} → {ew}x{eh} 以匹配现有模板 {save_name}.png")

        cv2.imwrite(save_path, img_to_save)

        log(f"✅  {c['roi_type']} → {save_name}.png ({img_to_save.shape[1]}x{img_to_save.shape[0]})")
        saved += 1

    summary = (
        f"\n{'='*40}\n"
        f"模板保存完成！\n"
        f"  ✅ 已生成: {saved} 个\n"
        f"  ⏭️  跳过: {skipped} 个（未识别或未选中）\n"
        f"  目录: _internal/data/firearms/{resolution}/{{Name|Scope|Muzzle|Grip|Stock}}/\n"
        f"{'='*40}"
    )
    log(summary)
    return "\n".join(lines)
