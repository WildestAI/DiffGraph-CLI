import subprocess
import sys
from pathlib import Path
import click
from click_spinner import spinner
from typing import List, Dict
import os
from diffgraph.ai_analysis import CodeAnalysisAgent
from diffgraph.html_report import generate_html_report, AnalysisResult
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

def is_clean_state() -> bool:
    """Check if the working directory is clean (no changes)."""
    try:
        # Check for any changes in tracked files
        diff_result = subprocess.run(
            ["git", "diff", "--quiet"],
            capture_output=True
        )

        # Check for any untracked files
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True
        )

        # If diff returns 0 (no changes) and status is empty (no untracked files)
        return diff_result.returncode == 0 and not status_result.stdout.strip()
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
@click.option('--output', '-o', default='diffgraph.html', help='Output HTML file path')
@click.option('--no-open', is_flag=True, help='Do not open the HTML report automatically')
def main(api_key: str, output: str, no_open: bool):
    """DiffGraph - Visualize code changes with AI."""
    if not is_git_repo():
        click.echo("❌ Error: Not a git repository", err=True)
        sys.exit(1)

    if is_clean_state():
        click.echo("ℹ️ No changes to analyze - working directory is clean")
        sys.exit(0)

    click.echo("🔍 Scanning for changed files...")
    changed_files = get_changed_files()

    if not changed_files:
        click.echo("ℹ️ No changes to analyze")
        sys.exit(0)

    click.echo(f"📝 Found {len(changed_files)} changed files")

    # Load contents of changed files with progress bar
    with click.progressbar(changed_files, label='📖 Loading file contents') as files:
        files_with_content = load_file_contents(files)

    try:
        # Initialize the AI analysis agent
        click.echo("🤖 Initializing AI analysis...")
        agent = CodeAnalysisAgent(api_key=api_key)

        # Define progress callback
        def progress_callback(current_file, total_files, status):
            if current_file is None:
                click.echo("📊 Generating final diagram...")
                return

            file_name = os.path.basename(current_file)
            current_index = len(agent.graph_manager.processed_files) + 1

            if status == "processing":
                click.echo(f"🔄 Processing {file_name} ({current_index}/{total_files})...")
            elif status == "analyzing":
                click.echo(f"🧠 Analyzing {file_name} with AI ({current_index}/{total_files})...")
            elif status == "processing_components":
                click.echo(f"🔍 Processing components in {file_name} ({current_index}/{total_files})...")
            elif status == "completed":
                click.echo(f"✅ Completed analysis of {file_name} ({current_index}/{total_files})...")
            elif status == "error":
                click.echo(f"❌ Error analyzing {file_name} ({current_index}/{total_files})...")

        # Analyze the changes with progress updates
        click.echo("🧠 Starting code analysis...")
        analysis = agent.analyze_changes(files_with_content, progress_callback)

        # Create analysis result
        click.echo("📊 Creating analysis result...")
        analysis_result = AnalysisResult(
            summary=analysis.summary,
            mermaid_diagram=analysis.mermaid_diagram
        )

        # Generate HTML report
        click.echo("🖨️ Generating HTML report...")
        html_path = generate_html_report(analysis_result, output)
        click.echo(f"✅ HTML report generated: {html_path}")

        # Open the HTML report in the default browser
        if not no_open:
            click.echo("🌐 Opening report in browser...")
            if sys.platform == 'darwin':  # macOS
                subprocess.run(['open', html_path])
            elif sys.platform == 'win32':  # Windows
                os.startfile(html_path)
            else:  # Linux
                subprocess.run(['xdg-open', html_path])

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error during analysis: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    main()