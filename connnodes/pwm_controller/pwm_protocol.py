"""
PWM 控制器 — 与 MCU 通信的二进制协议编解码

协议帧格式：
  [帧头 2B: 0xAA 0x55]
  [命令 1B: uint8]
  [载荷长度 2B: uint16 LE]
  [载荷 N bytes]
  [校验 1B: XOR]

校验范围：帧头到载荷最后一个字节（不含校验字节），XOR 算法。

命令码：
  PC→MCU:  0x10 FETCH_PWM_INFO  /  0x11 SET_PWM_FREQ  /  0x12 SET_PWM_DUTY  /  0x13 SET_PWM_ENABLE
  MCU→PC:  0x20 PWM_INFO_REPORT /  0x21 PWM_SET_ACK   /  0xFF PWM_ERROR
"""

import struct
from dataclasses import dataclass
from PyQt5.QtCore import QByteArray


# ── 帧常量 ──────────────────────────────────────────────────

SOF = b'\xAA\x55'
SOF_SIZE = 2
CMD_SIZE = 1
PAYLOAD_LEN_SIZE = 2
HEADER_SIZE = SOF_SIZE + CMD_SIZE + PAYLOAD_LEN_SIZE   # 5
CHECKSUM_SIZE = 1
MIN_FRAME_SIZE = HEADER_SIZE + CHECKSUM_SIZE            # 6

# ── 命令码 ──────────────────────────────────────────────────

# PC → MCU
CMD_FETCH_PWM_INFO = 0x10
CMD_SET_PWM_FREQ   = 0x11
CMD_SET_PWM_DUTY   = 0x12
CMD_SET_PWM_ENABLE = 0x13

# MCU → PC
CMD_PWM_INFO_REPORT = 0x20
CMD_PWM_SET_ACK     = 0x21
CMD_PWM_ERROR       = 0xFF

# ── 错误码 ──────────────────────────────────────────────────

ERR_INVALID_CMD     = 0x01
ERR_INVALID_CHANNEL = 0x02
ERR_OUT_OF_RANGE    = 0x03
ERR_NOT_ADJUSTABLE  = 0x04
ERR_CHECKSUM        = 0x05
ERR_CHANNEL_NOT_OCCUPIED = 0x06

_ERROR_MESSAGES = {
    ERR_INVALID_CMD:     "无效命令",
    ERR_INVALID_CHANNEL: "无效通道索引",
    ERR_OUT_OF_RANGE:    "数值超出范围",
    ERR_NOT_ADJUSTABLE:  "通道参数不可调",
    ERR_CHECKSUM:        "校验错误",
    ERR_CHANNEL_NOT_OCCUPIED: "通道未被占用",
}

# ── 标志位 ──────────────────────────────────────────────────

FLAG_FREQ_ADJUSTABLE = 0x01   # bit0: 频率可调
FLAG_DUTY_ADJUSTABLE = 0x02   # bit1: 占空比可调
FLAG_OCCUPIED        = 0x04   # bit2: 通道被占用
FLAG_ENABLED         = 0x08   # bit3: 当前启用

# ── 通道数据结构 ───────────────────────────────────────────

@dataclass
class PwmChannelInfo:
    """单路 PWM 通道的完整状态"""
    index: int                    # 0-3 (对应通道 1-4)
    name: str = ""                # "1"~"4"
    occupied: bool = False        # MCU 是否报告此通道被占用
    freq_adjustable: bool = False
    duty_adjustable: bool = False
    enabled: bool = False
    freq_min: int = 0             # Hz
    freq_max: int = 0
    freq_default: int = 0
    freq_current: int = 0
    duty_min: int = 0             # 0-10000 (0.00%-100.00%)
    duty_max: int = 10000
    duty_default: int = 0
    duty_current: int = 0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "occupied": self.occupied,
            "freq_adjustable": self.freq_adjustable,
            "duty_adjustable": self.duty_adjustable,
            "enabled": self.enabled,
            "freq_min": self.freq_min,
            "freq_max": self.freq_max,
            "freq_default": self.freq_default,
            "freq_current": self.freq_current,
            "duty_min": self.duty_min,
            "duty_max": self.duty_max,
            "duty_default": self.duty_default,
            "duty_current": self.duty_current,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PwmChannelInfo":
        return cls(
            index=d.get("index", 0),
            name=d.get("name", ""),
            occupied=d.get("occupied", False),
            freq_adjustable=d.get("freq_adjustable", False),
            duty_adjustable=d.get("duty_adjustable", False),
            enabled=d.get("enabled", False),
            freq_min=d.get("freq_min", 0),
            freq_max=d.get("freq_max", 0),
            freq_default=d.get("freq_default", 0),
            freq_current=d.get("freq_current", 0),
            duty_min=d.get("duty_min", 0),
            duty_max=d.get("duty_max", 10000),
            duty_default=d.get("duty_default", 0),
            duty_current=d.get("duty_current", 0),
        )


# ── 校验 ─────────────────────────────────────────────────────

def xor_checksum(data: bytes) -> int:
    """计算 bytes 的 XOR 校验和"""
    ck = 0
    for b in data:
        ck ^= b
    return ck


# ── 底层帧打包/解包 ─────────────────────────────────────────

def _pack_frame(cmd: int, payload: bytes = b"") -> QByteArray:
    """将命令和载荷打包为完整帧"""
    ba = QByteArray()
    ba.append(SOF)                                 # 帧头
    ba.append(struct.pack('B', cmd))               # 命令
    ba.append(struct.pack('<H', len(payload)))     # 载荷长度
    if payload:
        ba.append(payload)                         # 载荷
    raw = bytes(ba)
    ck = xor_checksum(raw)
    ba.append(struct.pack('B', ck))                # 校验
    return ba


def decode_frame(ba: QByteArray) -> tuple | None:
    """解析协议帧，返回 (cmd: int, payload: bytes) 或 None（校验失败/格式错误）"""
    if ba.size() < MIN_FRAME_SIZE:
        return None

    raw = bytes(ba)

    if raw[0] != 0xAA or raw[1] != 0x55:
        return None

    payload_len = struct.unpack_from('<H', raw, SOF_SIZE + CMD_SIZE)[0]
    expected_size = HEADER_SIZE + payload_len + CHECKSUM_SIZE
    if len(raw) != expected_size:
        return None

    # 校验（排除校验字节）
    if xor_checksum(raw[:-1]) != raw[-1]:
        return None

    cmd = raw[SOF_SIZE]
    payload = raw[HEADER_SIZE:HEADER_SIZE + payload_len]
    return (cmd, payload)


# ── PC → MCU 命令打包 ───────────────────────────────────────

def build_fetch_info() -> QByteArray:
    """构造 FETCH_PWM_INFO 命令（无载荷）"""
    return _pack_frame(CMD_FETCH_PWM_INFO)


def build_set_freq(channel_idx: int, freq_hz: int) -> QByteArray:
    """构造 SET_PWM_FREQ 命令

    Args:
        channel_idx: 通道索引 (0-3)
        freq_hz: 频率 (Hz, uint32)
    """
    payload = struct.pack('<H', channel_idx) + struct.pack('<I', freq_hz)
    return _pack_frame(CMD_SET_PWM_FREQ, payload)


def build_set_duty(channel_idx: int, duty: int) -> QByteArray:
    """构造 SET_PWM_DUTY 命令

    Args:
        channel_idx: 通道索引 (0-3)
        duty: 占空比 0-10000 (0.00%-100.00%, uint16)
    """
    payload = struct.pack('<H', channel_idx) + struct.pack('<H', duty)
    return _pack_frame(CMD_SET_PWM_DUTY, payload)


def build_set_enable(channel_idx: int, enable: bool) -> QByteArray:
    """构造 SET_PWM_ENABLE 命令

    Args:
        channel_idx: 通道索引 (0-3)
        enable: True=启用, False=禁用
    """
    payload = struct.pack('<H', channel_idx) + struct.pack('B', 1 if enable else 0)
    return _pack_frame(CMD_SET_PWM_ENABLE, payload)


# ── MCU → PC 响应解析 ──────────────────────────────────────

def decode_info_report(payload: bytes) -> list | None:
    """解析 CMD_PWM_INFO_REPORT 载荷，返回 PwmChannelInfo 列表（4条）或 None"""
    if len(payload) < 1:
        return None

    channel_count = payload[0]
    offset = 1
    channels = []

    for i in range(channel_count):
        if offset >= len(payload):
            return None

        name_len = payload[offset]
        offset += 1
        if offset + name_len > len(payload):
            return None

        name = payload[offset:offset + name_len].decode('utf-8', errors='replace')
        offset += name_len

        # flags (1B) + freq(4*4=16B) + duty(4*2=8B) = 25B
        if offset + 25 > len(payload):
            return None

        flags = payload[offset]
        offset += 1
        occupied = bool(flags & FLAG_OCCUPIED)
        freq_adjustable = bool(flags & FLAG_FREQ_ADJUSTABLE)
        duty_adjustable = bool(flags & FLAG_DUTY_ADJUSTABLE)
        enabled = bool(flags & FLAG_ENABLED)

        freq_min, freq_max, freq_default, freq_current = struct.unpack_from(
            '<IIII', payload, offset)
        offset += 16

        duty_min, duty_max, duty_default, duty_current = struct.unpack_from(
            '<HHHH', payload, offset)
        offset += 8

        channels.append(PwmChannelInfo(
            index=i,
            name=name,
            occupied=occupied,
            freq_adjustable=freq_adjustable,
            duty_adjustable=duty_adjustable,
            enabled=enabled,
            freq_min=freq_min,
            freq_max=freq_max,
            freq_default=freq_default,
            freq_current=freq_current,
            duty_min=duty_min,
            duty_max=duty_max,
            duty_default=duty_default,
            duty_current=duty_current,
        ))

    return channels


def decode_set_ack(payload: bytes) -> dict | None:
    """解析 CMD_PWM_SET_ACK 载荷，返回 {ch_idx, cmd, value} 或 None

    value 类型取决于 cmd:
      - SET_PWM_FREQ: uint32 (4B)
      - SET_PWM_DUTY: uint16 (2B)
      - SET_PWM_ENABLE: uint8 (1B)
    """
    if len(payload) < 3:  # ch_idx(2) + cmd(1)
        return None

    ch_idx = struct.unpack_from('<H', payload, 0)[0]
    cmd = payload[2]

    value = None
    if cmd == CMD_SET_PWM_FREQ:
        if len(payload) >= 7:
            value = struct.unpack_from('<I', payload, 3)[0]
    elif cmd == CMD_SET_PWM_DUTY:
        if len(payload) >= 5:
            value = struct.unpack_from('<H', payload, 3)[0]
    elif cmd == CMD_SET_PWM_ENABLE:
        if len(payload) >= 4:
            value = bool(payload[3])
    else:
        return None

    return {"ch_idx": ch_idx, "cmd": cmd, "value": value}


def decode_error(payload: bytes) -> tuple | None:
    """解析 CMD_PWM_ERROR 载荷，返回 (error_code, channel_idx) 或 None"""
    if len(payload) < 3:
        return None
    error_code = payload[0]
    ch_idx = struct.unpack_from('<H', payload, 1)[0]
    return (error_code, ch_idx)


def get_error_message(error_code: int) -> str:
    """获取错误码的描述文本"""
    return _ERROR_MESSAGES.get(error_code, f"未知错误 (0x{error_code:02X})")
