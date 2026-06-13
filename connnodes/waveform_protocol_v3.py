"""
波形采样协议 V3 — 编解码实现

协议格式见 connnodes/waveform_protocol_v3.md
编码: encode_packet(sampling_interval_us, data, gap_count=0, channel_id=0) → QByteArray
解码: decode_packet(qba) → dict | None
"""

import struct
import binascii
import numpy as np
from typing import Optional
from PyQt5.QtCore import QByteArray


# ── 编码 ──────────────────────────────────────────────────────────────────

def encode_packet(
    sampling_interval_us: int,
    data,
    gap_count: int = 0,
    channel_id: int = 0,
) -> QByteArray:
    """将波形数据编码为 V3 格式的 QByteArray

    Args:
        sampling_interval_us: 采样间隔（微秒）
        data: 浮点数序列，list 或 numpy 1-D array
        gap_count: 前 N 个点为危险丢弃点
        channel_id: 通道 ID (0-255)

    Returns:
        编码后的 QByteArray
    """
    data_count = len(data)
    payload_offset = 13

    ba = QByteArray()
    ba.append(b'\xaa\x55')                         # 帧头 [2B]
    ba.append(struct.pack('B', channel_id))         # 通道 ID [1B]
    ba.append(struct.pack('<I', sampling_interval_us))  # 采样间隔 [4B]
    ba.append(struct.pack('<H', data_count))        # 数据数 [2B]
    ba.append(struct.pack('<I', gap_count))         # gap 数 [4B]

    # 数据载荷 — 逐个 float32 LE
    for v in data:
        ba.append(struct.pack('<f', v))

    # CRC-16/CCITT — 从帧头到最后一个数据字节
    crc = binascii.crc_hqx(ba, 0xffff)
    ba.append(struct.pack('<H', crc))

    return ba


# ── 解码 ──────────────────────────────────────────────────────────────────

def _check_crc(ba: QByteArray, crc_offset: int) -> bool:
    """验证 CRC-16"""
    data_part = ba.left(crc_offset)
    expected_crc = struct.unpack('<H', ba.mid(crc_offset, 2))[0]
    actual_crc = binascii.crc_hqx(data_part, 0xffff)
    return actual_crc == expected_crc


def decode_packet(ba: QByteArray) -> Optional[dict]:
    """解码 V3 协议包

    Returns:
        dict with keys:
            channel_id: int
            sampling_interval_us: int
            data_count: int
            gap_count: int
            data: np.ndarray  # float64
        None — 解码失败
    """
    raw = bytes(ba)

    # 1. 长度检查（最小 15 字节）
    if len(raw) < 15:
        return None

    # 2. 帧头检查
    if raw[0] != 0xAA or raw[1] != 0x55:
        return None

    # 3. 解析元数据
    channel_id = raw[2]                           # uint8
    sampling_interval_us = struct.unpack('<I', raw[3:7])[0]
    data_count = struct.unpack('<H', raw[7:9])[0]
    gap_count = struct.unpack('<I', raw[9:13])[0]

    # 4. 长度验证
    crc_offset = 13 + 4 * data_count
    if crc_offset + 2 > len(raw):
        return None

    # 5. CRC 校验
    if not _check_crc(ba, crc_offset):
        return None

    # 6. 解码数据（numpy float64）
    data = np.frombuffer(raw[13:13 + 4 * data_count], dtype=np.float32).astype(np.float64)

    return {
        "channel_id": channel_id,
        "sampling_interval_us": sampling_interval_us,
        "data_count": data_count,
        "gap_count": gap_count,
        "data": data,
    }
