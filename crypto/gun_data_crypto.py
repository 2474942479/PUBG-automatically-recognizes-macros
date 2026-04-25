"""
GunData JSON 加密/解密模块

加密方案: AES-256-CBC + PKCS7 padding
- 加密工具: encrypt_all_gun_data()  — 构建时调用，将明文 JSON 加密为 .enc 文件
- 解密接口: load_gun_data()         — 运行时调用，在内存中解密，不落盘

使用方式:
    # 构建时加密 (在 build.py 中自动调用)
    python -m crypto.gun_data_crypto encrypt

    # 也可以手动解密验证
    python -m crypto.gun_data_crypto decrypt akm
"""

import os
import sys
import json
import hashlib
import struct
from pathlib import Path

# AES 实现选择: 优先用 pycryptodome，退回到纯 Python 实现
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    HAS_PYCRYPTODOME = True
except ImportError:
    HAS_PYCRYPTODOME = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 密钥配置 — 编译后嵌入到 .pyd / native code 中
# 使用混淆编码增加逆向工程难度
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# SALT 的 ASCII 码表示 (PUBG_MACRO_TOOL_2024)
_SALT_ENCODED = [80, 85, 66, 71, 95, 77, 65, 67, 82, 79, 95, 84, 79, 79, 76, 95, 50, 48, 50, 52]

# PASSPHRASE 分段存储,运行时拼接 (xK9#mP2$vL5@nQ8&wR3*jT7!)
_PASSPHRASE_PARTS = [
    [120, 75, 57, 35],   # xK9#
    [109, 80, 50, 36],   # mP2$
    [118, 76, 53, 64],   # vL5@
    [110, 81, 56, 38],   # nQ8&
    [119, 82, 51, 42],   # wR3*
    [106, 84, 55, 33],   # jT7!
]

def _get_salt():
    """动态获取 SALT,避免明文存储。"""
    return bytes(_SALT_ENCODED)

def _get_passphrase():
    """动态拼接 PASSPHRASE,避免明文存储。"""
    return b"".join(bytes(part) for part in _PASSPHRASE_PARTS)

def _get_hardware_id():
    """
    获取硬件指纹 (基于 CPU ID + 主板序列号)
    用于生成机器绑定的密钥
    :return: 硬件ID字符串
    """
    try:
        import subprocess
        import platform
        
        if platform.system() == "Windows":
            # 获取 CPU ID
            cpu_cmd = 'wmic cpu get processorid'
            cpu_result = subprocess.check_output(cpu_cmd, shell=True).decode('utf-8', errors='ignore')
            cpu_id = cpu_result.split('\n')[1].strip() if '\n' in cpu_result else ''
            
            # 获取主板序列号
            board_cmd = 'wmic baseboard get serialnumber'
            board_result = subprocess.check_output(board_cmd, shell=True).decode('utf-8', errors='ignore')
            board_id = board_result.split('\n')[1].strip() if '\n' in board_result else ''
            
            # 组合硬件ID
            hw_id = f"{cpu_id}_{board_id}"
            return hw_id.encode('utf-8')
        else:
            # Linux/Mac  fallback
            return b"cross_platform_fallback"
    except Exception:
        # 如果获取失败,使用默认值
        return b"hardware_id_error"

def _derive_key(use_hardware_binding=False):
    """
    从密码短语派生 AES-256 密钥。
    :param use_hardware_binding: 是否使用硬件绑定 (实验性功能)
    :return: 32字节的 AES 密钥
    """
    base_passphrase = _get_passphrase()
    base_salt = _get_salt()
    
    if use_hardware_binding:
        # 将硬件ID加入到盐值中,实现机器绑定
        hw_id = _get_hardware_id()
        combined_salt = base_salt + hw_id
        return hashlib.pbkdf2_hmac("sha256", base_passphrase, combined_salt, iterations=100000)
    else:
        # 标准模式:不使用硬件绑定
        return hashlib.pbkdf2_hmac("sha256", base_passphrase, base_salt, iterations=100000)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 纯 Python AES-CBC 后备实现 (无需第三方库)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if not HAS_PYCRYPTODOME:
    import secrets

    _SBOX = [
        0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
        0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
        0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
        0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
        0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
        0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
        0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
        0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
        0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
        0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
        0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
        0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
        0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
        0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
        0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
        0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
    ]

    _INV_SBOX = [0] * 256
    for _i, _v in enumerate(_SBOX):
        _INV_SBOX[_v] = _i

    _RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]

    def _xtime(a):
        return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff

    def _mix_single(a):
        t = a[0] ^ a[1] ^ a[2] ^ a[3]
        u = a[0]
        r = [0]*4
        r[0] = a[0] ^ _xtime(a[0] ^ a[1]) ^ t
        r[1] = a[1] ^ _xtime(a[1] ^ a[2]) ^ t
        r[2] = a[2] ^ _xtime(a[2] ^ a[3]) ^ t
        r[3] = a[3] ^ _xtime(a[3] ^ u) ^ t
        return r

    def _key_expansion(key):
        nk = len(key) // 4
        nr = nk + 6
        w = []
        for i in range(nk):
            w.append(list(key[4*i:4*i+4]))
        for i in range(nk, 4*(nr+1)):
            tmp = list(w[i-1])
            if i % nk == 0:
                tmp = [_SBOX[tmp[1]] ^ _RCON[i//nk - 1], _SBOX[tmp[2]], _SBOX[tmp[3]], _SBOX[tmp[0]]]
            elif nk > 6 and i % nk == 4:
                tmp = [_SBOX[b] for b in tmp]
            w.append([w[i-nk][j] ^ tmp[j] for j in range(4)])
        return w

    def _aes_encrypt_block(block, round_keys, nr):
        state = [list(block[i*4:(i+1)*4]) for i in range(4)]
        state = [[state[j][i] for j in range(4)] for i in range(4)]
        for i in range(4):
            for j in range(4):
                state[i][j] ^= round_keys[i][j]
        for rnd in range(1, nr):
            for i in range(4):
                for j in range(4):
                    state[i][j] = _SBOX[state[i][j]]
            for i in range(1,4):
                state[i] = state[i][i:] + state[i][:i]
            for j in range(4):
                col = [state[i][j] for i in range(4)]
                mixed = _mix_single(col)
                for i in range(4):
                    state[i][j] = mixed[i]
            for i in range(4):
                for j in range(4):
                    state[i][j] ^= round_keys[rnd*4+i][j]
        for i in range(4):
            for j in range(4):
                state[i][j] = _SBOX[state[i][j]]
        for i in range(1,4):
            state[i] = state[i][i:] + state[i][:i]
        for i in range(4):
            for j in range(4):
                state[i][j] ^= round_keys[nr*4+i][j]
        result = bytearray(16)
        for i in range(4):
            for j in range(4):
                result[j*4+i] = state[i][j]
        return bytes(result)

    def _aes_decrypt_block(block, round_keys, nr):
        state = [list(block[i*4:(i+1)*4]) for i in range(4)]
        state = [[state[j][i] for j in range(4)] for i in range(4)]
        for i in range(4):
            for j in range(4):
                state[i][j] ^= round_keys[nr*4+i][j]
        for rnd in range(nr-1, 0, -1):
            for i in range(1,4):
                state[i] = state[i][4-i:] + state[i][:4-i]
            for i in range(4):
                for j in range(4):
                    state[i][j] = _INV_SBOX[state[i][j]]
            for i in range(4):
                for j in range(4):
                    state[i][j] ^= round_keys[rnd*4+i][j]
            for j in range(4):
                col = [state[i][j] for i in range(4)]
                a0,a1,a2,a3 = col
                u = _xtime(_xtime(a0^a2))
                v = _xtime(_xtime(a1^a3))
                col = [a0^u, a1^v, a2^u, a3^v]
                mixed = _mix_single(col)
                for i in range(4):
                    state[i][j] = mixed[i]
        for i in range(1,4):
            state[i] = state[i][4-i:] + state[i][:4-i]
        for i in range(4):
            for j in range(4):
                state[i][j] = _INV_SBOX[state[i][j]]
        for i in range(4):
            for j in range(4):
                state[i][j] ^= round_keys[i][j]
        result = bytearray(16)
        for i in range(4):
            for j in range(4):
                result[j*4+i] = state[i][j]
        return bytes(result)

    def _pkcs7_pad(data, block_size=16):
        padding_len = block_size - (len(data) % block_size)
        return data + bytes([padding_len] * padding_len)

    def _pkcs7_unpad(data):
        padding_len = data[-1]
        if padding_len < 1 or padding_len > 16:
            raise ValueError("Invalid padding")
        if data[-padding_len:] != bytes([padding_len] * padding_len):
            raise ValueError("Invalid padding")
        return data[:-padding_len]

    def _aes_cbc_encrypt(plaintext, key, iv):
        nr = len(key) // 4 + 6
        rk_raw = _key_expansion(key)
        rk = [[rk_raw[i*4+j][k] for k in range(4)] for j in range(4) for i in range(nr+1)]
        rk2 = []
        for i in range(nr+1):
            for j in range(4):
                rk2.append([rk_raw[i][j2] for j2 in range(4)] if i < len(rk_raw) else [0]*4)
        padded = _pkcs7_pad(plaintext)
        prev = bytearray(iv)
        result = b""
        for off in range(0, len(padded), 16):
            block = bytearray(padded[off:off+16])
            for i in range(16):
                block[i] ^= prev[i]
            enc = _aes_encrypt_block(bytes(block), rk_raw, nr)
            result += enc
            prev = bytearray(enc)
        return result

    def _aes_cbc_decrypt(ciphertext, key, iv):
        nr = len(key) // 4 + 6
        rk_raw = _key_expansion(key)
        prev = bytearray(iv)
        result = b""
        for off in range(0, len(ciphertext), 16):
            block = ciphertext[off:off+16]
            dec = _aes_decrypt_block(block, rk_raw, nr)
            plain_block = bytearray(dec)
            for i in range(16):
                plain_block[i] ^= prev[i]
            result += bytes(plain_block)
            prev = bytearray(block)
        return _pkcs7_unpad(result)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 统一加密/解密接口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def encrypt_bytes(data: bytes, use_hardware_binding=False) -> bytes:
    """
    加密数据，返回 IV(16字节) + 密文。
    :param data: 要加密的原始数据
    :param use_hardware_binding: 是否使用硬件绑定 (加密和解密必须一致)
    :return: IV + 密文
    """
    key = _derive_key(use_hardware_binding)

    if HAS_PYCRYPTODOME:
        cipher = AES.new(key, AES.MODE_CBC)
        ct = cipher.encrypt(pad(data, AES.block_size))
        return cipher.iv + ct
    else:
        iv = secrets.token_bytes(16)
        ct = _aes_cbc_encrypt(data, key, iv)
        return iv + ct


def decrypt_bytes(data: bytes, use_hardware_binding=False) -> bytes:
    """
    解密数据 (IV + 密文)。
    :param data: IV + 密文
    :param use_hardware_binding: 是否使用硬件绑定 (必须与加密时一致)
    :return: 解密后的原始数据
    """
    key = _derive_key(use_hardware_binding)
    iv = data[:16]
    ct = data[16:]

    if HAS_PYCRYPTODOME:
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        return unpad(cipher.decrypt(ct), AES.block_size)
    else:
        return _aes_cbc_decrypt(ct, key, iv)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GunData 加密/解密 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_base_dir():
    """获取项目根目录 (兼容 Nuitka 编译后的路径)。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def encrypt_gun_data_file(json_path: Path, output_path: Path = None, use_hardware_binding=False):
    """
    将单个 GunData JSON 加密为 .enc 文件。
    :param json_path: JSON 文件路径
    :param output_path: 输出路径 (默认同名 .enc)
    :param use_hardware_binding: 是否使用硬件绑定
    :return: 加密文件路径
    """
    raw = json_path.read_bytes()
    encrypted = encrypt_bytes(raw, use_hardware_binding)

    if output_path is None:
        output_path = json_path.with_suffix(".enc")
    output_path.write_bytes(encrypted)
    return output_path


def decrypt_gun_data_file(enc_path: Path, use_hardware_binding=False) -> dict:
    """
    解密 .enc 文件，返回字典 (不落盘)。
    :param enc_path: 加密文件路径
    :param use_hardware_binding: 是否使用硬件绑定 (必须与加密时一致)
    :return: 解密后的字典数据
    """
    raw = enc_path.read_bytes()
    decrypted = decrypt_bytes(raw, use_hardware_binding)
    return json.loads(decrypted.decode("utf-8"))


def encrypt_all_gun_data(gun_data_dir: Path = None, use_hardware_binding=False):
    """
    加密 GunData 目录下所有 JSON 文件。
    :param gun_data_dir: GunData 目录路径
    :param use_hardware_binding: 是否使用硬件绑定 (默认False,便于分发)
    """
    if gun_data_dir is None:
        gun_data_dir = _get_base_dir() / "_internal" / "GunData"

    if not gun_data_dir.exists():
        print(f"[CRYPTO] GunData 目录不存在: {gun_data_dir}")
        return

    json_files = list(gun_data_dir.glob("*.json"))
    mode_str = "硬件绑定模式" if use_hardware_binding else "标准模式"
    print(f"[CRYPTO] 发现 {len(json_files)} 个 JSON 文件，开始加密 ({mode_str})...")

    for jf in json_files:
        enc_path = encrypt_gun_data_file(jf, use_hardware_binding=use_hardware_binding)
        print(f"  {jf.name} -> {enc_path.name}")

    print(f"[CRYPTO] 加密完成。可以删除原始 .json 文件用于发布。")


def load_gun_data(file_name: str, gun_data_dir: Path = None, use_hardware_binding=False) -> dict:
    """
    运行时加载弹道数据 — 优先读 .enc (加密)，降级读 .json (开发模式)。

    这是 core/process.py 中 read_gun_data() 应该调用的接口。
    
    :param file_name: 枪械名称 (不含扩展名)
    :param gun_data_dir: GunData 目录路径
    :param use_hardware_binding: 是否使用硬件绑定 (必须与加密时一致)
    :return: 枪械数据字典
    """
    if gun_data_dir is None:
        gun_data_dir = _get_base_dir() / "_internal" / "GunData"

    enc_path = gun_data_dir / f"{file_name}.enc"
    if enc_path.exists():
        return decrypt_gun_data_file(enc_path, use_hardware_binding)

    json_path = gun_data_dir / f"{file_name}.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI 入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m crypto.gun_data_crypto encrypt          # 加密所有 GunData JSON")
        print("  python -m crypto.gun_data_crypto decrypt <枪名>    # 解密并打印指定枪械数据")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "encrypt":
        encrypt_all_gun_data()

    elif cmd == "decrypt":
        if len(sys.argv) < 3:
            print("请指定枪械名称, 如: python -m crypto.gun_data_crypto decrypt akm")
            sys.exit(1)
        name = sys.argv[2]
        data = load_gun_data(name)
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"未找到 {name} 的数据文件")
