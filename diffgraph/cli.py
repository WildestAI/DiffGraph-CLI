import subprocess
import sys
from pathlib import Path
import click

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

@click.command()
@click.version_option()
def main():
    """DiffGraph - Visualize code changes with AI."""
    if not is_git_repo():
        click.echo("Error: Not a git repository", err=True)
        sys.exit(1)

    try:
        result = subprocess.run(
            ["git", "diff"],
            check=True,
            capture_output=True,
            text=True
        )
        click.echo(result.stdout)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running git diff: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()