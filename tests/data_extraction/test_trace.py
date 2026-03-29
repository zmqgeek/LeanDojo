from pathlib import Path
from types import SimpleNamespace
import os
import time
from lean_dojo import *
from lean_dojo.data_extraction.cache import cache
from lean_dojo.data_extraction.traced_data import (
    TracedFile,
    _is_complete_xml_output,
    _save_xml_to_disk,
)
from lean_dojo.utils import working_directory
from lean_dojo.data_extraction.lean import RepoType
from git import Repo


def test_github_trace(lean4_example_url):
    # github
    github_repo = LeanGitRepo(lean4_example_url, "main")
    assert github_repo.repo_type == RepoType.GITHUB
    trace_repo = trace(github_repo)
    path = cache.get(github_repo.get_cache_dirname() / github_repo.name)
    assert path is not None


def test_local_trace(lean4_example_url):
    # local
    with working_directory() as tmp_dir:
        # git repo placed in `tmp_dir / repo_name`
        Repo.clone_from(lean4_example_url, "lean4-example")
        local_dir = str((tmp_dir / "lean4-example"))
        local_url = str((tmp_dir / "lean4-example").absolute())
        local_repo = LeanGitRepo(local_dir, "main")
        assert local_repo.url == local_url
        assert local_repo.repo_type == RepoType.LOCAL
        trace_repo = trace(local_repo)
        path = cache.get(local_repo.get_cache_dirname() / local_repo.name)
        assert path is not None


def test_trace(traced_repo):
    traced_repo.check_sanity()


def test_get_traced_repo_path(mathlib4_repo):
    path = get_traced_repo_path(mathlib4_repo)
    assert isinstance(path, Path) and path.exists()


def test_save_xml_to_disk_is_atomic(tmp_path):
    tf = SimpleNamespace(
        root_dir=tmp_path,
        path=Path("Foo.lean"),
        repo=object(),
        to_xml=lambda: "<TracedFile/>",
    )

    _save_xml_to_disk(tf)

    final_path = tmp_path / ".lake/build/ir/Foo.trace.xml"
    assert final_path.exists()
    assert final_path.read_text() == "<TracedFile/>"
    assert not (tmp_path / ".lake/build/ir/Foo.trace.xml.tmp").exists()


def test_is_complete_xml_output_checks_freshness_and_parseability(tmp_path, monkeypatch):
    root_dir = tmp_path
    json_path = root_dir / ".lake/build/ir/Foo.ast.json"
    xml_path = root_dir / ".lake/build/ir/Foo.trace.xml"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text("{}")

    assert _is_complete_xml_output(root_dir, json_path, object()) is False

    xml_path.write_text("<TracedFile/>")
    now = time.time()
    os.utime(xml_path, (now - 10, now - 10))
    os.utime(json_path, (now, now))
    assert _is_complete_xml_output(root_dir, json_path, object()) is False

    os.utime(xml_path, (now + 10, now + 10))
    monkeypatch.setattr(TracedFile, "from_xml", classmethod(lambda cls, *args, **kwargs: object()))
    assert _is_complete_xml_output(root_dir, json_path, object()) is True

    monkeypatch.setattr(
        TracedFile,
        "from_xml",
        classmethod(
            lambda cls, *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad xml"))
        ),
    )
    assert _is_complete_xml_output(root_dir, json_path, object()) is False
