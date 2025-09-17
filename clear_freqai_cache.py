import os
import shutil
from pathlib import Path

# 清理FreqAI可能的缓存位置
cache_dirs = [
    'user_data/models',
    'user_data/freqaimodels/__pycache__',
    'user_data/strategies/__pycache__',
    '.freqai_cache',
    'freqai_cache'
]

print("清理FreqAI缓存...")

for cache_dir in cache_dirs:
    cache_path = Path(cache_dir)
    if cache_path.exists():
        if cache_path.is_dir():
            print(f"删除目录: {cache_path}")
            shutil.rmtree(cache_path)
        else:
            print(f"删除文件: {cache_path}")
            cache_path.unlink()
    else:
        print(f"目录不存在: {cache_path}")

# 重新创建models目录
models_dir = Path('user_data/models')
models_dir.mkdir(parents=True, exist_ok=True)
print(f"重新创建目录: {models_dir}")

# 查找并删除任何.pkl或.joblib文件
for pattern in ['**/*.pkl', '**/*.joblib', '**/*.model']:
    for file_path in Path('.').glob(pattern):
        if 'user_data' in str(file_path):
            print(f"删除模型文件: {file_path}")
            file_path.unlink()

print("缓存清理完成！")