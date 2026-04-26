import asyncio
import logging
import simplejson as json
import os
import sys
import threading
import time

import numpy as np
from core.ghub import ghub_device
from core.paths import res_path
from core.recognition import capture_all_positions_thread, recogniseif_firearm, capture_gun_icons, _mss_capture_lock
from core import input_trace as _input_trace
from data.fire_data import KEY_DATA_V3, SCOPE_FACTOR

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "resolution": "1920x1080",
    "scope_factor_v3": {},
    "posture_v3": {},
    "gun_ratio_v3": {},
    "debug_mode": False,
}

class ProcessClass:
    _instance_lock = threading.Lock()
    _Result1 = {}  # 1号枪的识别结果[]
    _Result2 = {}  # 2号枪的识别结果
    _gd = ghub_device()

    @classmethod
    def get_recognition_results(cls):
        return cls._Result1, cls._Result2

    def __new__(cls, *args, **kwargs):
        if not hasattr(ProcessClass, "_instance"):
            with ProcessClass._instance_lock:
                if not hasattr(ProcessClass, "_instance"):
                    # 类加括号就回去执行__new__方法，__new__方法会创建一个类实例：Singleton()
                    ProcessClass._instance = object.__new__(cls)  # 继承object类的__new__方法，类去调用方法，说明是函数，要手动传cls
        return ProcessClass._instance  # obj1

    def __init__(self):
        # ✅ 初始化守卫：单例模式下 __init__ 每次都会被调用，但只需初始化一次
        # 防止识别线程中 ProcessClass() 重复调用导致 TabKey/_ui_log_callback 被重置
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.TabKey = False
        self.ghub_device_info = self._gd.info
        self.window_version = self.get_window_version()
        self.Monitor = self.get_config_data("r")
        self.mouse_one = False  # 是否开枪
        self.Current_firearms = None  # 当前枪械 1号枪2号枪
        self.Current_posture = "None"  # 当前姿态 None 站立 z 趴下 c 蹲下
        self.sensitivity = 1  # 瞄准灵敏度
        self.StartFire = False  # 是否开枪倍镜
        self.RightClick = True  # 右键按下模式 False 单击 True 长按
        self.clicking = False
        self.firstPerson = False # 是否第一人称
        self.ScopeFactorV3 = self.get_config_data('sf3')  # v3 倍镜系数
        self.PostureV3 = self.get_config_data('p3')  # v3 姿态系数
        self.GunRatioV3 = self.get_config_data('gr3')  # v3 独立压枪系数
        self.GunsName = None
        self.recoil_version = 3
        # 全局压枪系数（对应Lua的all_ratio）
        # 默认1.0，3号位武器时降为0.9
        self.all_ratio = 1.0
        
        # ═══ 双模式倍镜状态管理 ═══
        # 用于跟踪 duobei 倍镜的当前模式 (duobei1=低倍, duobei4=高倍)
        # 当识别到 duobei 倍镜时，默认是 duobei1(低倍/红点模式)
        # 通过 Alt+鼠标右键 切换为 duobei4(高倍模式)
        self.duobei_scope_mode = {}  # {gun_slot: 'duobei1' or 'duobei4'}
        
        # ═══ 姿势图片识别配置 ═══
        self.posture_roi = None  # 姿势识别 ROI 区域 (left, top, right, bottom)
        self.posture_templates = {}  # 姿势模板图片缓存
        
        # 从 resolution_setting 加载当前分辨率的姿势 ROI
        self._load_posture_roi_from_resolution()
        
        # ✅ 预加载姿势模板，避免首次识别时的延迟
        self.load_posture_templates()
        
        # ═══ UI 日志回调 ═══
        self._ui_log_callback = None  # 用于将日志输出到 UI
        # F9 / 界面「调试」按钮切换后刷新按钮文字等（可选，由主窗口注册）
        self._on_debug_mode_changed = None
        # 与开镜/姿势等线程错开：Tab 识别持锁期间不并发第二段 asyncio.run
        self._gun_recognize_lock = threading.Lock()
        _cfg = self.get_config_data("a")
        # ✅ 调试模式仅在程序生命周期内有效，默认关闭，不持久化到配置
        self.debug_input_trace = False

        # ═══ 背包识别自愈状态 ═══
        # _tab_fail_count：连续“全 none”的背包识别次数
        # _recognition_failed：HUD 红字警告标志（连续失败 ≥ 阈值时置位）
        # _TAB_FAIL_THRESHOLD：连续失败几次后触发 HUD 警告
        self._tab_fail_count = 0
        self._recognition_failed = False
        self._TAB_FAIL_THRESHOLD = 2

    def move_mouse(self, x, y):
        self._gd.mouse_R(x, y)

    def _config_path(self):
        return res_path('Config', 'config.json')

    def get_config_data(self, mode='r'):
        config_path = self._config_path()
        try:
            with open(config_path, "r", encoding='utf-8') as f:
                Config_data = json.loads(f.read())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("配置文件读取失败，使用默认配置: %s", e)
            Config_data = DEFAULT_CONFIG.copy()
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w", encoding='utf-8') as f:
                f.write(json.dumps(Config_data, ensure_ascii=False, indent=2))

        if mode == 'r':
            return Config_data.get("resolution", "1920x1080")
        elif mode == 'sf3':
            return Config_data.get('scope_factor_v3', {})
        elif mode == 'p3':
            return Config_data.get('posture_v3', {})
        elif mode == 'gr3':
            return Config_data.get('gun_ratio_v3', {})
        elif mode == 'a':
            return Config_data

    def save_config_data(self, mode, data):
        save_data = self.get_config_data('a')
        if mode == 'resolution':
            save_data['resolution'] = data
        elif mode == 'scope_factor_v3':
            save_data['scope_factor_v3'] = data
        elif mode == 'posture_v3':
            save_data['posture_v3'] = data
        elif mode == 'gun_ratio_v3':
            save_data['gun_ratio_v3'] = data
        elif mode in ('debug_mode', 'debug_input_trace'):
            save_data['debug_mode'] = bool(data)
        try:
            with open(self._config_path(), "w", encoding='utf-8') as f:
                f.write(json.dumps(save_data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error("保存配置失败: %s", e)

    def reduction_data(self):
        self.StartFire = False
        self.clicking = False
        self.sensitivity = 1
        self.Current_posture = "None"
        self.Current_firearms = None
        self.mouse_one = False
        self.TabKey = False
        self._Result1 = {}
        self._Result2 = {}
        # 重置双模式倍镜状态
        self.duobei_scope_mode = {}
        # 重置识别自愈状态
        self._tab_fail_count = 0
        self._recognition_failed = False

    def read_gun_data(self, fileName) -> dict:
        """读取 v3 枪械弹道数据（直接读取 JSON）"""
        import json as _json
        key = (fileName or "").strip()
        if not key:
            return None
        gun_path = res_path("_internal", "GunData", f"{key.lower()}.json")
        try:
            with open(gun_path, "r", encoding="utf-8") as f:
                return _json.load(f)
        except FileNotFoundError:
            logger.warning(f"枪械数据文件不存在: {gun_path}")
            return None
        except Exception as e:
            logger.error(f"读取枪械数据失败: {e}")
            return None

    def get_current_scope(self):
        """
        获取当前倍镜名称，支持双模式倍镜(duobei)的状态跟踪
        :return: 倍镜名称字符串
        """
        result = self.get_guns_info()
        if result is None:
            return "none"
        
        scope_name = result.get("Scope", "none")
        
        # 如果是 duobei 倍镜，返回当前模式
        if scope_name in ("duobei1", "duobei4"):
            gun_slot = self.Current_firearms
            if gun_slot and gun_slot in self.duobei_scope_mode:
                return self.duobei_scope_mode[gun_slot]
            # 默认返回低倍模式
            return "duobei1"
        
        return scope_name
    
    def toggle_duobei_scope(self, gun_slot=None):
        """
        切换双模式倍镜 (duobei) 的模式
        :param gun_slot: 枪械槽位 (1或2)，如果不指定则使用当前枪械
        :return: 切换后的倍镜模式名称
        """
        if gun_slot is None:
            gun_slot = self.Current_firearms
        
        if not gun_slot:
            return None
        
        # 获取当前识别的倍镜类型
        result = self._Result1 if gun_slot == 1 else self._Result2
        if not result:
            return None
        
        scope_name = result.get("Scope", "none")
        
        # 只对 duobei 倍镜进行切换
        if scope_name not in ("duobei1", "duobei4"):
            return None
        
        # 切换模式
        current_mode = self.duobei_scope_mode.get(gun_slot, "duobei1")
        new_mode = "duobei4" if current_mode == "duobei1" else "duobei1"
        self.duobei_scope_mode[gun_slot] = new_mode
        
        logger.info(f"枪械{gun_slot} 倍镜切换: {current_mode} -> {new_mode}")
        return new_mode
    
    def reset_duobei_scope(self, gun_slot=None):
        """
        重置双模式倍镜到默认状态(低倍模式)
        :param gun_slot: 枪械槽位，不指定则重置所有
        """
        if gun_slot:
            if gun_slot in self.duobei_scope_mode:
                del self.duobei_scope_mode[gun_slot]
                logger.info(f"枪械{gun_slot} 倍镜已重置为默认(低倍)")
        else:
            self.duobei_scope_mode.clear()
            logger.info("所有枪械倍镜已重置为默认(低倍)")
    
    def _load_posture_roi_from_resolution(self):
        """
        从 roi_config.json 中加载当前分辨率的姿势 ROI
        """
        try:
            import json
            from core.paths import res_path
            
            config_file = res_path('Config', 'roi_config.json')
            if not os.path.exists(config_file):
                logger.warning(f"ROI 配置文件不存在: {config_file}")
                return
            
            with open(config_file, 'r', encoding='utf-8') as f:
                roi_config = json.load(f)
            
            if self.Monitor in roi_config:
                resolution_config = roi_config[self.Monitor]
                posture_roi = resolution_config.get('posture_roi')
                
                if posture_roi:
                    self.posture_roi = tuple(posture_roi)
                    logger.info(f"从 ROI 配置加载姿势 ROI: {self.Monitor} -> {self.posture_roi}")
                else:
                    logger.debug(f"分辨率 {self.Monitor} 未配置姿势 ROI")
            else:
                logger.warning(f"未找到分辨率 {self.Monitor} 的 ROI 配置")
        except Exception as e:
            logger.error(f"加载姿势 ROI 失败: {e}")
    
    def load_posture_templates(self):
        """
        加载姿势模板图片（三级分辨率搜索）
        优先级: {resolution}/zishi/ → default/zishi/ → zishi/
        :return: 是否加载成功
        """
        try:
            import cv2
            import os
            from core.paths import res_path
            
            # ✅ 三级搜索：分辨率目录 → default 目录 → 根目录（与配件模板一致）
            search_dirs = [
                res_path('_internal', 'data', 'firearms', self.Monitor, 'zishi'),
                res_path('_internal', 'data', 'firearms', 'default', 'zishi'),
                res_path('_internal', 'data', 'firearms', 'zishi'),
            ]
            
            # 找出第一个存在的目录
            template_dir = None
            for d in search_dirs:
                if os.path.exists(d):
                    template_dir = d
                    break
            
            if not template_dir:
                logger.warning(f"姿势模板目录不存在，已搜索: {search_dirs}")
                return False
            
            logger.info(f"姿势模板目录: {template_dir}")
            
            # 加载三个姿势模板: None(站立), c(蹲下), z(趴下)
            posture_names = {'None': 'None.png', 'c': 'c.png', 'z': 'z.png'}
            
            for key, filename in posture_names.items():
                template_path = os.path.join(template_dir, filename)
                if os.path.exists(template_path):
                    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
                    if template is not None:
                        self.posture_templates[key] = template
                        logger.info(f"加载姿势模板: {key} ({template.shape})")
                    else:
                        logger.warning(f"无法读取姿势模板: {template_path}")
                else:
                    logger.warning(f"姿势模板文件不存在: {template_path}")
            
            return len(self.posture_templates) > 0
        except Exception as e:
            logger.error(f"加载姿势模板失败: {e}")
            return False
    
    def _save_debug_screenshot(self, screenshot, best_match, best_score, match_scores):
        """
        保存调试截图到文件
        :param screenshot: 原始截图 (BGR)
        :param best_match: 最佳匹配的姿势名称
        :param best_score: 最佳匹配分数
        :param match_scores: 所有匹配分数
        """
        try:
            import cv2
            import os
            from datetime import datetime
            from core.paths import res_path
            
            # 创建调试目录
            debug_dir = res_path('logs', 'posture_debug')
            os.makedirs(debug_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # 精确到毫秒
            result_str = best_match if best_match else 'None'
            filename = f"posture_{result_str}_{best_score:.3f}_{timestamp}.png"
            filepath = os.path.join(debug_dir, filename)
            
            # 在图片上绘制匹配信息
            img_with_info = screenshot.copy() if len(screenshot.shape) == 3 else cv2.cvtColor(screenshot, cv2.COLOR_GRAY2BGR)
            
            # 添加文字信息
            y_offset = 30
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            font_color = (0, 255, 0) if best_score >= 0.7 else (0, 165, 255)  # 绿色或橙色
            
            # 标题
            cv2.putText(img_with_info, f"Result: {result_str} ({best_score:.4f})", 
                       (10, y_offset), font, font_scale, font_color, 2)
            y_offset += 30
            
            # 详细分数
            for name, score in match_scores.items():
                color = (0, 255, 0) if score >= 0.7 else (100, 100, 255)  # 绿色或红色
                marker = "[BEST]" if name == best_match else ""
                text = f"{name}: {score:.4f} {marker}"
                cv2.putText(img_with_info, text, (10, y_offset), font, 0.5, color, 1)
                y_offset += 25
            
            # 保存带标注的图片
            cv2.imwrite(filepath, img_with_info)
            logger.info(f"📸 调试截图已保存: {filepath}")
            
            # 同时保存原始灰度图（用于分析）
            if len(screenshot.shape) == 3:
                gray_path = filepath.replace('.png', '_gray.png')
                gray_img = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                cv2.imwrite(gray_path, gray_img)
                logger.debug(f"灰度图已保存: {gray_path}")
            
        except Exception as e:
            logger.error(f"保存调试截图失败: {e}")
    
    def recognize_posture_from_image(self, screenshot_roi, debug=False):
        """
        从截图区域识别姿势
        :param screenshot_roi: ROI 区域的截图 (numpy array, grayscale)
        :param debug: 是否启用调试模式（保存截图和详细日志）
        :return: 姿势名称 ('None', 'c', 'z') 或 None
        """
        try:
            import cv2
            
            # ✅ 模板已在 __init__ 中预加载，这里只检查是否为空
            if not self.posture_templates:
                logger.warning("⚠️ 姿势模板未加载，请检查模板文件是否存在")
                return None
            
            if screenshot_roi is None or screenshot_roi.size == 0:
                logger.warning("⚠️ 截图为空")
                return None
            
            # 确保是灰度图
            if len(screenshot_roi.shape) == 3:
                screenshot_roi_gray = cv2.cvtColor(screenshot_roi, cv2.COLOR_BGR2GRAY)
            else:
                screenshot_roi_gray = screenshot_roi
            
            logger.debug(f"📊 开始模板匹配，截图尺寸: {screenshot_roi_gray.shape}")
            
            best_match = None
            best_score = -1
            match_scores = {}  # 记录所有匹配分数
            
            # 使用模板匹配
            for posture_name, template in self.posture_templates.items():
                # 如果模板比截图大，缩小模板到截图尺寸而不是跳过
                th, tw = template.shape[:2]
                sh, sw = screenshot_roi_gray.shape[:2]
                if th > sh or tw > sw:
                    logger.debug(f"模板 {posture_name}({template.shape}) 比截图大，缩小到截图尺寸")
                    template = cv2.resize(template, (sw, sh), interpolation=cv2.INTER_AREA)
                
                # 执行模板匹配
                result = cv2.matchTemplate(screenshot_roi_gray, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                # 记录分数
                match_scores[posture_name] = max_val
                
                # 记录最佳匹配
                if max_val > best_score:
                    best_score = max_val
                    best_match = posture_name
            
            # 输出详细的匹配信息
            threshold = 0.5  # ✅ 降低阈值，提高识别率（游戏 UI 有抗锯齿和半透明）
            logger.debug("=" * 50)
            logger.debug("姿势识别结果详情:")
            for name, score in match_scores.items():
                status = "✓" if score >= threshold else "✗"
                logger.debug(f"  {status} {name}: {score:.4f} {'(最佳)' if name == best_match else ''}")
            logger.debug(f"  阈值: {threshold}, 最终结果: {best_match if best_score >= threshold else 'None'}")
            logger.debug("=" * 50)
            
            # 发送详细日志到 UI（仅 debug 模式）
            if debug and hasattr(self, '_ui_log_callback') and self._ui_log_callback:
                summary_lines = ["姿势识别详情:"]
                for name, score in match_scores.items():
                    marker = " ← 最佳" if name == best_match else ""
                    summary_lines.append(f"  {name}: {score:.4f}{marker}")
                result_str = f"{best_match} ({best_score:.4f})" if best_score >= threshold else "None"
                summary_lines.append(f"结果: {result_str}")
                self._ui_log_callback("\n".join(summary_lines))
            
            # 调试模式：保存截图
            if debug:
                self._save_debug_screenshot(screenshot_roi, best_match, best_score, match_scores)
            
            # 设置阈值，只有置信度足够高才认为匹配成功
            if best_score >= threshold and best_match:
                logger.info(f"✅ 姿势识别成功: {best_match} (置信度: {best_score:.4f})")
                return best_match
            else:
                logger.debug(f"⚠️ 姿势识别失败: 最佳匹配 {best_match} 置信度 {best_score:.4f} < 阈值 {threshold}")
                return None
                
        except Exception as e:
            import traceback
            logger.error(f"姿势识别失败: {e}\n{traceback.format_exc()}")
            return None
    
    def capture_and_recognize_posture(self, debug=False):
        """
        截取 ROI 区域并识别姿势
        :param debug: 是否启用调试模式（保存截图）
        :return: 识别到的姿势名称或 None
        """
        try:
            import mss
            import numpy as np
            import cv2  # 导入 OpenCV
            
            if not self.posture_roi:
                logger.warning("⚠️ 姿势识别 ROI 未配置")
                # 输出到 UI
                if hasattr(self, '_ui_log_callback') and self._ui_log_callback:
                    self._ui_log_callback("⚠️ 姿势识别 ROI 未配置，请使用 F8 配置姿势 ROI")
                return None
            
            left, top, right, bottom = self.posture_roi
            width = right - left
            height = bottom - top
            
            if width <= 0 or height <= 0:
                logger.warning(f"⚠️ 无效的 ROI 区域: {self.posture_roi}")
                if hasattr(self, '_ui_log_callback') and self._ui_log_callback:
                    self._ui_log_callback(f"⚠️ 无效的 ROI 区域: {self.posture_roi}")
                return None
            
            logger.info(f"📷 开始姿势识别 (ROI: {self.posture_roi}, 调试: {debug})")
            _input_trace.log(
                "姿势识别 开始 ROI=%s StartFire=%s TabKey=%s",
                self.posture_roi,
                self.StartFire,
                self.TabKey,
            )
            # 输出到 UI
            if hasattr(self, '_ui_log_callback') and self._ui_log_callback:
                self._ui_log_callback(f"📷 开始姿势识别...")
            
            # 截取屏幕区域（与枪械识别共用 mss 串行锁）
            with _mss_capture_lock:
                with mss.mss() as sct:
                    monitor = {"top": top, "left": left, "width": width, "height": height}
                    screenshot = sct.grab(monitor)
            img = np.array(screenshot)
            if img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            posture = self.recognize_posture_from_image(img, debug=debug)
            _input_trace.log("开镜姿势识别 结果=%s StartFire=%s TabKey=%s", posture, self.StartFire, self.TabKey)

            if posture is None and debug:
                if hasattr(self, "_ui_log_callback") and self._ui_log_callback:
                    self._ui_log_callback("⚠️ 姿势识别失败，请查看 logs/posture_debug/ 目录中的截图")

            return posture

        except Exception as e:
            import traceback
            logger.error(f"截取并识别姿势失败: {e}\n{traceback.format_exc()}")
            if hasattr(self, '_ui_log_callback') and self._ui_log_callback:
                self._ui_log_callback(f"❌ 姿势识别异常: {e}")
            return None

    def get_window_version(self):
        if not hasattr(sys, 'getwindowsversion'):
            return False
        windows_version = sys.getwindowsversion()
        if windows_version.build >= 22000:
            return True
        return False

    def get_guns_result(self):
        """
        获取枪械识别结果
        :return:
        """
        return [self._Result1, self._Result2]

    def recognize_all_guns_info(self, Emit):
        """
        枪械配件识别
        :return:
        """
        _input_trace.log(
            "Tab识别 请求开始 TabKey=%s Monitor=%s", self.TabKey, self.Monitor
        )
        if not self._gun_recognize_lock.acquire(blocking=True, timeout=5.0):
            logger.error("Tab 识别等待超时（5s），强制跳过（可能锁异常）")
            _input_trace.log("Tab识别 等待超时，跳过")
            return
        
        try:
            if not self.TabKey:
                _input_trace.log("Tab识别 已取消(背包关)")
                return

            # ✅ 优化：降低等待时间（180ms → 100ms），提升响应速度
            time.sleep(0.10)
            if not self.TabKey:
                _input_trace.log("Tab识别 等待UI后已取消(背包关)")
                return
            t0 = time.perf_counter()
            Data = asyncio.run(capture_all_positions_thread(self.Monitor))
            if not self.TabKey:
                _input_trace.log("Tab识别 完成但已关背包，丢弃 (耗时=%.2fs)", time.perf_counter() - t0)
                return
            self._Result1 = Data[0]
            self._Result2 = Data[1]
            _input_trace.log(
                "Tab识别 完成 耗时=%.2fs 槽1Name=%s 槽2Name=%s",
                time.perf_counter() - t0,
                self._Result1.get("Name") if self._Result1 else None,
                self._Result2.get("Name") if self._Result2 else None,
            )

            # ✅ 自愈机制：检测“全 none”的无效识别，避免 Tab 误点导致状态卡死
            # 规则：两个槽位的 Name/Scope/Muzzle/Grip/Stock 全部为 none 或空 → 视为失败
            def _slot_all_empty(res):
                if not res:
                    return True
                for k in ("Name", "Scope", "Muzzle", "Grip", "Stock"):
                    v = str(res.get(k, "") or "").lower()
                    if v and v not in ("none", ""):
                        return False
                return True

            both_empty = _slot_all_empty(self._Result1) and _slot_all_empty(self._Result2)
            if both_empty:
                self._tab_fail_count += 1
                self.TabKey = False  # 自愈：无效识别重置 Tab 标志，下次按 Tab 即重新识别
                _input_trace.log(
                    "Tab识别 全none自愈 重置TabKey=False 失败计数=%d/%d",
                    self._tab_fail_count, self._TAB_FAIL_THRESHOLD,
                )
                if self._tab_fail_count >= self._TAB_FAIL_THRESHOLD:
                    self._recognition_failed = True
                    Emit("l", (
                        f"⚠️ 连续 {self._tab_fail_count} 次背包识别全部失败，HUD 已警告。"
                        f"请确认：(1) 在游戳内按 Tab 打开背包；(2) 分辨率匹配；(3) ROI 区域配置正确。",
                    ))
                else:
                    Emit("l", (f"⚠️ 背包识别全部为空，已重置 Tab 标志（失败 {self._tab_fail_count}/{self._TAB_FAIL_THRESHOLD}）",))
            else:
                # 识别成功：清除失败计数与警告标志
                if self._tab_fail_count > 0 or self._recognition_failed:
                    Emit("l", ("✅ 背包识别恢复正常",))
                self._tab_fail_count = 0
                self._recognition_failed = False

            logger.info(f"✅ 准备发送 UI 更新信号: Emit('g')")
            Emit("g", (None,))
            logger.info(f"✅ 已发送 UI 更新信号")
        finally:
            try:
                self._gun_recognize_lock.release()
                _input_trace.log("Tab识别 已释放锁")
            except RuntimeError as e:
                logger.warning(f"Tab识别 释放锁失败: {e}")

    def Change_firearms(self, keyWord):
        """
        枪械切换
        :param keyWord:按键编码
        :return:
        """
        if keyWord == "x":
            self.Current_firearms = None
            self.all_ratio = 1.0  # 无武器时恢复默认
        else:
            self.Current_firearms = int(keyWord)
            # Lua: 3号位武器(wbflag=='3')时 all_ratio=0.9
            # 对应 Python 中 Current_firearms==3 (手枪位)
            self.all_ratio = 0.9 if self.Current_firearms == 3 else 1.0

    def recognize_gun_icons(self, Emit=None):
        """
        从 HUD 右下角识别枪械图标，作为背包识别的**独立双源**，不相互覆盖。

        关键设计（用户可见的冲突提示）：
        - Tab 背包识别结果→ _Result*["Name"]（压枪算法权威来源）
        - HUD 图标识别结果→ _Result*["Name_hud"]（**不**覆盖权威字段，只做旁证）
        - 两者均保留，overlay_hud 绘制层检测 Name != Name_hud 时 → 给出冲突提示，
          用户自己判断哪个源准确，必要时重按 Tab 决斗。
        - 原因：单源每当有错识，自动覆盖会让用户无感知；双源并列让误差浮出水面。
        当前持枪由按键 1/2 驱动，HUD 不再改写 Current_firearms。
        """
        try:
            result = capture_gun_icons(self.Monitor)
            if not result:
                logger.warning("枪械图标识别失败（未配置 HUD ROI 或截图失败）")
                return

            gun1_name = result.get("Gun_1", "none")
            gun2_name = result.get("Gun_2", "none")

            # 双源并存：HUD 写入 Name_hud 独立字段，不触碰权威 Name
            conflicts = []
            for slot_idx, hud_name, result_attr in (
                (1, gun1_name, '_Result1'),
                (2, gun2_name, '_Result2'),
            ):
                existing = getattr(self, result_attr, None)
                if not existing:
                    existing = {}
                    setattr(self, result_attr, existing)

                # 无论 HUD 识别到什么，都写入 Name_hud（无值时写 none 保持一致）
                existing["Name_hud"] = hud_name

                existing_name = str(existing.get("Name", "") or "").lower()
                hud_name_l = str(hud_name or "").lower()
                has_bag = existing_name and existing_name not in ("none", "")
                has_hud = hud_name_l and hud_name_l not in ("none", "")

                if has_bag and has_hud and existing_name != hud_name_l:
                    conflicts.append((slot_idx, existing_name, hud_name_l))
                    logger.warning(
                        f"枪械识别冲突 槽{slot_idx}: 背包={existing_name} vs HUD={hud_name_l}（两源并存，不自动决断）"
                    )
                elif has_hud and not has_bag:
                    # 背包未识别过（用户还没按过 Tab）：容许 HUD 充当临时数据源，但标记 Name 仅旁证
                    existing["Name"] = hud_name_l  # 作为临时 Name，供压枪使用
                    logger.info(f"HUD 临时填补槽{slot_idx} Name={hud_name_l}（背包未识别，建议按 Tab 确认）")

            _input_trace.log(
                "枪械图标识别 完成 Gun_1=%s Gun_2=%s 当前持枪=%s(按键驱动) 冲突=%s",
                gun1_name, gun2_name, self.Current_firearms, conflicts or "无"
            )

            if Emit:
                Emit('g', (None,))  # 刷新 UI显示
                if conflicts:
                    parts = [f"槽{s}：背包={b}/HUD={h}" for s, b, h in conflicts]
                    Emit('l', (f"⚠️ 识别源冲突，建议重按 Tab 确认：{'; '.join(parts)}",))

        except Exception as e:
            logger.error(f"枪械图标识别异常: {e}")
            _input_trace.log("枪械图标识别 异常: %s", e)

    def IF_Open_Lens(self):
        self.StartFire = recogniseif_firearm(self.Monitor)

    def Change_posture(self, keyWord):
        """
        姿势切换
        :param keyWord:按键编码
        :return:
        """
        if keyWord == "space" or self.Current_posture == keyWord:
            self.Current_posture = "None"
        else:
            self.Current_posture = keyWord

    def calculate_the_recoil(self, recoil, posture, scope):
        """
        计算本 tick 应下发的垂直鼠标移动量（与 GunData 单元素含义一致）。

        合成公式: ``posture * (recoil * scope)``，乘法结合顺序与 ``recoil * scope * posture`` 等价。

        - ``recoil``: GunData 数组中当前 tick 的基准补偿值（无单位系数，相对表）。
        - ``scope``: 来自 ``ScopeData`` 的倍镜/机瞄灵敏度倍率；放大倍率越高，同等 ``recoil`` 需要更大的鼠标下移量。
        - ``posture``: 枪械 JSON 中站姿/蹲/趴等姿态系数；不同姿态后坐力表现不同，与 ``recoil`` 相乘体现姿态对补偿的缩放。

        三者相乘得到「本 tick 理论像素/驱动单位位移」，再 ``int(round(...))`` 取整为整数。
        """
        recoil_value = posture * (recoil * scope)
        return int(round(recoil_value))  # 返回整数

    def get_guns_info(self):
        if self.Current_firearms == 1:
            return self._Result1
        elif self.Current_firearms == 2:
            return self._Result2
        else:
            return None

    def FIRE_Start(self, Emit):
        """
        压枪宏入口 (v3)：校验状态 → 读枪 JSON → ``_fire_start_v3`` / ``FIRE_v3``。

        不在此函数内做识别；识别由其他线程/回调更新 ``_Result*``、``StartFire`` 等状态。
        """
        # 判断数据是否准确
        Judge_List = (self.StartFire, self.Current_firearms, self._Result1, self._Result2)
        LogInfo_List = ("当前没有开启倍镜，无需压枪", "当前没有装备枪械，无需压枪", "还未进行枪械识别，无需压枪",
                        "还未进行枪械识别，无需压枪")
        for i in range(len(Judge_List)):
            if not Judge_List[i]:
                return Emit("l", (LogInfo_List[i],))

        # 获取当前枪械识别情况数据
        guns_info = self.get_guns_info()
        if not guns_info:
            return Emit("l", ("当前装备不是枪械，无需压枪",))
        # 获取枪械名称
        gunsName = guns_info.get("Name", "None")
        if gunsName == "None" or not gunsName:
            return Emit("l", ("未检测到枪械",))
        # 获取枪械数据 枪械对应json数据
        gun = self.read_gun_data(gunsName)
        if not gun:
            return Emit("l", ("枪械数据不存在",))

        return self._fire_start_v3(gun, guns_info, Emit)

    def get_accessories_nameCode_v3(self, guns_info):
        """
        获取配件编码 (v3 格式: ABCD 4位码，含镜组)
        与 Lua 脚本 / data.txt 的编码完全一致:
          A=镜组(1=低倍镜,2=高倍镜), B=枪口, C=握把, D=枪托
        :param guns_info:识别枪械的数据
        :return: ABCD 4位字符串，如 "1231"
        """
        scope_name = guns_info.get("Scope", "None").lower()
        a_code = KEY_DATA_V3["Scope"].get(scope_name, "1")

        muzzle_name = guns_info.get("Muzzle", "None").lower()
        b_code = KEY_DATA_V3["Muzzle"].get(muzzle_name, "0")

        grip_name = guns_info.get("Grip", "None").lower()
        c_code = KEY_DATA_V3["Grip"].get(grip_name, "0")

        stock_name = guns_info.get("Stock", "None").lower()
        d_code = KEY_DATA_V3["Stock"].get(stock_name, "0")

        return a_code + b_code + c_code + d_code

    def Computation_latency(self, latency):
        if self.window_version:
            return (latency - 0) / 1000
        return latency / 1000

    # ═══════════════════════════════════════════
    # v3 开火路径：per-tick 直接下发 + ABCD key + Lua 公式
    # 完全对齐 Lua 脚本的压枪体系
    # ═══════════════════════════════════════════

    def _fire_start_v3(self, gun, guns_info, Emit):
        """v3 格式入口：使用 ABCD 4位码查找弹道数据，调用 FIRE_v3。

        v3 与 v2 的核心区别:
        - key 使用 ABCD 4位码（含镜组 A 位），与 data.txt/Lua 脚本一致
        - 每把枪有独立 gun_ratio（来自 Lua 脚本的 xxx_ratio）
        - scope 使用 scope_map（来自 Lua 脚本的 ratiobj），不再依赖 config.json
        - 姿态系数来自 Lua 脚本（蹲=0.7, 趴=0.8）
        - 公式: ymove = ceil(gun_ratio * scope_factor * posture_factor * y)
        """
        abcd_code = self.get_accessories_nameCode_v3(guns_info)
        recoil_data = gun.get("recoil", {}).get(abcd_code)

        # 降级匹配：先尝试去掉枪托(D→0)，再尝试裸枪(B0C0D0)
        if not recoil_data:
            fallback1 = abcd_code[:3] + "0"  # ABC0
            recoil_data = gun.get("recoil", {}).get(fallback1)
            if recoil_data:
                Emit("l", (f"配件 {abcd_code} 无精确弹道，降级使用 {fallback1}",))

        if not recoil_data:
            fallback2 = abcd_code[0] + "000"  # A000 裸枪
            recoil_data = gun.get("recoil", {}).get(fallback2)
            if recoil_data:
                Emit("l", (f"配件 {abcd_code} 无弹道数据，降级使用裸枪 {fallback2}",))

        # A=2 降级 A=1：如果高倍镜没有数据，用低倍镜的
        if not recoil_data and abcd_code[0] == "2":
            fallback3 = "1" + abcd_code[1:]
            recoil_data = gun.get("recoil", {}).get(fallback3)
            if recoil_data:
                Emit("l", (f"配件 {abcd_code} 无高倍镜数据，降级使用低倍镜 {fallback3}",))

        if not recoil_data:
            return Emit("l", (f"配件组合 {abcd_code} 无弹道数据",))

        y_array = recoil_data.get("y", [])
        x_array = recoil_data.get("x", [])
        d_sequence = recoil_data.get("d_sequence")
        if not y_array:
            return Emit("l", ("弹道数据为空",))

        # gun_ratio: 独立压枪系数
        # 优先使用 config.json 的 gun_ratio_v3（用户可在UI调整），
        # 否则使用 JSON 内的 gun_ratio（Lua 默认值）
        weapon_name = gun.get("weapon", "")
        if self.GunRatioV3 and weapon_name in self.GunRatioV3:
            gun_ratio = self.GunRatioV3[weapon_name]
        else:
            gun_ratio = gun.get("gun_ratio", 1.0)

        # scope_factor: 倍镜系数
        # 优先使用 config.json 的 scope_factor_v3（用户可在UI调整），
        # 否则使用 JSON 内的 scope_map（Lua 默认值），最后回退到 SCOPE_FACTOR
        # 注意：使用 get_current_scope() 获取切换后的倍镜模式（支持双模式倍镜）
        scope_name = self.get_current_scope().lower()
        
        # 获取基础scope_factor
        if self.ScopeFactorV3 and scope_name in self.ScopeFactorV3:
            scope_factor = self.ScopeFactorV3[scope_name]
        else:
            scope_factor = gun.get("scope_map", SCOPE_FACTOR).get(scope_name, 1.0)
        
        # 如果Shift按下，应用该倍镜对应的Shift倍率 - 使用Windows API实时检测
        try:
            import ctypes
            # 使用Windows API检测Shift键状态 (VK_SHIFT = 0x10)
            shift_pressed = ctypes.windll.user32.GetKeyState(0x10) & 0x8000 != 0
            
            if shift_pressed and self.ScopeFactorV3:
                # 从 scope_factor_v3 中读取对应倍镜的 shift 系数
                # 命名规则: {scope_name}_shift (例如: hongdian_shift, 4bei_shift)
                shift_key = f"{scope_name}_shift"
                if shift_key in self.ScopeFactorV3:
                    shift_multiplier = float(self.ScopeFactorV3[shift_key])
                    # 使用乘法，默认1.0表示无变化
                    scope_factor *= shift_multiplier
        except Exception:
            # 如果检测失败，忽略Shift倍率
            pass

        # posture_factor: 姿态系数
        # 优先使用 config.json 的 posture_v3（用户可在UI调整），
        # 否则使用 JSON 内的 posture（Lua 默认值）
        posture_key = self.Current_posture.lower()
        if self.PostureV3 and posture_key in self.PostureV3:
            posture_factor = self.PostureV3[posture_key]
        else:
            posture_factor = gun.get("posture", {}).get(posture_key, 1.0)

        # tick_ms 和 has_variable_d
        tick_ms = gun.get("tick_ms", 28)
        has_variable_d = gun.get("has_variable_d", False)

        # 趴下判断：Lua 中趴下时 ratio_zong=0.8 是固定值，不含 gun_ratio 和 ratiobj
        # Current_posture: "None"=站立, "c"=蹲下, "z"=趴下
        prone = (posture_key == "z")

        return self.FIRE_v3(gun_ratio, scope_factor, posture_factor,
                            y_array, x_array, tick_ms, has_variable_d, d_sequence, Emit, prone,
                            self.all_ratio)

    def FIRE_v3(self, gun_ratio, scope_factor, posture_factor,
                y_array, x_array, tick_ms, has_variable_d=False,
                d_sequence=None, Emit=None, prone=False, all_ratio=1.0):
        """
        v3 压枪核心：per-tick 直接下发，完全对齐 Lua 脚本。

        Lua 压枪公式 (站立/蹲下):
          ratio_zong = lj * all_ratio * GunRatio[noweapon] * ratiobj * dra
          ymove = math.ceil(ditu * ratio_zong * data.y)
          简化后（ditu=1, lj=1, all_ratio=1）:
          ymove = ceil(gun_ratio * scope_factor * dra * y)

        Lua 压枪公式 (趴下):
          ratio_zong = 0.8  ← 固定值！不含 GunRatio、ratiobj、dra
          ymove = math.ceil(ditu * 0.8 * data.y)

        与 Lua 的精确对齐:
        - 无 remainder 累积（Lua 每 tick 独立 ceil，不做亚像素追踪）
        - 趴下时 ratio_zong=0.8 是固定值（不含 gun_ratio 和 scope_factor）
        - 取整统一使用 math.ceil（与 Lua 一致）
        - 水平补偿：纯随机 -1~1（Lua 模式2 不使用 data.x）
        - 支持变 d 值武器（如 MK14: 前7 tick d=3, 后续 d=24）
        """
        import math
        import random

        recoil_list = []

        for i in range(len(y_array)):
            if not self.mouse_one:
                break
            Emit('x', (True,))

            # ── 垂直补偿 ──
            # 趴下特殊处理：Lua 中趴下时 ratio_zong=0.8 是固定值
            # 不含 GunRatio、ratiobj（scope_factor），与站立/蹲下完全不同
            if prone:
                # Lua: if zhan==0 then ratio_zong = 0.8 end
                # ymove = ceil(ditu * 0.8 * data.y)
                y_move = math.ceil(0.8 * y_array[i])
            else:
                # Lua: ratio_zong = lj * all_ratio * GunRatio * ratiobj * dra
                # ymove = ceil(ditu * ratio_zong * data.y)
                # 无 remainder 累积！Lua 每 tick 独立 ceil
                y_move = math.ceil(all_ratio * gun_ratio * scope_factor * posture_factor * y_array[i])

            # ── 水平补偿 ──
            # 固定为0,不使用随机偏移
            x_move = 0

            self._gd.mouse_R(x_move, y_move)
            recoil_list.append(y_move)

            # ── 延时 ──
            # Lua: 绝对时间同步 Sleep3(timestart)，Python 只能用相对 sleep
            if has_variable_d and d_sequence and i < len(d_sequence):
                latency = self.Computation_latency(d_sequence[i])
            else:
                latency = self.Computation_latency(tick_ms)
            time.sleep(latency)

        Emit('x', (False,))
        return recoil_list

