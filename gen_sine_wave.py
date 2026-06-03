"""
生成正弦波测试数据（V3 协议格式）

用法:
    python gen_sine_wave.py
    python gen_sine_wave.py --sampling 100 --signal 10 --points 50 --channel 0

输出: .hex.txt 文件，可用 Hex发送器 加载
"""

import argparse
import math
import struct
import binascii
from PyQt5.QtCore import QByteArray

# ── 手动实现编码，避免导入 connnodes 时的循环/依赖问题 ──────────────

def encode_v3_packet(
    sampling_interval_us: int,
    data: list,
    gap_count: int = 0,
    channel_id: int = 0,
) -> QByteArray:
    """编码 V3 协议包（独立实现，不依赖 connnodes）"""
    ba = QByteArray()
    ba.append(b'\xaa\x55')
    ba.append(struct.pack('B', channel_id))
    ba.append(struct.pack('<I', sampling_interval_us))
    ba.append(struct.pack('<H', len(data)))
    ba.append(struct.pack('<I', gap_count))
    for v in data:
        ba.append(struct.pack('<f', v))
    crc = binascii.crc_hqx(ba, 0xffff)
    ba.append(struct.pack('<H', crc))
    return ba


def generate_sine(sampling_hz: int, signal_hz: float, points: int,
                  channel_id: int = 0):
    """生成正弦波 V3 协议包，返回 QByteArray"""
    sampling_interval_us = int(1_000_000 / sampling_hz)
    data = [math.sin(2 * math.pi * signal_hz * i / sampling_hz)
            for i in range(points)]
    qba = encode_v3_packet(sampling_interval_us, data, channel_id=channel_id)
    return qba, data


def save_hex_txt(qba: QByteArray, filepath: str):
    """保存为 Hex 文本文件（空格分隔的大写 hex，单行）"""
    hex_str = " ".join(f"{b:02X}" for b in bytes(qba))
    with open(filepath, 'w') as f:
        f.write(hex_str + "\n")


def save_bin(qba: QByteArray, filepath: str):
    """保存为原始二进制文件"""
    with open(filepath, 'wb') as f:
        f.write(bytes(qba))


# ── 命令行入口 ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="生成正弦波 V3 协议测试数据")
    parser.add_argument("--sampling", type=int, default=10,
                        help="采样频率 (Hz)，默认 10")
    parser.add_argument("--signal", type=float, default=1.0,
                        help="信号频率 (Hz)，默认 1")
    parser.add_argument("--points", type=int, default=10,
                        help="数据点数，默认 10")
    parser.add_argument("--channel", type=int, default=0,
                        help="通道 ID，默认 0")
    parser.add_argument("--output", type=str, default=None,
                        help="输出文件路径（不含扩展名）")
    parser.add_argument("--bin", action="store_true",
                        help="同时输出 .bin 二进制文件")
    args = parser.parse_args()

    # 生成
    qba, data = generate_sine(args.sampling, args.signal,
                              args.points, args.channel)

    # 输出路径
    base = args.output or f"test_sine_{args.sampling}hz_{args.signal}hz_{args.points}pts"

    # 保存 hex 文本
    txt_path = f"{base}.hex.txt"
    save_hex_txt(qba, txt_path)

    # 可选保存 bin
    if args.bin:
        bin_path = f"{base}.bin"
        save_bin(qba, bin_path)

    # 打印信息
    print(f"参数: 采样={args.sampling}Hz, 信号={args.signal}Hz, 点数={args.points}, 通道={args.channel}")
    print(f"采样间隔: {int(1_000_000 / args.sampling)} μs")
    print(f"包大小: {len(bytes(qba))} 字节")
    print(f"数据: {[round(v, 4) for v in data]}")
    print()
    print(f"Hex 文本: {txt_path}")
    hex_line = " ".join(f"{b:02X}" for b in bytes(qba))
    print(f"内容: {hex_line}")
    if args.bin:
        print(f"二进制: {bin_path}")


if __name__ == "__main__":
    main()
