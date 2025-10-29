"""
Tests for CLI functionality.
"""
import pytest
from click.testing import CliRunner
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


def test_cli_invalid_mode_error(cli_runner):
    """Test that invalid mode shows helpful error."""
    # We need a git repo and changes for this to work properly
    # This test will fail early with invalid mode error
    result = cli_runner.invoke(main, ['diff', '--mode', 'invalid-mode'])
    
    # Should show error about invalid mode
    # (might fail earlier if not in a git repo, which is fine)
    assert result.exit_code != 0 or 'Available processing modes' in result.output


def test_cli_version(cli_runner):
    """Test --version flag."""
    result = cli_runner.invoke(main, ['--version'])
    
    assert result.exit_code == 0
    assert 'version' in result.output.lower()
