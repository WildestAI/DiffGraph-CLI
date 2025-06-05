import subprocess
import sys
from pathlib import Path
import click
from typing import List, Dict

def is_git_repo() -> bool:
    """Check if current directory is a git repository."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def get_changed_files() -> List[Dict[str, str]]:
    """
    Get list of changed and untracked files.
    Returns a list of dicts with 'path' and 'status' keys.
    """
    changed_files = []

    # Get modified/staged files
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            check=True,
            capture_output=True,
            text=True
        )
        for file_path in result.stdout.strip().split('\n'):
            if file_path:  # Skip empty lines
                changed_files.append({
                    'path': file_path,
                    'status': 'modified'
                })
    except subprocess.CalledProcessError as e:
        click.echo(f"Error getting modified files: {e}", err=True)
        sys.exit(1)

    # Get untracked files
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True
        )
        for line in result.stdout.strip().split('\n'):
            if line.startswith('??'):  # Untracked files
                file_path = line[3:].strip()
                changed_files.append({
                    'path': file_path,
                    'status': 'untracked'
                })
    except subprocess.CalledProcessError as e:
        click.echo(f"Error getting untracked files: {e}", err=True)
        sys.exit(1)

    return changed_files

@click.command()
@click.version_option()
def main():
    """DiffGraph - Visualize code changes with AI."""
    if not is_git_repo():
        click.echo("Error: Not a git repository", err=True)
        sys.exit(1)

    changed_files = get_changed_files()

    if not changed_files:
        click.echo("No changes to analyze")
        sys.exit(0)

    # Print the list of changed files
    click.echo("Changed files:")
    for file_info in changed_files:
        click.echo(f"{file_info['status']}: {file_info['path']}")

if __name__ == "__main__":
    main()