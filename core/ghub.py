import logging
import platform
from ctypes import CDLL, c_char_p
from core.paths import res_path

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"


class ghub_device:
    info = None
    
    def __init__(self):
        if not IS_WINDOWS:
            self.gm = None
            self.gm_ok = 0
            self.info = f'当前系统 {platform.system()} 不支持 GHUB 驱动 (仅Windows可用)'
            logger.warning(self.info)
            return
        try:
            dll_path = res_path('_internal', 'ghub_device_GHUB.dll')
            self.gm = CDLL(dll_path)
            self.gm_ok = self.gm.device_open()
            self.gm.key_down.argtypes = [c_char_p]
            self.gm.key_up.argtypes = [c_char_p]
            if not self.gm_ok:
                self.info = '未安装ghub或者lgs驱动!!!'
            else:
                self.info = '驱动初始化成功!'
        except FileNotFoundError:
            self.info = '重要键鼠文件缺失'
            self.gm_ok = 0
    
    def _mouse_event(self, fun, *args):
        if self.gm_ok:
            try:
                if hasattr(self.gm, fun):
                    return getattr(self.gm, fun)(*args)
                else:
                    return None
            except (NameError, OSError):
                self.info = '键鼠调用严重错误!!!'
    
    def mouse_R(self, x, y):
        return self._mouse_event('moveR', int(x), int(y))
    
    def mouse_To(self, x, y):
        return self._mouse_event('moveTo', int(x), int(y))
    
    def mouse_down(self, key=1):
        return self._mouse_event('mouse_down', int(key))
    
    def mouse_up(self, key=1):
        return self._mouse_event('mouse_up', int(key))
    
    def scroll(self, num=1):
        return self._mouse_event('scroll', int(num))
    
    def key_down(self, key):
        return self._mouse_event('key_down', key.encode('utf-8'))

    def key_up(self, key):
        return self._mouse_event('key_up', key.encode('utf-8'))

    def device_close(self):
        return self._mouse_event('device_close')
