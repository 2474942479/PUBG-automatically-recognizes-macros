"""
ONNX 图像分类推理封装（YOLOv8-cls 导出的 ONNX 模型）。

工作流程:
  1. 程序启动 → 检查 _internal/models/ 下是否有 ONNX 模型
  2. 有模型 → 加载 onnxruntime 推理，返回 (标签, 置信度)
  3. 无模型 / onnxruntime 未安装 / 推理失败 → 返回 None，调用方自动回退模板匹配

模型文件命名规则 (放入 _internal/models/ 目录):
  name_cls.onnx           — ONNX 模型权重
  name_cls_labels.json    — 类别标签列表 ["m416", "akm", ...]
  name_cls_meta.json      — 元数据 {"imgsz": 224, ...}

环境变量:
  PUBG_ONNX_CONF  — 置信度阈值，默认 0.8；低于此值认为"不可信"，回退模板匹配
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.paths import res_path

logger = logging.getLogger(__name__)

# ============================================================
# 类别映射：ROI 类型名 -> (ONNX 文件名前缀, 默认输入尺寸)
# 与 tools/train_classifier.py 中的 CATEGORY_CONFIG 一一对应
# ============================================================
_CATEGORY_STEM_DEFAULT_IMGSZ: Dict[str, Tuple[str, int]] = {
    "Name":   ("name_cls",     224),   # 枪械名称（背包 Tab）
    "Scope":  ("scope_cls",    128),   # 倍镜
    "Muzzle": ("muzzle_cls",   128),   # 枪口
    "Grip":   ("grip_cls",     128),   # 握把
    "Stock":  ("stock_cls",    128),   # 枪托
    "gun":    ("gun_hud_cls",  128),   # HUD 武器图标
    "zishi":  ("posture_cls",  128),   # 姿势（站/蹲/趴）
}


def _default_conf_threshold() -> float:
    """读取环境变量 PUBG_ONNX_CONF，默认 0.8"""
    raw = os.environ.get("PUBG_ONNX_CONF", "0.8").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.8


# ============================================================
# 全局缓存（进程级单例，避免重复加载）
# ============================================================
_sessions: Dict[str, Any] = {}              # stem -> InferenceSession
_labels_cache: Dict[str, List[str]] = {}    # stem -> ["m416", "akm", ...]
_meta_cache: Dict[str, Dict[str, Any]] = {} # stem -> {"imgsz": 224, ...}
_init_logged: Dict[str, bool] = {}          # 记录首次加载日志，避免刷屏


def _try_import_onnxruntime():
    """尝试导入 onnxruntime，未安装时返回 None（程序正常运行）"""
    try:
        import onnxruntime as ort
        return ort
    except ImportError:
        return None


def _models_dir() -> str:
    """ONNX 模型存放目录: _internal/models/"""
    return res_path("_internal", "models")


def _load_labels(stem: str) -> Optional[List[str]]:
    """加载类别标签列表（JSON 数组）"""
    if stem in _labels_cache:
        return _labels_cache[stem]
    p = os.path.join(_models_dir(), f"{stem}_labels.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            _labels_cache[stem] = [str(x) for x in data]
            logger.debug("[ONNX] 已加载标签 %s: %d 类", stem, len(_labels_cache[stem]))
            return _labels_cache[stem]
    except Exception as e:
        logger.warning("[ONNX] 读取标签文件失败 %s: %s", p, e)
    return None


def _load_meta_imgsz(stem: str, default: int) -> int:
    """从 meta.json 读取模型训练时的 imgsz"""
    if stem in _meta_cache:
        return int(_meta_cache[stem].get("imgsz", default))
    p = os.path.join(_models_dir(), f"{stem}_meta.json")
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                _meta_cache[stem] = json.load(f)
            return int(_meta_cache[stem].get("imgsz", default))
        except Exception:
            pass
    return default


def _get_session(stem: str):
    """获取或创建 ONNX 推理会话（单例缓存）"""
    if stem in _sessions:
        return _sessions[stem]
    ort = _try_import_onnxruntime()
    if ort is None:
        if not _init_logged.get("_no_ort"):
            logger.info("[ONNX] onnxruntime 未安装，全部使用模板匹配")
            _init_logged["_no_ort"] = True
        return None
    onnx_path = os.path.join(_models_dir(), f"{stem}.onnx")
    if not os.path.isfile(onnx_path):
        if not _init_logged.get(stem):
            logger.debug("[ONNX] 模型文件不存在: %s", onnx_path)
            _init_logged[stem] = True
        return None
    try:
        sess = ort.InferenceSession(
            onnx_path,
            providers=["CPUExecutionProvider"],
        )
        _sessions[stem] = sess
        logger.info("[ONNX] 已加载模型: %s", onnx_path)
        return sess
    except Exception as e:
        logger.warning("[ONNX] 加载模型失败 %s: %s", onnx_path, e)
        return None


def _preprocess_bgr_or_gray(img: np.ndarray, imgsz: int) -> np.ndarray:
    """
    将 ROI 图像预处理为 ONNX 输入格式。
    输入: HWC BGR 或单通道灰度 uint8
    输出: NCHW float32 RGB [0,1]，形状 (1, 3, imgsz, imgsz)
    """
    import cv2

    if img is None or img.size == 0:
        raise ValueError("empty image")
    # 统一转为 3 通道 BGR
    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    # 缩放到模型训练时的输入尺寸
    img = cv2.resize(img, (imgsz, imgsz), interpolation=cv2.INTER_LINEAR)
    # BGR -> RGB -> float32 归一化到 [0, 1]
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    # HWC -> CHW -> NCHW
    chw = np.transpose(rgb, (2, 0, 1))
    return np.expand_dims(chw, axis=0)


def classify_roi(
    img_gray_or_bgr: np.ndarray,
    category: str,
) -> Optional[Tuple[str, float]]:
    """
    对 ROI 图像做 CNN 分类。

    :param img_gray_or_bgr: 灰度或 BGR 的 ROI 图像（numpy 数组）
    :param category: 类别名，如 Name / Scope / Muzzle / Grip / Stock / gun / zishi
    :return: (标签名, 置信度) 或 None（模型缺失/推理失败时返回 None，调用方回退模板匹配）
    """
    cat = category.strip()
    if cat not in _CATEGORY_STEM_DEFAULT_IMGSZ:
        return None
    stem, default_imgsz = _CATEGORY_STEM_DEFAULT_IMGSZ[cat]

    # 加载 ONNX 会话（首次会打日志）
    sess = _get_session(stem)
    if sess is None:
        return None

    # 加载类别标签
    labels = _load_labels(stem)
    if not labels:
        return None

    # 从 meta.json 读取训练时的 imgsz
    imgsz = _load_meta_imgsz(stem, default_imgsz)

    # 预处理
    try:
        blob = _preprocess_bgr_or_gray(img_gray_or_bgr, imgsz)
    except Exception as e:
        logger.debug("[ONNX] 预处理失败(%s): %s", cat, e)
        return None

    # 推理
    inp = sess.get_inputs()[0]
    out = sess.run(None, {inp.name: blob})
    if not out:
        return None

    logits = np.asarray(out[0]).reshape(-1)

    # softmax（数值稳定版）
    mx = float(np.max(logits))
    ex = np.exp(logits - mx)
    probs = ex / (np.sum(ex) + 1e-9)
    idx = int(np.argmax(probs))
    conf = float(probs[idx])

    if idx >= len(labels):
        logger.warning("[ONNX] 输出索引 %d 超出标签数 %d", idx, len(labels))
        return None

    label = labels[idx]
    return label, conf


def should_trust(confidence: float) -> bool:
    """判断 ONNX 分类结果是否可信（置信度 >= 阈值）"""
    return confidence >= _default_conf_threshold()


def clear_classifier_cache():
    """清空所有缓存（模型热重载时调用）"""
    global _sessions, _labels_cache, _meta_cache, _init_logged
    _sessions = {}
    _labels_cache = {}
    _meta_cache = {}
    _init_logged = {}
    logger.info("[ONNX] 分类器缓存已清空")
