import os
# 设置 GitHub token 以避免请求频率限制
# os.environ['GITHUB_ACCESS_TOKEN'] = ''
# 配置线程数以加快 `trace` 的运行速度
os.environ['NUM_PROCS'] = '64'
# 设置临时目录以便观察 `trace` 阶段生成的文件
os.environ['TMP_DIR'] = 'temp_dir'
# 取消远程缓存下载，在本地进行构建
os.environ['DISABLE_REMOTE_CACHE'] = 'true'

os.makedirs("temp_dir", exist_ok=True)

from lean_dojo import LeanGitRepo
from lean_dojo import trace

repo = LeanGitRepo("https://github.com/zmqgeek/lean4-example/", "d361b5a0c03d9ca5abb93b1e015353d8ddf953f3")
trace(repo, dst_dir="traced_lean4-example")
