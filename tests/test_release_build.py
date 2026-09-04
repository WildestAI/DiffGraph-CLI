from pathlib import Path

import pytest

import build


def test_release_build_command_does_not_add_data_files(tmp_path):
    command = build.build_command(
        output_dir=tmp_path / "release",
        work_dir=tmp_path / "work",
        spec_dir=tmp_path / "spec",
        name="wild",
    )

    assert "--onefile" in command
    assert "--add-data" not in command
    assert "--add-binary" not in command
    assert all(".env" not in argument for argument in command)


def test_release_build_rejects_local_dotenv(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=must-not-bundle\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="never package .env files"):
        build.assert_release_workspace_safe(tmp_path)


def test_release_build_allows_env_example(tmp_path):
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    assert build.find_forbidden_files(tmp_path) == []


def test_release_build_rejects_nested_dotenv(tmp_path):
    nested_env = tmp_path / "package" / ".env"
    nested_env.parent.mkdir()
    nested_env.write_text("OPENAI_API_KEY=must-not-bundle\n", encoding="utf-8")

    assert build.find_forbidden_files(tmp_path) == [nested_env]
