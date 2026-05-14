import os
from os.path import dirname, basename, isfile, join, isdir
import glob

current_dir = dirname(__file__)

# 1. 收集当前目录下的 .py 文件（排除 __init__.py）
py_files = glob.glob(join(current_dir, "*.py"))
module_names = [
    basename(f)[:-3] for f in py_files
    if isfile(f) and not f.endswith('__init__.py')
]

# 2. 收集第一层子目录（只取目录名，不递归）
#    可选：只收集那些包含 __init__.py 的子目录（确保是有效的子包）
sub_dirs = [
    d for d in os.listdir(current_dir)
    if isdir(join(current_dir, d)) 
    and not d.startswith('__')  # 排除 __pycache__ 等
    and isfile(join(current_dir, d, '__init__.py'))  # 必须是子包
]

# 3. 合并并去重（通常不会有重名冲突）
__all__ = module_names + sub_dirs