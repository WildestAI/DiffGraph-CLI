"""
Tests for CLI functionality.
"""
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from diffgraph import cli
from diffgraph.cli import main


@pytest.fixture
def cli_runner():
    """Fixture providing a Click CLI runner."""
    return CliRunner()


def test_cli_list_modes(cli_runner):
    """Test --list-modes flag."""
    result = cli_runner.invoke(main, ['diff', '--list-modes'])
    
    assert result.exit_code == 0
    assert 'Available processing modes' in result.output
    assert 'openai-agents-dependency-graph' in result.output


def test_cli_help_shows_mode_option(cli_runner):
    """Test that help shows --mode option."""
    result = cli_runner.invoke(main, ['diff', '--help'])
    
    assert result.exit_code == 0
    assert '--mode' in result.output or '-m' in result.output
    assert '--list-modes' in result.output


def test_cli_help_shows_default_mode(cli_runner):
    """Test that help shows default mode."""
    result = cli_runner.invoke(main, ['diff', '--help'])
    
    assert result.exit_code == 0
    # Mode name might be wrapped, so check for components
    assert 'openai-agents-dependency-graph' in result.output or \
           ('openai-' in result.output and 'dependency-graph' in result.output)


def test_cli_invalid_mode_error(cli_runner, monkeypatch):
    """Invalid modes are rejected even when the repository has no changes."""
    monkeypatch.setattr(cli, "is_git_repo", lambda: True)
    monkeypatch.setattr(cli, "get_changed_files", lambda args: [])

    result = cli_runner.invoke(main, ['diff', '--mode', 'invalid-mode'])

    assert result.exit_code == 1
    assert "Unknown processing mode: 'invalid-mode'" in result.output
    assert 'Use --list-modes to see available processing modes.' in result.output


def test_cli_version(cli_runner):
    """Test --version flag."""
    result = cli_runner.invoke(main, ['--version'])
    
    assert result.exit_code == 0
    assert 'version' in result.output.lower()


@pytest.mark.parametrize(
    ("graph_format", "export_name"),
    [("json", "export_structured_json"), ("pickle", "export_graph")],
)
def test_cli_exports_selected_processors_graph(
    cli_runner, monkeypatch, graph_format, export_name
):
    """Graph export uses the selected processor rather than a stale variable."""
    graph_manager = object()
    processor = SimpleNamespace(
        graph_manager=graph_manager,
        analyze_changes=lambda files, callback: SimpleNamespace(),
    )
    exported = {}

    monkeypatch.setattr(cli, "is_git_repo", lambda: True)
    monkeypatch.setattr(
        cli, "get_changed_files", lambda args: [{"path": "example.py", "status": "modified"}]
    )
    monkeypatch.setattr(
        cli,
        "load_file_contents",
        lambda files, args: [{"path": "example.py", "status": "modified", "content": ""}],
    )
    monkeypatch.setattr(cli, "get_processor", lambda mode, api_key=None: processor)

    def record_export(manager, output, *args):
        exported["manager"] = manager
        return output

    monkeypatch.setattr(cli, export_name, record_export)

    result = cli_runner.invoke(
        main,
        [
            "--format",
            "graph",
            "--graph-format",
            graph_format,
            "--output",
            "result.json",
            "diff",
        ],
    )

    assert result.exit_code == 0, result.output
    assert exported["manager"] is graph_manager
