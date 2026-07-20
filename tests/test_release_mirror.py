"""Tests for the closure-list mirror builder (tools/build_release_mirror.py)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_release_mirror import ClosureError, build_mirror  # noqa: E402


def make_tree(root: Path):
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "a.py").write_text("a")
    (root / "src" / "pkg" / "sub").mkdir()
    (root / "src" / "pkg" / "sub" / "b.py").write_text("b")
    (root / "top.md").write_text("top")
    (root / "secret").mkdir()
    (root / "secret" / "keys.txt").write_text("nope")


def write_closure(path: Path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_copies_globs_preserving_layout(tmp_path):
    repo = tmp_path / "repo"
    make_tree(repo)
    closure = tmp_path / "closure.txt"
    write_closure(closure, ["# comment", "", "src/pkg/**", "top.md"])
    out = tmp_path / "out"
    n = build_mirror(repo, closure, out)
    assert (out / "src" / "pkg" / "a.py").read_text() == "a"
    assert (out / "src" / "pkg" / "sub" / "b.py").read_text() == "b"
    assert (out / "top.md").exists()
    assert not (out / "secret").exists()
    assert n == 3


def test_wipes_stale_output(tmp_path):
    repo = tmp_path / "repo"
    make_tree(repo)
    closure = tmp_path / "closure.txt"
    write_closure(closure, ["top.md"])
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("old")
    build_mirror(repo, closure, out)
    assert not (out / "stale.txt").exists()
    assert (out / "top.md").exists()


def test_rename_maps_source_to_public_name(tmp_path):
    repo = tmp_path / "repo"
    make_tree(repo)
    (repo / "docs").mkdir()
    (repo / "docs" / "readme-public.md").write_text("public")
    closure = tmp_path / "closure.txt"
    write_closure(closure, ["docs/readme-public.md -> README.md", "top.md"])
    out = tmp_path / "out"
    n = build_mirror(repo, closure, out)
    assert (out / "README.md").read_text() == "public"
    assert not (out / "docs" / "readme-public.md").exists()
    assert n == 2


def test_rename_with_multiple_matches_raises(tmp_path):
    repo = tmp_path / "repo"
    make_tree(repo)
    closure = tmp_path / "closure.txt"
    write_closure(closure, ["src/pkg/** -> flat.py"])
    with pytest.raises(ClosureError) as e:
        build_mirror(repo, closure, tmp_path / "out")
    assert "exactly one" in str(e.value)


def test_zero_match_line_raises_naming_line(tmp_path):
    repo = tmp_path / "repo"
    make_tree(repo)
    closure = tmp_path / "closure.txt"
    write_closure(closure, ["top.md", "does/not/exist/**"])
    with pytest.raises(ClosureError) as e:
        build_mirror(repo, closure, tmp_path / "out")
    assert "does/not/exist/**" in str(e.value)
