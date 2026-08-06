import json
import os
import subprocess
from pathlib import Path

import jsonschema
import pytest

from diffgraph.git_snapshot import GitSnapshotError, ResolutionWarning, SnapshotResolution
from diffgraph.structural import analyze_local_diff

SCHEMA = json.loads((Path(__file__).parents[1] / "diffgraph/schema/diffgraph-v2.schema.json").read_text())


def git(repo, *args, input_bytes=None):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_bytes,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode().strip()


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
    write(root, "renamed.py", "def moved():\n    return 2\n")
    git(root, "add", "-A")

    artifact = analyze_local_diff(str(root), staged=True)
    assert_valid(artifact)
    assert [f["path"] for f in artifact["files"]] == ["add.py", "delete.py", "modify.py", "renamed.py"]
    assert {f["path"]: f["change_kind"] for f in artifact["files"]} == {
        "add.py": "added", "delete.py": "deleted", "modify.py": "modified", "renamed.py": "renamed_modified"
    }
    changes = {s["id"]: s["change_kind"] for s in artifact["symbols"]}
    assert changes["sym::add.py::added"] == "added"
    assert changes["sym::delete.py::Deleted"] == "deleted"
    assert changes["sym::modify.py::retained"] == "modified"
    assert changes["sym::modify.py::removed"] == "deleted"
    assert changes["sym::modify.py::created"] == "added"
    assert changes["sym::renamed.py::moved"] == "modified"
    assert artifact["metadata"]["files_analyzed"] == 4
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
        pytest.skip("golden fixture regenerated")
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


def test_cli_terminal_format_renders_validated_local_artifact(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from diffgraph.cli import main

    root = repo(tmp_path)
    write(root, "cli.py", "def value():\n    return 1\n")
    commit(root)
    write(root, "cli.py", "def value():\n    return 2\n")
    monkeypatch.chdir(root)

    result = CliRunner().invoke(main, ["diff", "--format", "terminal"])

    assert result.exit_code == 0, result.output
    assert "wild diff" in result.output
    assert "cli.py" in result.output
    assert "value" in result.output
    assert "Analysis: structural" in result.output


def test_cli_default_format_keeps_legacy_html_path(monkeypatch):
    import sys
    from types import ModuleType

    from click.testing import CliRunner
    import diffgraph.cli as cli

    spinner_module = ModuleType("click_spinner")
    spinner_module.spinner = object()
    ai_module = ModuleType("diffgraph.ai_analysis")
    ai_module.CodeAnalysisAgent = object
    html_module = ModuleType("diffgraph.html_report")
    html_module.generate_html_report = lambda *args, **kwargs: None
    html_module.AnalysisResult = object
    monkeypatch.setitem(sys.modules, "click_spinner", spinner_module)
    monkeypatch.setitem(sys.modules, "diffgraph.ai_analysis", ai_module)
    monkeypatch.setitem(sys.modules, "diffgraph.html_report", html_module)
    monkeypatch.setattr(cli, "is_git_repo", lambda: True)
    monkeypatch.setattr(cli, "get_changed_files", lambda diff_args: [])

    result = CliRunner().invoke(cli.main, ["diff"])

    assert result.exit_code == 0, result.output
    assert "No changes to analyze" in result.output


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


def test_cli_structural_json_requires_separator_before_pathspecs(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from diffgraph.cli import main

    root = repo(tmp_path)
    write(root, "app.py", "def value():\n    return 1\n")
    commit(root)
    write(root, "app.py", "def value():\n    return 2\n")
    monkeypatch.chdir(root)

    result = CliRunner().invoke(
        main, ["--structural-json", "-", "diff", "app.py"]
    )

    assert result.exit_code == 2
    assert "put pathspecs after '--'" in result.output


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


def test_duplicate_symbol_occurrences_are_preserved(tmp_path):
    root = repo(tmp_path)
    write(
        root,
        "properties.py",
        "class Item:\n"
        "    @property\n"
        "    def value(self):\n"
        "        return 1\n\n"
        "    @value.setter\n"
        "    def value(self, new):\n"
        "        self._value = new\n",
    )
    commit(root)
    write(
        root,
        "properties.py",
        "class Item:\n"
        "    @property\n"
        "    def value(self):\n"
        "        return 1\n\n"
        "    @value.setter\n"
        "    def value(self, new):\n"
        "        self._value = new + 1\n",
    )

    artifact = analyze_local_diff(str(root))
    assert_valid(artifact)
    values = {
        item["qualified_name"]: item
        for item in artifact["symbols"]
        if item["name"] == "value"
    }
    assert set(values) == {"Item.value", "Item.value#1"}
    assert values["Item.value"]["change_kind"] == "unchanged"
    assert values["Item.value#1"]["change_kind"] == "modified"


def test_aliased_import_uses_name_field_and_reports_alias_edit_as_modified(tmp_path):
    root = repo(tmp_path)
    write(root, "imports.py", "import package \\\n    as old_alias\n")
    commit(root)
    write(root, "imports.py", "import package \\\n    as new_alias\n")

    artifact = analyze_local_diff(str(root))
    assert_valid(artifact)
    imported = next(item for item in artifact["symbols"] if item["kind"] == "import")
    assert imported["name"] == "package"
    assert imported["qualified_name"] == "import::package"
    assert imported["change_kind"] == "modified"


def test_worktree_symlink_uses_exact_link_bytes_without_partial_warning(tmp_path):
    root = repo(tmp_path)
    os.symlink("original.py", root / "link.py")
    commit(root)
    os.unlink(root / "link.py")
    os.symlink("replacement.py", root / "link.py")

    artifact = analyze_local_diff(str(root))
    assert_valid(artifact)
    assert artifact["metadata"]["files_analyzed"] == 1
    assert not any(
        warning["code"] == "PARTIAL_ANALYSIS"
        for warning in artifact["metadata"]["warnings"]
    )
    provenance = json.loads(artifact["files"][0]["evidence"][0]["detail"])
    assert provenance["new_oid"] == git(
        root, "hash-object", "--stdin", input_bytes=b"replacement.py"
    )


def test_snapshot_read_failure_is_partial_analysis(monkeypatch, tmp_path):
    root = repo(tmp_path)
    write(root, "app.py", "def value():\n    return 1\n")
    commit(root)
    write(root, "app.py", "def value():\n    return 2\n")

    def fail_read(*args, **kwargs):
        raise GitSnapshotError("simulated read race")

    monkeypatch.setattr("diffgraph.structural.read_worktree_blob", fail_read)
    artifact = analyze_local_diff(str(root))
    assert_valid(artifact)
    assert artifact["metadata"]["files_analyzed"] == 0
    assert artifact["metadata"]["files_skipped"] == 1
    warning = artifact["metadata"]["warnings"][0]
    assert warning["code"] == "PARTIAL_ANALYSIS"
    assert "simulated read race" in warning["detail"]


def test_resolution_warning_preserves_machine_readable_code(monkeypatch, tmp_path):
    root = repo(tmp_path)
    warning = ResolutionWarning("hash_object_failed", "simulated failure", "app.py")
    monkeypatch.setattr(
        "diffgraph.structural.resolve_unstaged",
        lambda repository, pathspecs: SnapshotResolution((), (warning,)),
    )

    artifact = analyze_local_diff(str(root))
    assert_valid(artifact)
    assert artifact["metadata"]["warnings"] == [
        {
            "code": "hash_object_failed",
            "file": "app.py",
            "detail": "hash_object_failed: simulated failure",
        }
    ]


def test_cli_structural_json_rejects_non_diff_command():
    from click.testing import CliRunner
    from diffgraph.cli import main

    result = CliRunner().invoke(main, ["--structural-json", "out.json", "status"])
    assert result.exit_code == 2
    assert "can only be used with 'diff'" in result.output


def test_cli_pathspec_is_relative_to_calling_subdirectory(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from diffgraph.cli import main

    root = repo(tmp_path)
    write(root, "src/app.py", "def value():\n    return 1\n")
    write(root, "app.py", "def root_value():\n    return 1\n")
    commit(root)
    write(root, "src/app.py", "def value():\n    return 2\n")
    write(root, "app.py", "def root_value():\n    return 2\n")
    monkeypatch.chdir(root / "src")

    result = CliRunner().invoke(
        main, ["--structural-json", "-", "diff", "--", "app.py"]
    )
    assert result.exit_code == 0, result.output
    artifact = json.loads(result.output)
    assert [item["path"] for item in artifact["files"]] == ["src/app.py"]


def test_cli_missing_structural_output_parent_is_a_click_error(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from diffgraph.cli import main

    root = repo(tmp_path)
    write(root, "app.py", "def value():\n    return 1\n")
    git(root, "add", "app.py")
    monkeypatch.chdir(root)
    output = root / "nested" / "artifact.json"

    result = CliRunner().invoke(
        main, ["--structural-json", str(output), "diff", "--staged"]
    )
    assert result.exit_code == 1
    assert "could not write" in result.output
    assert "Traceback" not in result.output
    assert not output.exists()


def test_schema_errors_become_click_errors(monkeypatch):
    import jsonschema as jsonschema_module
    from click import ClickException
    from diffgraph.cli import _validate_structural_artifact

    def invalid_schema(*args, **kwargs):
        raise jsonschema_module.SchemaError("invalid schema")

    monkeypatch.setattr(jsonschema_module, "validate", invalid_schema)
    with pytest.raises(ClickException, match="structural artifact validation failed"):
        _validate_structural_artifact({})


def test_missing_parser_dependency_is_a_run_level_cli_error(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from diffgraph.cli import main
    from diffgraph.structural import StructuralDependencyError

    root = repo(tmp_path)
    write(root, "app.py", "def value():\n    return 1\n")
    git(root, "add", "app.py")
    monkeypatch.chdir(root)

    def unavailable():
        raise StructuralDependencyError("parser dependency is unavailable")

    monkeypatch.setattr("diffgraph.structural._parser", unavailable)
    result = CliRunner().invoke(
        main, ["--structural-json", "-", "diff", "--staged"]
    )
    assert result.exit_code == 1
    assert "parser dependency is unavailable" in result.output
    assert "PARSE_FAILURE" not in result.output


def test_missing_ai_dependency_is_a_click_error(tmp_path, monkeypatch):
    import builtins
    from click.testing import CliRunner
    from diffgraph.cli import main

    root = repo(tmp_path)
    monkeypatch.chdir(root)
    real_import = builtins.__import__

    def without_spinner(name, *args, **kwargs):
        if name == "click_spinner":
            raise ImportError("simulated missing spinner")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_spinner)
    result = CliRunner().invoke(main, ["diff"])
    assert result.exit_code == 1
    assert "requires additional dependencies" in result.output
    assert "Traceback" not in result.output
