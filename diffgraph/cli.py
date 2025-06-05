import subprocess
import sys
from pathlib import Path
import click
from typing import List, Dict
import os
from .ai_analysis import CodeAnalysisAgent
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

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

def get_all_files_in_directory(directory: str) -> List[str]:
    """
    Recursively get all files in a directory.
    Excludes .git directory and other hidden files/folders.
    """
    all_files = []
    for root, dirs, files in os.walk(directory):
        # Skip .git directory and other hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for file in files:
            # Skip hidden files
            if not file.startswith('.'):
                full_path = os.path.join(root, file)
                # Convert to relative path
                rel_path = os.path.relpath(full_path, os.getcwd())
                all_files.append(rel_path)
    return all_files

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

    # Get untracked files and directories
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True
        )
        for line in result.stdout.strip().split('\n'):
            if line.startswith('??'):  # Untracked files/directories
                path = line[3:].strip()

                if os.path.isdir(path):
                    # If it's a directory, get all files in it
                    files_in_dir = get_all_files_in_directory(path)
                    for file_path in files_in_dir:
                        changed_files.append({
                            'path': file_path,
                            'status': 'untracked'
                        })
                else:
                    # If it's a file, add it directly
                    changed_files.append({
                        'path': path,
                        'status': 'untracked'
                    })
    except subprocess.CalledProcessError as e:
        click.echo(f"Error getting untracked files: {e}", err=True)
        sys.exit(1)

    return changed_files

def load_file_contents(changed_files: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Load contents of changed files.
    For modified files, gets the diff content.
    For untracked files, reads the entire file.
    """
    files_with_content = []

    for file_info in changed_files:
        file_path = file_info['path']
        status = file_info['status']

        try:
            if status == 'modified':
                # Get diff content for modified files
                result = subprocess.run(
                    ["git", "diff", file_path],
                    check=True,
                    capture_output=True,
                    text=True
                )
                content = result.stdout
            else:  # untracked
                # Read entire file for untracked files
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

            files_with_content.append({
                'path': file_path,
                'status': status,
                'content': content
            })
        except (subprocess.CalledProcessError, IOError) as e:
            click.echo(f"Error reading file {file_path}: {e}", err=True)
            continue

    return files_with_content

@click.command()
@click.version_option()
@click.option('--api-key', envvar='OPENAI_API_KEY', help='OpenAI API key')
def main(api_key: str):
    """DiffGraph - Visualize code changes with AI."""
    if not is_git_repo():
        click.echo("Error: Not a git repository", err=True)
        sys.exit(1)

    changed_files = get_changed_files()

    if not changed_files:
        click.echo("No changes to analyze")
        sys.exit(0)

    # Load contents of changed files
    files_with_content = load_file_contents(changed_files)

    try:
        # Initialize the AI analysis agent
        agent = CodeAnalysisAgent(api_key=api_key)

        # Analyze the changes
        analysis = agent.analyze_changes(files_with_content)

        # Print the analysis results
        click.echo("\nAnalysis Summary:")
        click.echo(analysis.summary)

        click.echo("\nDependency Diagram:")
        click.echo("```mermaid")
        click.echo(analysis.mermaid_diagram)
        click.echo("```")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error during analysis: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()