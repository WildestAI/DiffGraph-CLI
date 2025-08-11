import subprocess
import sys
from pathlib import Path
import click
from click_spinner import spinner
from typing import List, Dict
import os
from diffgraph.ai_analysis import CodeAnalysisAgent
from diffgraph.html_report import generate_html_report, AnalysisResult
from diffgraph.env_loader import load_env_file, debug_environment
from diffgraph.utils import sanitize_diff_args, involves_working_tree

# Load environment variables
load_env_file()

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

def get_changed_files(diff_args: List[str] = None) -> List[Dict[str, str]]:
    """
    Get list of changed and untracked files.
    Returns a list of dicts with 'path' and 'status' keys.
    """
    if diff_args is None:
        diff_args = []

    changed_files = []

    # Get modified/staged files
    try:
        sanitized_args, pathspecs = sanitize_diff_args(diff_args)
        cmd = ["git", "diff", "--name-only"] + sanitized_args
        if pathspecs:
            cmd += ["--"] + pathspecs
        result = subprocess.run(
            cmd,
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

    # Decide if we should include untracked files
    if involves_working_tree(diff_args):
        try:
            # Use git ls-files for native untracked file detection
            # --others: show untracked files
            # --exclude-standard: respect .gitignore patterns
            # -z: null-byte separated output for reliable parsing
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", "-z"],
                check=True,
                capture_output=True,
                text=True
            )

            # Split on null byte and filter out empty strings
            untracked_files = [path for path in result.stdout.split('\0') if path.strip()]

            for file_path in untracked_files:
                changed_files.append({
                    'path': file_path,
                    'status': 'untracked'
                })
        except subprocess.CalledProcessError as e:
            click.echo(f"Error getting untracked files: {e}", err=True)
            sys.exit(1)

    return changed_files

def load_file_contents(changed_files: List[Dict[str, str]], diff_args: List[str] = None) -> List[Dict[str, str]]:
    """
    Load contents of changed files.
    For modified files, gets the diff content.
    For untracked files, reads the entire file.
    """
    if diff_args is None:
        diff_args = []

    files_with_content = []

    for file_info in changed_files:
        file_path = file_info['path']
        status = file_info['status']

        try:
            if status == 'modified':
                # Get diff content for modified files with sanitized args and proper separator
                sanitized_args, _ = sanitize_diff_args(diff_args)
                cmd = ["git", "diff"] + sanitized_args + ["--", file_path]
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True
                )
                content = result.stdout
            else:  # untracked
                # Read entire file for untracked files
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
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

@click.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.version_option(package_name='wild')
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
@click.option('--api-key', envvar='OPENAI_API_KEY', help='OpenAI API key')
@click.option('--output', '-o', default='diffgraph.html', help='Output HTML file path')
@click.option('--no-open', is_flag=True, help='Do not open the HTML report automatically')
@click.option('--debug-env', is_flag=True, help='Debug environment variable loading')
def main(args, api_key: str, output: str, no_open: bool, debug_env: bool):
    """wild - Git wrapper CLI with DiffGraph for diff commands."""

    # Check if this is a diff command
    if args and args[0] == 'diff':
        # Handle diff command with custom logic
        diff_args = list(args[1:])  # Skip 'diff' and pass remaining args

        # Debug environment variable loading if requested
        if debug_env:
            debug_environment(api_key)
            return

        if not is_git_repo():
            click.echo("❌ Error: Not a git repository", err=True)
            sys.exit(1)

        click.echo("🔍 Scanning for changed files...")
        changed_files = get_changed_files(diff_args)

        if not changed_files:
            click.echo("ℹ️ No changes to analyze")
            sys.exit(0)

        click.echo(f"📝 Found {len(changed_files)} changed files")

        # Load contents of changed files with progress bar
        with click.progressbar(changed_files, label='📖 Loading file contents') as files:
            files_with_content = load_file_contents(files, diff_args)

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
    else:
        # Pass through to git for all other commands
        try:
            result = subprocess.run(["git"] + list(args))
            sys.exit(result.returncode)
        except Exception as e:
            click.secho(f"❌ Error running git command: {e}", fg="red", err=True)
            sys.exit(1)

if __name__ == "__main__":
    main()