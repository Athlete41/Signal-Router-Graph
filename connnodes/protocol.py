"""
二进制协议编解码

协议格式：
  [帧头2B: 0xAA55][采样间隔4B: uint32 LE(μs)][数据数2B: uint16 LE][数据N*4B: float32 LE][校验1B: XOR]

校验：XOR 从帧头到最后一个数据字节
"""
import struct
from PyQt5.QtCore import QByteArray


FRAME_HEADER = b'\xAA\x55'
HEADER_SIZE = 2
INTERVAL_SIZE = 4
COUNT_SIZE = 2
FLOAT_SIZE = 4
CHECKSUM_SIZE = 1

# 最小包长度：帧头+采样间隔+数据数+0个数据+校验 = 2+4+2+0+1 = 9
MIN_PACKET_SIZE = HEADER_SIZE + INTERVAL_SIZE + COUNT_SIZE + CHECKSUM_SIZE


def _xor_checksum(data: bytes) -> int:
    """计算 bytes 的 XOR 校验和"""
    ck = 0
    for b in data:
        ck ^= b
    return ck


def encode_packet(sampling_interval_us: int, data: list[float]) -> QByteArray:
    """将浮点数数组编码为协议包"""
    ba = QByteArray()
    ba.append(FRAME_HEADER)
    ba.append(struct.pack('<I', sampling_interval_us))
    ba.append(struct.pack('<H', len(data)))
    for v in data:
        ba.append(struct.pack('<f', v))

    # XOR 校验（基于所有已写入字节）
    raw = bytes(ba)
    ck = _xor_checksum(raw)
    ba.append(struct.pack('B', ck))
    return ba


def decode_packet(ba: QByteArray) -> dict | None:
    """解析协议包，返回 {sampling_interval_us, data(floats)} 或 None"""
    if ba.size() < MIN_PACKET_SIZE:
        return None

    raw = bytes(ba)  # QByteArray → Python bytes

    if raw[0] != 0xAA or raw[1] != 0x55:
        return None

    # 校验（排除最后一个校验字节）
    if _xor_checksum(raw[:-1]) != raw[-1]:
        return None

    data_count = struct.unpack_from('<H', raw, HEADER_SIZE + INTERVAL_SIZE)[0]
    expected_size = MIN_PACKET_SIZE + data_count * FLOAT_SIZE
    if len(raw) != expected_size:
        return None

    sampling_interval_us = struct.unpack_from('<I', raw, HEADER_SIZE)[0]
    data_start = HEADER_SIZE + INTERVAL_SIZE + COUNT_SIZE
    floats = []
    for i in range(data_count):
        offset = data_start + i * FLOAT_SIZE
        floats.append(struct.unpack_from('<f', raw, offset)[0])

    return {
        "sampling_interval_us": sampling_interval_us,
        "data": floats,
    }
