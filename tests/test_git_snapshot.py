import os
import subprocess

from diffgraph.git_snapshot import (
    resolve_commit_range,
    resolve_staged,
    resolve_unstaged,
)


def git(repo, *args, input_bytes=None):
    completed = subprocess.run(
        ["git"] + list(args),
        cwd=str(repo),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout


def write(repo, path, content):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def oid(repo, revision):
    return git(repo, "rev-parse", revision).decode("ascii").strip()


def index_oid(repo, path):
    output = git(repo, "ls-files", "-s", "--", path)
    return output.split()[1].decode("ascii")


def commit_all(repo, message="baseline"):
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Snapshot Tests")
    git(repo, "config", "user.email", "snapshot@example.test")
    return repo


def test_staged_add_modify_delete_and_rename_have_exact_identities(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "modify.txt", b"old modify\n")
    write(repo, "delete.txt", b"old delete\n")
    write(repo, "rename-old.txt", b"rename content\n" * 20)
    commit_all(repo)

    old_modify = oid(repo, "HEAD:modify.txt")
    old_delete = oid(repo, "HEAD:delete.txt")
    old_rename = oid(repo, "HEAD:rename-old.txt")

    write(repo, "added.txt", b"new file\n")
    write(repo, "modify.txt", b"new modify\n")
    os.unlink(repo / "delete.txt")
    git(repo, "mv", "rename-old.txt", "rename-new.txt")
    git(repo, "add", "-A")

    result = resolve_staged(str(repo))
    entries = {entry.new_path or entry.old_path: entry for entry in result.entries}

    assert result.warnings == ()
    assert set(entries) == {"added.txt", "modify.txt", "delete.txt", "rename-new.txt"}

    added = entries["added.txt"]
    assert (added.status, added.old_path, added.new_path) == ("A", None, "added.txt")
    assert (added.old_mode, added.old_oid) == (None, None)
    assert (added.new_mode, added.new_oid) == ("100644", index_oid(repo, "added.txt"))

    modified = entries["modify.txt"]
    assert (modified.status, modified.old_path, modified.new_path) == (
        "M",
        "modify.txt",
        "modify.txt",
    )
    assert modified.old_oid == old_modify
    assert modified.new_oid == index_oid(repo, "modify.txt")

    deleted = entries["delete.txt"]
    assert (deleted.status, deleted.old_path, deleted.new_path) == (
        "D",
        "delete.txt",
        None,
    )
    assert (deleted.old_oid, deleted.new_oid) == (old_delete, None)
    assert (deleted.old_mode, deleted.new_mode) == ("100644", None)

    renamed = entries["rename-new.txt"]
    assert (renamed.status, renamed.old_path, renamed.new_path) == (
        "R",
        "rename-old.txt",
        "rename-new.txt",
    )
    assert (renamed.old_oid, renamed.new_oid) == (old_rename, old_rename)
    assert (renamed.old_mode, renamed.new_mode) == ("100644", "100644")


def test_unstaged_modify_and_delete_have_exact_identities(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "modify.txt", b"old\n")
    write(repo, "delete.txt", b"delete me\n")
    commit_all(repo)
    old_modify = oid(repo, "HEAD:modify.txt")
    old_delete = oid(repo, "HEAD:delete.txt")

    write(repo, "modify.txt", b"new working tree bytes\n")
    os.unlink(repo / "delete.txt")

    result = resolve_unstaged(str(repo))
    entries = {entry.new_path or entry.old_path: entry for entry in result.entries}

    assert result.warnings == ()
    assert set(entries) == {"modify.txt", "delete.txt"}
    modified = entries["modify.txt"]
    assert modified.status == "M"
    assert modified.old_oid == old_modify
    assert modified.new_oid == git(
        repo, "hash-object", "--stdin", "--path=modify.txt", input_bytes=b"new working tree bytes\n"
    ).decode("ascii").strip()
    assert len(modified.new_oid) == 40

    deleted = entries["delete.txt"]
    assert deleted.status == "D"
    assert (deleted.old_oid, deleted.new_oid) == (old_delete, None)
    assert (deleted.old_mode, deleted.new_mode) == ("100644", None)


def test_unstaged_hash_matches_git_add_clean_filter_semantics(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, ".gitattributes", b"filtered.txt text eol=lf\n")
    write(repo, "filtered.txt", b"old\n")
    commit_all(repo)

    write(repo, "filtered.txt", b"line one\r\nline two\r\n")
    result = resolve_unstaged(str(repo), ["filtered.txt"])
    assert result.warnings == ()
    assert len(result.entries) == 1
    resolved_oid = result.entries[0].new_oid

    git(repo, "add", "--", "filtered.txt")
    assert resolved_oid == index_oid(repo, "filtered.txt")


def test_explicit_pathspec_scope_is_not_widened(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "inside/a.txt", b"old a\n")
    write(repo, "outside/b.txt", b"old b\n")
    commit_all(repo)

    write(repo, "inside/a.txt", b"staged a\n")
    write(repo, "outside/b.txt", b"staged b\n")
    git(repo, "add", "-A")
    write(repo, "inside/a.txt", b"unstaged a\n")
    write(repo, "outside/b.txt", b"unstaged b\n")

    staged = resolve_staged(str(repo), ["inside"])
    unstaged = resolve_unstaged(str(repo), ["inside"])
    no_match = resolve_staged(str(repo), ["does-not-exist"])

    assert [entry.new_path for entry in staged.entries] == ["inside/a.txt"]
    assert [entry.new_path for entry in unstaged.entries] == ["inside/a.txt"]
    assert no_match.entries == ()
    assert no_match.warnings == ()


def test_nul_parsing_preserves_tabs_and_newlines_in_paths(tmp_path):
    repo = make_repo(tmp_path)
    old_name = "old\tname\npart.txt"
    new_name = "new\nname\tpart.txt"
    write(repo, old_name, b"unusual path\n" * 10)
    commit_all(repo)

    git(repo, "mv", old_name, new_name)
    result = resolve_staged(str(repo))

    assert result.warnings == ()
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.status == "R"
    assert entry.old_path == old_name
    assert entry.new_path == new_name
    assert entry.old_oid == entry.new_oid == oid(repo, "HEAD:" + old_name)


def test_repeated_resolution_is_deterministic(tmp_path):
    repo = make_repo(tmp_path)
    for name in ("z.txt", "a.txt", "middle.txt"):
        write(repo, name, ("old " + name + "\n").encode("ascii"))
    commit_all(repo)
    for name in ("z.txt", "a.txt", "middle.txt"):
        write(repo, name, ("new " + name + "\n").encode("ascii"))

    first = resolve_unstaged(str(repo))
    second = resolve_unstaged(str(repo))

    assert first == second
    assert [entry.new_path for entry in first.entries] == ["a.txt", "middle.txt", "z.txt"]


def test_git_failures_are_warnings_not_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    result = resolve_staged(str(tmp_path))

    assert result.entries == ()
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "not_a_git_repository"


def test_unstaged_intent_to_add_and_rename_have_exact_identities(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "rename-old.py", b"def moved():\n    return 1\n" * 20)
    commit_all(repo)
    old_oid = oid(repo, "HEAD:rename-old.py")

    os.rename(repo / "rename-old.py", repo / "rename-new.py")
    write(repo, "added.py", b"def added():\n    return 1\n")
    # Intent-to-add lets Git represent working-tree additions without putting
    # their content in the index; the resolver must still derive exact IDs.
    git(repo, "add", "-N", "--", "rename-new.py", "added.py")

    result = resolve_unstaged(str(repo))
    entries = {entry.new_path or entry.old_path: entry for entry in result.entries}
    assert result.warnings == ()
    assert set(entries) == {"rename-new.py", "added.py"}

    renamed = entries["rename-new.py"]
    assert (renamed.status, renamed.old_path, renamed.new_path) == (
        "R",
        "rename-old.py",
        "rename-new.py",
    )
    assert renamed.old_oid == old_oid
    assert renamed.new_oid == git(
        repo,
        "hash-object",
        "--stdin",
        "--path=rename-new.py",
        input_bytes=(repo / "rename-new.py").read_bytes(),
    ).decode("ascii").strip()

    added = entries["added.py"]
    assert (added.status, added.old_path, added.new_path) == ("A", None, "added.py")
    assert added.old_oid is None
    assert added.new_oid == git(
        repo,
        "hash-object",
        "--stdin",
        "--path=added.py",
        input_bytes=(repo / "added.py").read_bytes(),
    ).decode("ascii").strip()


def test_unstaged_includes_non_ignored_untracked_files_with_exact_identities(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, ".gitignore", b"ignored.py\n")
    write(repo, "tracked.py", b"def tracked():\n    return 1\n")
    commit_all(repo)

    write(repo, "new.py", b"def added():\n    return 1\n")
    write(repo, "ignored.py", b"def ignored():\n    return 1\n")
    write(repo, "bin/tool", b"#!/bin/sh\nexit 0\n")
    os.chmod(repo / "bin/tool", 0o700)
    os.symlink("new.py", repo / "new-link")

    result = resolve_unstaged(str(repo))
    entries = {entry.new_path: entry for entry in result.entries}

    assert result.warnings == ()
    assert set(entries) == {"new.py", "bin/tool", "new-link"}
    assert entries["new.py"].status == "A"
    assert entries["new.py"].old_oid is None
    assert entries["new.py"].new_mode == "100644"
    assert entries["new.py"].new_oid == git(
        repo,
        "hash-object",
        "--stdin",
        "--path=new.py",
        input_bytes=(repo / "new.py").read_bytes(),
    ).decode("ascii").strip()
    assert entries["bin/tool"].new_mode == "100755"
    assert entries["new-link"].new_mode == "120000"
    assert entries["new-link"].new_oid == git(
        repo, "hash-object", "--stdin", input_bytes=b"new.py"
    ).decode("ascii").strip()


def test_untracked_pathspec_scope_is_relative_and_not_widened(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "tracked.txt", b"baseline\n")
    commit_all(repo)
    write(repo, "inside/new.py", b"inside = True\n")
    write(repo, "outside.py", b"outside = True\n")

    scoped = resolve_unstaged(str(repo / "inside"), ["new.py"])
    no_match = resolve_unstaged(str(repo), ["missing"])

    assert scoped.warnings == ()
    assert [entry.new_path for entry in scoped.entries] == ["inside/new.py"]
    assert no_match.entries == ()
    assert no_match.warnings == ()


def test_pathspecs_are_relative_to_the_calling_subdirectory(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "src/app.py", b"def value():\n    return 1\n")
    write(repo, "app.py", b"def root_value():\n    return 1\n")
    commit_all(repo)
    write(repo, "src/app.py", b"def value():\n    return 2\n")
    write(repo, "app.py", b"def root_value():\n    return 2\n")

    result = resolve_unstaged(str(repo / "src"), ["app.py"])

    assert result.warnings == ()
    assert [entry.new_path for entry in result.entries] == ["src/app.py"]


def test_unstaged_symlink_hashes_raw_target_without_attributes(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, ".gitattributes", b"*.py filter=decorate\n")
    git(repo, "config", "filter.decorate.clean", "sed 's/^/filtered:/'")
    os.symlink("original.py", repo / "link.py")
    commit_all(repo)

    os.unlink(repo / "link.py")
    os.symlink("replacement.py", repo / "link.py")
    result = resolve_unstaged(str(repo), ["link.py"])

    assert result.warnings == ()
    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.new_mode == "120000"
    assert entry.new_oid == git(
        repo, "hash-object", "--stdin", input_bytes=b"replacement.py"
    ).decode("ascii").strip()


def test_two_dot_range_records_exact_endpoints_and_tree_identities(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "shared.txt", b"common\n")
    commit_all(repo, "common")
    git(repo, "branch", "base")

    write(repo, "head-only.txt", b"head\n")
    commit_all(repo, "head change")
    git(repo, "branch", "head")
    head_oid = oid(repo, "head")

    git(repo, "switch", "base")
    write(repo, "base-only.txt", b"base\n")
    commit_all(repo, "base change")
    base_oid = oid(repo, "base")

    result = resolve_commit_range(str(repo), "base", "head")
    entries = {entry.new_path or entry.old_path: entry for entry in result.entries}

    assert result.warnings == ()
    assert result.base_oid == result.comparison_base_oid == base_oid
    assert result.head_oid == head_oid
    assert result.three_dot is False
    assert set(entries) == {"base-only.txt", "head-only.txt"}
    assert entries["base-only.txt"].status == "D"
    assert entries["base-only.txt"].old_oid == oid(repo, "base:base-only.txt")
    assert entries["base-only.txt"].new_oid is None
    assert entries["head-only.txt"].status == "A"
    assert entries["head-only.txt"].old_oid is None
    assert entries["head-only.txt"].new_oid == oid(repo, "head:head-only.txt")


def test_three_dot_range_uses_merge_base_and_excludes_base_only_changes(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "shared.txt", b"common\n")
    commit_all(repo, "common")
    common_oid = oid(repo, "HEAD")
    git(repo, "branch", "base")

    write(repo, "head-only.txt", b"head\n")
    commit_all(repo, "head change")
    git(repo, "branch", "head")

    git(repo, "switch", "base")
    write(repo, "base-only.txt", b"base\n")
    commit_all(repo, "base change")

    result = resolve_commit_range(str(repo), "base", "head", three_dot=True)

    assert result.warnings == ()
    assert result.comparison_base_oid == common_oid
    assert result.base_oid == oid(repo, "base")
    assert result.head_oid == oid(repo, "head")
    assert result.three_dot is True
    assert [entry.new_path or entry.old_path for entry in result.entries] == [
        "head-only.txt"
    ]


def test_commit_range_pathspec_is_relative_to_calling_subdirectory(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "inside/a.txt", b"old a\n")
    write(repo, "outside/b.txt", b"old b\n")
    commit_all(repo)
    git(repo, "branch", "before")
    write(repo, "inside/a.txt", b"new a\n")
    write(repo, "outside/b.txt", b"new b\n")
    commit_all(repo, "both changed")

    result = resolve_commit_range(
        str(repo / "inside"), "before", "HEAD", pathspecs=["a.txt"]
    )

    assert result.warnings == ()
    assert [entry.new_path for entry in result.entries] == ["inside/a.txt"]


def test_invalid_commit_range_ref_is_a_warning_not_a_change(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "tracked.txt", b"content\n")
    commit_all(repo)

    result = resolve_commit_range(str(repo), "missing-ref", "HEAD")

    assert result.entries == ()
    assert result.base_oid is None
    assert result.head_oid == oid(repo, "HEAD")
    assert [warning.code for warning in result.warnings] == ["invalid_base_ref"]


def test_three_dot_without_merge_base_is_a_warning_not_a_change(tmp_path):
    repo = make_repo(tmp_path)
    write(repo, "first.txt", b"first\n")
    commit_all(repo)
    git(repo, "branch", "first")
    git(repo, "switch", "--orphan", "second")
    first_path = repo / "first.txt"
    if first_path.exists():
        first_path.unlink()
    write(repo, "second.txt", b"second\n")
    commit_all(repo, "unrelated root")

    result = resolve_commit_range(str(repo), "first", "second", three_dot=True)

    assert result.entries == ()
    assert result.comparison_base_oid is None
    assert [warning.code for warning in result.warnings] == ["merge_base_failed"]
