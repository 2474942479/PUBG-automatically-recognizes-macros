from threading import Thread  # 导入线程模块，用于多线程操作
from PyQt5.QtCore import QThread, pyqtSignal  # 导入PyQt5的线程和信号模块
import keyboard  # 导入keyboard库，用于全局键盘事件监听
import logging  # 导入日志模块

from core import input_trace as _input_trace

logger = logging.getLogger(__name__)  # 创建 logger 实例

class AppMainKeyListener(QThread):  # 定义键盘监听器类，继承自QThread
    keyInfo = pyqtSignal(str, tuple)  # 定义信号，用于发送键盘事件信息
    roi_config_requested = pyqtSignal()  # 定义信号，用于请求打开 ROI 配置
    batch_template_requested = pyqtSignal()  # 定义信号，用于请求批量生成模板

    def __init__(self, PCdata):  # 初始化方法
        super().__init__()  # 调用父类的初始化方法
        self.KeyHook = None  # 初始化键盘钩子
        self.PC = PCdata  # 保存PC对象引用
        self.alt_pressed = False  # Alt键状态标记
        self.ctrl_pressed = False  # Ctrl键状态标记

    def on_key_pressed(self, event):  # 键盘按下事件处理方法
        try:
            Keys = event.name  # 获取按键名称
            if Keys:
                Keys = Keys.lower()  # 统一转换为小写，避免 Shift 导致的大小写问题
        except Exception:
            return
        
        if not Keys:
            return
        
        # 只处理必要的按键，其他按键立即返回
        # ✅ 添加 Tab 键防抖，避免快速切换导致状态混乱
        if Keys == "tab":  # 如果按下Tab键
            import time
            current_time = time.time()
            
            # 检查是否在防抖时间内（500ms）
            # 过长防抖会导致软件 TabKey 与游戏背包不同步，进而截屏时机错误；此处仅防连点
            if hasattr(self, '_last_tab_time') and (current_time - self._last_tab_time) < 0.12:
                logger.debug("Tab 键防抖：忽略连点")
                return
            
            self._last_tab_time = current_time
            
            # 切换背包状态
            self.PC.TabKey = not self.PC.TabKey
            _input_trace.log(
                "Tab键 -> TabKey=%s StartFire=%s",
                self.PC.TabKey,
                self.PC.StartFire,
            )
            
            if self.PC.TabKey:
                # 第一次按 Tab：打开背包，进行识别
                self.PC.StartFire = False  # 设置开镜状态为False
                self.keyInfo.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
                self.keyInfo.emit('l', ("📦 背包已打开，等待UI渲染...",))
                
                # ✅ 保留旧数据，直接启动识别线程
                # 识别完成后会自动更新 _Result1/2 并刷新 UI
                Thread(target=self.PC.recognize_all_guns_info, args=(self.keyInfo.emit,)).start()
            else:
                # 第二次按 Tab：关闭背包，✅ 不清空识别结果，保留已识别的枪械信息
                self.keyInfo.emit('l', ("📦 背包已关闭",))
        elif Keys in "12!@":  # 如果按下1、2或Shift+1(!)、Shift+2(@)
            # 将特殊符号映射回数字
            key_map = {'!': '1', '@': '2'}
            actual_key = key_map.get(Keys, Keys)
            slot_num = int(actual_key)

            self.PC.StartFire = False  # 设置开镜状态为False
            self.keyInfo.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号

            # ✅ 双源冲突解决：若当前槽位存在未解决冲突，按 1/2 = 接受 HUD 结果
            if self.PC._conflict_pending.get(slot_num):
                self.PC.confirm_hud_result(slot_num, self.keyInfo.emit)

            self.PC.Change_firearms(actual_key)  # 先切换枪械槽位
            self.keyInfo.emit('e', (self.PC.Current_firearms,))  # 发送枪械信息信号
            # ✅ 触发枪械图标识别（异步线程，不阻塞按键处理）
            Thread(target=self.PC.recognize_gun_icons, args=(self.keyInfo.emit,)).start()
        elif Keys in "345gx#$":  # 如果按下3、4、5、g、x或Shift+3(#)、Shift+4($)
            self.PC.StartFire = False  # 设置开镜状态为False
            self.keyInfo.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
        elif Keys in "~`":  # 如果按下波浪号键（包括Shift+`）
            self.PC.StartFire = False  # 设置开镜状态为False
            self.keyInfo.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
        elif Keys in "zc" or Keys == "space":  # 如果按下z、c或空格键
            self.PC.Change_posture(Keys)  # 更改姿态
            self.keyInfo.emit('p', (self.PC.Current_posture,))  # 发送姿态信息信号
        elif Keys == "v":  # 切换视角
            self.PC.firstPerson = not self.PC.firstPerson  # 更改视角
            self.keyInfo.emit('v', (self.PC.firstPerson,))  # 发送视角信息信号
        elif Keys == "insert":  # 如果按下Insert键
            self.PC.reduction_data()  # 重置数据
            self.keyInfo.emit('c', (None,))  # 发送重置数据信号
            self.keyInfo.emit('l', ("🔄 已重置所有状态（包括背包关闭）",))
        elif Keys == "delete":  # 如果按下Delete键
            # 只重置双模式倍镜状态，不影响其他设置
            self.PC.reset_duobei_scope()
            self.keyInfo.emit('l', ("倍镜模式已重置为默认(低倍)",))
        elif Keys == "home":  # 如果按下Home键
            self.keyInfo.emit('t', (None,))  # 发送切换窗口信号
        elif Keys == "f8":  # 如果按下F8键
            # 用 keyboard.is_pressed 实时查修饰键状态，避免事件顺序不一致
            if keyboard.is_pressed('ctrl') and keyboard.is_pressed('alt'):
                # Ctrl+Alt+F8: 批量生成模板
                self.keyInfo.emit('l', ("📸 Ctrl+Alt+F8 触发批量生成模板…",))
                self.batch_template_requested.emit()
            else:
                # 普通 F8: 打开 ROI 配置
                self.roi_config_requested.emit()
        elif Keys == "f9":  # 调试总开关（与主界面「调试」按钮相同逻辑）
            try:
                import main as _main_mod
                from main import debug_hotkey_f9
                debug_hotkey_f9(self)
                level_name = "DEBUG" if _main_mod.DEBUG_MODE else "INFO"
                self.keyInfo.emit(
                    'l',
                    (f"📝 调试 (F9): {level_name} | 开镜时姿势可存 logs/posture_debug/",),
                )
            except Exception as e:
                self.keyInfo.emit('l', (f"⚠️ 切换调试总开关失败: {e}",))
        elif Keys in ("ctrl_l", "ctrl_r"):  # 如果按下Ctrl键
            self.ctrl_pressed = True  # 标记Ctrl键按下
            if Keys == "ctrl_l":  # 只有左Ctrl触发蹲下（原逻辑）
                self.PC.Current_posture = "c"  # 设置姿态为趴下
                self.keyInfo.emit('p', (self.PC.Current_posture,))  # 发送姿态信息信号
        elif Keys in ("alt_l", "alt_r"):  # 如果按下Alt键
            self.alt_pressed = True  # 标记Alt键按下

    def _test_posture_recognition(self):
        """
        测试姿势识别（在独立线程中执行）
        """
        import time
        time.sleep(0.5)  # 稍微延迟，让用户准备好
        
        try:
            posture = self.PC.capture_and_recognize_posture(
                debug=bool(getattr(self.PC, "debug_input_trace", False))
            )
            
            if posture:
                # ✅ 直接赋值，不用 Change_posture（图像识别是绝对结果）
                self.PC.Current_posture = posture
                mode_name = {"None": "站立", "c": "蹲下", "z": "趴下"}.get(posture, "未知")
                self.keyInfo.emit('l', (f"✅ 姿势识别测试成功: {mode_name}",))
                self.keyInfo.emit('p', (posture,))
            else:
                self.keyInfo.emit('l', ("⚠️ 姿势识别测试失败，请查看 logs/posture_debug/ 目录中的截图",))
        except Exception as e:
            self.keyInfo.emit('l', (f"❌ 姿势识别测试异常: {e}",))

    def on_key_release(self, event):  # 键盘释放事件处理方法
        try:
            Keys = event.name  # 获取按键名称
        except:
            return
        
        if not Keys:
            return
        if Keys == "ctrl_l":  # 如果释放左Ctrl键
            self.ctrl_pressed = False
            self.PC.Current_posture = "None"  # 设置姿态为站立
            self.keyInfo.emit('p', (self.PC.Current_posture,))  # 发送姿态信息信号
        elif Keys == "ctrl_r":
            self.ctrl_pressed = False
        elif Keys == "alt_l" or Keys == "alt_r":  # 如果释放Alt键
            self.alt_pressed = False  # 标记Alt键释放

    def run(self):  # 线程运行方法
        self.rerun()  # 调用rerun方法

    def rerun(self):  # 重新启动键盘监听
        try:
            # 清除之前的钩子
            if self.KeyHook:
                keyboard.unhook_all()
            
            # 注册按键事件 - 只观察，不拦截
            self.KeyHook = keyboard.hook(lambda e: self.on_key_pressed(e) if e.event_type == 'down' else self.on_key_release(e))
            self.keyInfo.emit('l', ("键盘监听已启动...",))  # 发送启动信号
        except Exception as e:
            error_msg = f"键盘监听启动失败: {e}"
            self.keyInfo.emit('l', (error_msg,))

    def stop_listener(self):  # 停止键盘监听
        if self.KeyHook:  # 如果键盘钩子存在
            try:
                keyboard.unhook_all()  # 取消所有钩子
                self.KeyHook = None  # 清除键盘钩子
            except:
                pass
            self.keyInfo.emit('l', ("键盘监听已停止.....",))  # 发送停止信号
