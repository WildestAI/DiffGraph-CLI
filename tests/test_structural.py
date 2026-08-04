import json
import os
import subprocess
from pathlib import Path

import jsonschema

from diffgraph.structural import analyze_local_diff

SCHEMA = json.loads((Path(__file__).parents[1] / "diffgraph/schema/diffgraph-v2.schema.json").read_text())


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE).stdout.decode().strip()


def write(repo, path, text):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "Structural Tests")
    git(root, "config", "user.email", "structural@example.test")
    return root


def commit(root):
    git(root, "add", "-A")
    git(root, "commit", "-m", "snapshot")


def stable(artifact):
    copy = json.loads(json.dumps(artifact))
    copy["generated_at"] = "<run>"
    copy["metadata"]["analysis_duration_ms"] = None
    copy["diff_ref"]["repo_root"] = "<repo>"
    return copy


def assert_valid(artifact):
    jsonschema.validate(artifact, SCHEMA)


def test_staged_add_modify_delete_rename_import_is_schema_valid_and_golden(tmp_path):
    root = repo(tmp_path)
    write(root, "modify.py", "def retained():\n    return 1\n\ndef removed():\n    return 0\n")
    write(root, "delete.py", "class Deleted:\n    pass\n")
    write(root, "rename.py", "def moved():\n    return 1\n")
    commit(root)

    write(root, "add.py", "import os\nfrom external.pkg import value\n\ndef added():\n    return value\n")
    write(root, "modify.py", "def retained():\n    return 2\n\ndef created():\n    return 3\n")
    os.unlink(root / "delete.py")
    git(root, "mv", "rename.py", "renamed.py")
    git(root, "add", "-A")

    artifact = analyze_local_diff(str(root), staged=True)
    assert_valid(artifact)
    assert [f["path"] for f in artifact["files"]] == ["add.py", "delete.py", "modify.py", "renamed.py"]
    assert {f["path"]: f["change_kind"] for f in artifact["files"]} == {
        "add.py": "added", "delete.py": "deleted", "modify.py": "modified", "renamed.py": "renamed"
    }
    changes = {s["id"]: s["change_kind"] for s in artifact["symbols"]}
    assert changes["sym::add.py::added"] == "added"
    assert changes["sym::delete.py::Deleted"] == "deleted"
    assert changes["sym::modify.py::retained"] == "modified"
    assert changes["sym::modify.py::removed"] == "deleted"
    assert changes["sym::modify.py::created"] == "added"
    assert changes["sym::renamed.py::moved"] == "unchanged"
    imports = [r for r in artifact["relationships"] if r["kind"] == "imports"]
    assert [r["label"] for r in imports] == [
        "unresolved/external module: external.pkg", "unresolved/external module: os"
    ]
    for file_entry in artifact["files"]:
        provenance = json.loads(file_entry["evidence"][0]["detail"])
        assert provenance["old_oid"] is None or len(provenance["old_oid"]) == 40
        assert provenance["new_oid"] is None or len(provenance["new_oid"]) == 40
        assert provenance["old_sha256"] is None or len(provenance["old_sha256"]) == 64
        assert provenance["new_sha256"] is None or len(provenance["new_sha256"]) == 64

    golden_path = Path(__file__).parent / "fixtures/python_topology.json"
    expected = json.loads(golden_path.read_text())
    actual = {
        "files": [{"path": f["path"], "old_path": f["old_path"], "change_kind": f["change_kind"]} for f in artifact["files"]],
        "symbols": [{"id": s["id"], "kind": s["kind"], "change_kind": s["change_kind"]} for s in artifact["symbols"]],
        "relationships": [{"id": r["id"], "kind": r["kind"]} for r in artifact["relationships"]],
    }
    if os.environ.get("UPDATE_GOLDEN"):
        golden_path.write_text(json.dumps(actual, indent=2) + "\n")
        expected = actual
    assert actual == expected


def test_unstaged_uses_index_to_worktree_exact_identity_and_is_stable(tmp_path):
    root = repo(tmp_path)
    write(root, "app.py", "def value():\n    return 1\n")
    commit(root)
    write(root, "app.py", "def value():\n    return 2\n")

    first = analyze_local_diff(str(root))
    second = analyze_local_diff(str(root))
    assert_valid(first)
    assert stable(first) == stable(second)
    provenance = json.loads(first["files"][0]["evidence"][0]["detail"])
    expected = git(root, "hash-object", "--path=app.py", "app.py")
    assert provenance["new_oid"] == expected
    assert first["symbols"][0]["change_kind"] == "modified"


def test_pathspec_scope_is_not_widened(tmp_path):
    root = repo(tmp_path)
    write(root, "inside/a.py", "def a():\n    return 1\n")
    write(root, "outside/b.py", "def b():\n    return 1\n")
    commit(root)
    write(root, "inside/a.py", "def a():\n    return 2\n")
    write(root, "outside/b.py", "def b():\n    return 2\n")
    artifact = analyze_local_diff(str(root), pathspecs=["inside"])
    assert [item["path"] for item in artifact["files"]] == ["inside/a.py"]


def test_unsupported_language_is_explicit_and_not_overclaimed(tmp_path):
    root = repo(tmp_path)
    write(root, "main.js", "export function value() { return 1; }\n")
    commit(root)
    write(root, "main.js", "export function value() { return 2; }\n")
    artifact = analyze_local_diff(str(root))
    assert_valid(artifact)
    assert artifact["symbols"] == []
    assert artifact["metadata"]["files_skipped"] == 1
    assert artifact["metadata"]["warnings"][0]["code"] == "UNSUPPORTED_LANGUAGE"
    assert "Python" in artifact["metadata"]["warnings"][0]["detail"]


def test_parse_failure_is_scoped_and_does_not_invent_symbol_changes(tmp_path):
    root = repo(tmp_path)
    write(root, "broken.py", "def valid():\n    return 1\n")
    commit(root)
    write(root, "broken.py", "def broken(:\n")
    artifact = analyze_local_diff(str(root))
    assert_valid(artifact)
    assert artifact["symbols"] == []
    assert artifact["relationships"] == []
    warning = artifact["metadata"]["warnings"][0]
    assert warning["code"] == "PARSE_FAILURE"
    assert warning["file"] == "broken.py"
    assert warning["detail"].startswith("post-change:")


def test_no_network_calls(monkeypatch, tmp_path):
    root = repo(tmp_path)
    write(root, "a.py", "def a():\n    pass\n")
    git(root, "add", "a.py")

    import socket
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    artifact = analyze_local_diff(str(root), staged=True)
    assert_valid(artifact)
    assert artifact["metadata"]["privacy_tier"] == "local"
    assert artifact["metadata"]["llm_calls"] == 0


def test_cli_structural_json_is_additive_and_stdout_is_valid_json(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from diffgraph.cli import main

    root = repo(tmp_path)
    write(root, "cli.py", "def old():\n    return 1\n")
    commit(root)
    write(root, "cli.py", "def old():\n    return 2\n")
    monkeypatch.chdir(root)

    result = CliRunner().invoke(main, ["--structural-json", "-", "diff"])
    assert result.exit_code == 0, result.output
    artifact = json.loads(result.output)
    assert_valid(artifact)
    assert artifact["symbols"][0]["change_kind"] == "modified"


def test_cli_structural_json_rejects_unimplemented_commit_ranges(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from diffgraph.cli import main

    root = repo(tmp_path)
    write(root, "cli.py", "def value():\n    return 1\n")
    commit(root)
    monkeypatch.chdir(root)
    result = CliRunner().invoke(main, ["--structural-json", "-", "diff", "HEAD~1..HEAD"])
    assert result.exit_code == 2
    assert "currently supports only unstaged" in result.output


def test_methods_nested_functions_and_deleted_imports_are_not_overclaimed(tmp_path):
    root = repo(tmp_path)
    write(
        root,
        "nested.py",
        "import removed_pkg\n\nclass Container:\n    def method(self):\n        return 1\n\ndef outer():\n    def inner():\n        return 1\n    return inner()\n",
    )
    commit(root)
    write(
        root,
        "nested.py",
        "class Container:\n    def method(self):\n        return 2\n\ndef outer():\n    def inner():\n        return 2\n    return inner()\n",
    )

    artifact = analyze_local_diff(str(root))
    assert_valid(artifact)
    symbols = {item["qualified_name"]: item for item in artifact["symbols"]}
    assert symbols["Container.method"]["kind"] == "method"
    assert symbols["outer.inner"]["kind"] == "function"
    assert symbols["import::removed_pkg"]["change_kind"] == "deleted"
    assert symbols["import::removed_pkg"]["location"] is None
    assert not any(
        item["kind"] == "imports"
        and item["target_id"] == symbols["import::removed_pkg"]["id"]
        for item in artifact["relationships"]
    )
