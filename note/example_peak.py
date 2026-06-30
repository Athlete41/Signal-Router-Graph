"""
波形降采样算法测试
"""
import numpy as np
import matplotlib

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt

_rng = np.random.RandomState(42)


def generate_signal(n_gap: int = 0, n_points: int = 20000) -> np.ndarray:
    t = np.linspace(0, n_points, n_points)
    signal = (
        np.sin(t * 0.0003) * 40 + 50
        + np.sin(t * 0.002) * 10
        + (np.sin(t * 0.005) > 0.5).astype(float) * 15
    )
    gap = np.full(n_gap, np.nan)
    noise = _rng.randn(n_points) * 3
    return np.concatenate([gap, signal + noise])


def downsample(data: np.ndarray, k: int) -> np.ndarray:
    """每 k 个点取一个"""
    n = len(data)
    M = n // k
    return data[:M * k:k]


def downsample_peak(data: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """峰值降采样，返回 (原始点, 峰值点) 各 M 个"""
    n = len(data)
    M = n // k

    data_max = data[:M * k:k]
    data_min = np.zeros(M, dtype=data.dtype)
    for i in range(M):
        bucket = data[i * k:(i + 1) * k]
        min_val = np.min(bucket)
        max_val = np.max(bucket)
        data_min[i] = min_val
        data_max[i] = max_val

    return data_max, data_min

# 生成数据
data = generate_signal(n_gap=0, n_points=1000)
k = 5

# 峰值降采样
data_max, data_min = downsample_peak(data, k)
M = len(data_max)

# 降采样（普通）
down = downsample(data, k)
x_down = np.arange(len(down)) * k

# 绘图：原始
plt.figure(figsize=(14, 5))
plt.plot(data, color="green", alpha=0.4, linewidth=0.5, label="原始")

# 绘图：降采样（普通）
plt.plot(x_down, down, color="blue", alpha=0.8, linewidth=1, marker=".", markersize=2, label="普通降采样")

# 绘图：峰值降采样
for i in range(M - 1):
    x0 = i * k
    x1 = (i + 1) * k
    if i == 0:
        plt.plot([x0, x0], [data_min[i], data_max[i]], color="red", linewidth=1, label="峰值降采样")
    else:
        plt.plot([x0, x0], [data_min[i], data_max[i]], color="red", linewidth=1)


plt.xlabel("样本序号")
plt.ylabel("幅度")
plt.legend()
plt.title("峰值降采样")
plt.tight_layout()
plt.show()
