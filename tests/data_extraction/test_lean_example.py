import os
# 设置 GitHub token 以避免请求频率限制
# os.environ['GITHUB_ACCESS_TOKEN'] = ''
# Lean 编译阶段的并行数。这个值会传给 `lake env lean --threads ...`。
os.environ['NUM_PROCS'] = '16'
# 将 Python/Ray 侧的并发压到 1，避免在解析大型 `*.ast.json` 时额外放大内存。
os.environ['NUM_WORKERS'] = '1'
# 设置临时目录以便观察 `trace` 阶段生成的文件
os.environ['TMP_DIR'] = 'temp_dir'
# 取消远程缓存下载，在本地进行构建
os.environ['DISABLE_REMOTE_CACHE'] = 'true'

os.makedirs("temp_dir", exist_ok=True)

from lean_dojo import LeanGitRepo, trace

repo = LeanGitRepo("https://github.com/leanprover-community/mathlib4", "29dcec074de168ac2bf835a77ef68bbe069194c5")
# repo = LeanGitRepo("https://github.com/zmqgeek/lean4-example/", "d361b5a0c03d9ca5abb93b1e015353d8ddf953f3")
trace(repo, dst_dir="traced_lean4-mathlib4")
