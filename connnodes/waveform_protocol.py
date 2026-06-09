"""
二进制协议编解码

协议格式：
  [帧头2B: 0xAA55]
  [采样间隔4B: uint32 LE(μs)]
  [数据数2B: uint16 LE]          ← 总浮点数数量（含 gap 点 + 有效数据）
  [起始丢弃数2B: uint16 LE]      ← 数据载荷前 N 个点为不可信丢弃点（危险区域）
  [数据N*4B: float32 LE]         ← 前 gap_count 个为 NaN 魔法数字（标记危险区域）
  [校验1B: XOR]                  ← XOR 从帧头到最后一个数据字节

校验：XOR 从帧头到最后一个数据字节
"""
import struct
from PyQt5.QtCore import QByteArray


FRAME_HEADER = b'\xAA\x55'
HEADER_SIZE = 2
INTERVAL_SIZE = 4
COUNT_SIZE = 2          # data_count (uint16)
GAP_SIZE = 2            # gap_count (uint16)  ← v2 新增
FLOAT_SIZE = 4
CHECKSUM_SIZE = 1

# v1 格式：帧头+采样间隔+数据数+数据+校验 = 2+4+2+4N+1 = 9+4N
# v2 格式：...gap数(2) + ... = 2+4+2+2+4N+1 = 11+4N
V1_MIN_PACKET_SIZE = (HEADER_SIZE + INTERVAL_SIZE + COUNT_SIZE
                      + CHECKSUM_SIZE)                      # 9
V2_MIN_PACKET_SIZE = (HEADER_SIZE + INTERVAL_SIZE + COUNT_SIZE
                      + GAP_SIZE + CHECKSUM_SIZE)           # 11

MAGIC_GAP = float('nan')   # 危险区域魔法数字 (NaN)


def _xor_checksum(data: bytes) -> int:
    """计算 bytes 的 XOR 校验和"""
    ck = 0
    for b in data:
        ck ^= b
    return ck


def encode_packet(sampling_interval_us: int, data: list[float],
                  gap_count: int = 0) -> QByteArray:
    """将浮点数数组编码为协议包（v2 格式）

    Args:
        sampling_interval_us: 采样间隔（微秒）
        data: 波形数据点
        gap_count: 起始丢弃点数（危险区域），前 gap_count 个点会被编码为 NaN
    """
    # 前 gap_count 个点用 NaN 魔法数字填充
    if gap_count > 0:
        payload = [MAGIC_GAP] * gap_count + data
    else:
        payload = data

    ba = QByteArray()
    ba.append(FRAME_HEADER)
    ba.append(struct.pack('<I', sampling_interval_us))
    ba.append(struct.pack('<H', len(payload)))
    ba.append(struct.pack('<H', gap_count))
    for v in payload:
        ba.append(struct.pack('<f', v))

    # XOR 校验（基于所有已写入字节）
    raw = bytes(ba)
    ck = _xor_checksum(raw)
    ba.append(struct.pack('B', ck))
    return ba


def decode_packet(ba: QByteArray) -> dict | None:
    """解析协议包，返回 {sampling_interval_us, data, gap_count} 或 None

    兼容 v1（无 gap_count 字段）和 v2（含 gap_count 字段）两种格式。
    """
    if ba.size() < V1_MIN_PACKET_SIZE:
        return None

    raw = bytes(ba)  # QByteArray → Python bytes

    if raw[0] != 0xAA or raw[1] != 0x55:
        return None

    # 校验（排除最后一个校验字节）
    if _xor_checksum(raw[:-1]) != raw[-1]:
        return None

    data_count = struct.unpack_from('<H', raw,
                                    HEADER_SIZE + INTERVAL_SIZE)[0]
    expected_v1 = V1_MIN_PACKET_SIZE + data_count * FLOAT_SIZE  # 9+4N
    expected_v2 = V2_MIN_PACKET_SIZE + data_count * FLOAT_SIZE  # 11+4N

    if len(raw) == expected_v2:
        # v2 格式：含 gap_count 字段
        gap_count = struct.unpack_from('<H', raw,
                                       HEADER_SIZE + INTERVAL_SIZE + COUNT_SIZE)[0]
        data_start = HEADER_SIZE + INTERVAL_SIZE + COUNT_SIZE + GAP_SIZE  # 10
    elif len(raw) == expected_v1:
        # v1 格式：无 gap_count 字段（向后兼容）
        gap_count = 0
        data_start = HEADER_SIZE + INTERVAL_SIZE + COUNT_SIZE  # 8
    else:
        return None

    sampling_interval_us = struct.unpack_from('<I', raw, HEADER_SIZE)[0]
    floats = []
    for i in range(data_count):
        offset = data_start + i * FLOAT_SIZE
        floats.append(struct.unpack_from('<f', raw, offset)[0])

    return {
        "sampling_interval_us": sampling_interval_us,
        "data": floats,       # 包含开头 gap_count 个 NaN 魔法数字
        "gap_count": gap_count,
    }
