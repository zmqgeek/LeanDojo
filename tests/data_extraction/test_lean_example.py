import os
import shutil
from pathlib import Path

# 设置 GitHub token 以避免请求频率限制
os.environ["GITHUB_ACCESS_TOKEN"] = ""
# Lean 编译阶段的并行数。这个值会传给 `lake env lean --threads ...`。
os.environ["NUM_PROCS"] = "8"
# 文件级提取并发上限。建议从 1/2/4 开始试，避免大仓库提取时内存峰值过高。
os.environ["NUM_FILE_WORKERS"] = "8"
# 将 Python/Ray 侧的并发压到 1，避免在解析大型 `*.ast.json` 时额外放大内存。
os.environ["NUM_WORKERS"] = "1"
# 固定临时目录，方便观察和复用本地半成品。
os.environ["TMP_DIR"] = "temp_dir"
# 取消远程缓存下载，在本地进行构建。
os.environ["DISABLE_REMOTE_CACHE"] = "true"

from git import Repo
from lean_dojo import LeanGitRepo
from lean_dojo.data_extraction.cache import cache
from lean_dojo.data_extraction.trace import (
    LEAN4_DATA_EXTRACTOR_PATH,
    LEAN4_REPL_PATH,
    check_files,
    get_lean_version,
    is_new_version,
)
from lean_dojo.data_extraction.traced_data import TracedRepo, save_xml_from_traced_files
from lean_dojo.utils import execute, working_directory


REPO_URL = "https://github.com/leanprover-community/mathlib4"
COMMIT = "29dcec074de168ac2bf835a77ef68bbe069194c5"
BUILD_DEPS = True

TEMP_ROOT = Path("temp_dir")
RESUME_ROOT = TEMP_ROOT / "resume_workdir"
DST_ROOT = Path("traced_lean4-mathlib4")


def ensure_local_repo(repo: LeanGitRepo, local_root: Path) -> Path:
    local_root.mkdir(parents=True, exist_ok=True)
    repo_dir = local_root / repo.name

    if repo_dir.exists():
        git_repo = Repo(repo_dir)
        git_repo.git.checkout(repo.commit)
        git_repo.submodule_update(init=True, recursive=True)
        return repo_dir

    with working_directory(local_root):
        repo.clone_and_checkout()
    return repo_dir


def ensure_lean4_stdlib(packages_path: Path) -> None:
    lean_prefix = Path(execute("lean --print-prefix", capture_output=True)[0].strip())
    target = packages_path / "lean4"
    if target.exists():
        return
    shutil.copytree(lean_prefix, target)


def ensure_repl_library(repo_dir: Path) -> None:
    repl_target = repo_dir / LEAN4_REPL_PATH.name
    if not repl_target.exists():
        shutil.copyfile(LEAN4_REPL_PATH, repl_target)

    lakefile_lean = repo_dir / "lakefile.lean"
    if lakefile_lean.exists():
        content = lakefile_lean.read_text()
        if "lean_lib Lean4Repl" not in content:
            with lakefile_lean.open("a") as oup:
                oup.write("\nlean_lib Lean4Repl {\n\n}\n")
        return

    lakefile_toml = repo_dir / "lakefile.toml"
    if lakefile_toml.exists():
        content = lakefile_toml.read_text()
        if 'name = "Lean4Repl"' not in content:
            with lakefile_toml.open("a") as oup:
                oup.write('\n[[lean_lib]]\nname = "Lean4Repl"\n')


def resume_trace_in_local_repo(repo: LeanGitRepo, repo_dir: Path, build_deps: bool) -> Path:
    with working_directory(repo_dir):
        if not build_deps:
            try:
                execute("lake exe cache get")
            except Exception:
                pass

        execute("lake build", capture_output=False)

        if is_new_version(get_lean_version()):
            packages_path = Path(".lake/packages")
        else:
            packages_path = Path("lake-packages")

        ensure_lean4_stdlib(packages_path)
        shutil.copyfile(LEAN4_DATA_EXTRACTOR_PATH, LEAN4_DATA_EXTRACTOR_PATH.name)

        cmd = "lake env lean --threads {} --run ExtractData.lean".format(
            os.environ["NUM_PROCS"]
        )
        if not build_deps:
            cmd += " noDeps"
        execute(cmd, capture_output=False)
        check_files(packages_path, not build_deps)

        extractor_copy = repo_dir / LEAN4_DATA_EXTRACTOR_PATH.name
        if extractor_copy.exists():
            extractor_copy.unlink()

        ensure_repl_library(repo_dir)
        try:
            execute("lake build Lean4Repl", capture_output=False)
        except Exception:
            pass

    save_xml_from_traced_files(repo_dir, build_deps)
    return repo_dir


def materialize_cache_if_needed(repo: LeanGitRepo, traced_dir: Path) -> Path:
    rel_cache_dir = repo.get_cache_dirname() / repo.name
    cached_path = cache.get(rel_cache_dir)
    if cached_path is not None:
        return cached_path
    return cache.store(traced_dir, rel_cache_dir)


def export_traced_repo(src_dir: Path, dst_root: Path) -> None:
    dst_root.mkdir(parents=True, exist_ok=True)
    dst_dir = dst_root / src_dir.name
    if dst_dir.exists():
        return
    shutil.copytree(src_dir, dst_dir)


def trace_with_local_resume(
    repo: LeanGitRepo,
    resume_root: Path,
    dst_root: Path,
    build_deps: bool = True,
) -> TracedRepo:
    rel_cache_dir = repo.get_cache_dirname() / repo.name
    cached_path = cache.get(rel_cache_dir)
    local_repo_dir = resume_root / repo.name

    if local_repo_dir.exists():
        print(f"[RESUME] continue from local workdir: {local_repo_dir}")
        traced_dir = resume_trace_in_local_repo(repo, local_repo_dir, build_deps)
        cached_path = materialize_cache_if_needed(repo, traced_dir)
    elif cached_path is not None:
        print(f"[RESUME] use complete cache: {cached_path}")
    else:
        print(f"[RESUME] start new local workdir: {local_repo_dir}")
        local_repo_dir = ensure_local_repo(repo, resume_root)
        traced_dir = resume_trace_in_local_repo(repo, local_repo_dir, build_deps)
        cached_path = materialize_cache_if_needed(repo, traced_dir)

    export_traced_repo(cached_path, dst_root)
    traced_repo = TracedRepo.load_from_disk(cached_path, build_deps)
    traced_repo.check_sanity()
    return traced_repo


def main() -> None:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    RESUME_ROOT.mkdir(parents=True, exist_ok=True)
    repo = LeanGitRepo(REPO_URL, COMMIT)
    trace_with_local_resume(repo, RESUME_ROOT, DST_ROOT, BUILD_DEPS)


if __name__ == "__main__":
    main()
