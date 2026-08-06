import json
import subprocess
import sys
from pathlib import Path
import click
from typing import List, Dict
import os
from diffgraph import __version__
from diffgraph.env_loader import load_env_file, debug_environment
from diffgraph.git_snapshot import GitSnapshotError
from diffgraph.utils import sanitize_diff_args, involves_working_tree
from diffgraph.structural import StructuralDependencyError, analyze_local_diff

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

class _RawArgsCommand(click.Command):
    """Retain the raw separator that Click removes from variadic arguments."""

    def parse_args(self, ctx, args):
        ctx.meta["raw_args"] = tuple(args)
        return super().parse_args(ctx, args)


def _separator_follows_diff(raw_args) -> bool:
    """Return whether the raw CLI placed ``--`` after the ``diff`` operand."""

    value_options = {"--api-key", "--output", "-o", "--structural-json", "--format"}
    index = 0
    while index < len(raw_args):
        argument = raw_args[index]
        if argument in value_options:
            index += 2
            continue
        if any(argument.startswith(option + "=") for option in value_options):
            index += 1
            continue
        if argument.startswith("-o") and argument != "-o":
            index += 1
            continue
        if argument == "diff":
            return "--" in raw_args[index + 1 :]
        index += 1
    return False


def _structural_scope(diff_args: List[str], separator_present: bool = False):
    """Accept only the exact local snapshot modes implemented by this increment."""
    staged = False
    pathspecs = []
    after_separator = separator_present
    for argument in diff_args:
        if argument == "--":
            after_separator = True
        elif argument in ("--staged", "--cached") and not after_separator:
            staged = True
        elif after_separator:
            pathspecs.append(argument)
        else:
            raise click.UsageError(
                "--structural-json currently supports only unstaged or --staged/--cached "
                "local diffs; put pathspecs after '--'"
            )
    return staged, pathspecs


def _validate_structural_artifact(artifact):
    """Fail closed when the canonical v2 schema cannot validate the artifact."""
    try:
        import jsonschema
    except ImportError as error:
        raise click.ClickException(
            "jsonschema is required to validate --structural-json output"
        ) from error
    schema_path = Path(__file__).parent / "schema" / "diffgraph-v2.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(artifact, schema)
    except (
        OSError,
        json.JSONDecodeError,
        jsonschema.ValidationError,
        jsonschema.SchemaError,
    ) as error:
        raise click.ClickException(f"structural artifact validation failed: {error}") from error


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

@click.command(
    cls=_RawArgsCommand,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.version_option(package_name='wild')
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
@click.option('--api-key', envvar='OPENAI_API_KEY', help='OpenAI API key')
@click.option('--output', '-o', default='diffgraph.html', help='Output HTML file path')
@click.option(
    '--format',
    'output_format',
    type=click.Choice(['html', 'terminal'], case_sensitive=False),
    default='html',
    show_default=True,
    help='Render the legacy HTML report or a local structural terminal review',
)
@click.option('--compact', is_flag=True, help='Hide terminal CONTEXT output')
@click.option('--all', 'show_all', is_flag=True, help='Show all terminal review items')
@click.option('--no-open', is_flag=True, help='Do not open the HTML report automatically')
@click.option('--debug-env', is_flag=True, help='Debug environment variable loading')
@click.option(
    '--structural-json',
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the local Python structural DiffGraph v2 artifact ('-' for stdout)",
)
def main(
    args,
    api_key: str,
    output: str,
    output_format: str,
    compact: bool,
    show_all: bool,
    no_open: bool,
    debug_env: bool,
    structural_json: Path,
):
    """wild - Git wrapper CLI with DiffGraph for diff commands."""

    if structural_json is not None and (not args or args[0] != "diff"):
        raise click.UsageError("--structural-json can only be used with 'diff'")
    if output_format == "terminal" and (not args or args[0] != "diff"):
        raise click.UsageError("--format terminal can only be used with 'diff'")
    if output_format == "terminal" and structural_json is not None:
        raise click.UsageError("--format terminal cannot be combined with --structural-json")

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

        if structural_json is not None or output_format == "terminal":
            raw_args = click.get_current_context().meta.get("raw_args", ())
            staged, pathspecs = _structural_scope(
                diff_args, separator_present=_separator_follows_diff(raw_args)
            )
            try:
                artifact = analyze_local_diff(
                    ".", staged=staged, pathspecs=pathspecs, wild_version=__version__
                )
            except (GitSnapshotError, StructuralDependencyError) as error:
                raise click.ClickException(str(error)) from error
            _validate_structural_artifact(artifact)
            if output_format == "terminal":
                from diffgraph.formatters.terminal import TerminalFormatter

                try:
                    TerminalFormatter(
                        artifact,
                        compact=compact,
                        max_items=(
                            None if show_all else TerminalFormatter.DEFAULT_MAX_ITEMS
                        ),
                    ).render()
                except ValueError as error:
                    raise click.ClickException(str(error)) from error
            else:
                rendered = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
                if str(structural_json) == "-":
                    click.echo(rendered, nl=False)
                else:
                    try:
                        structural_json.write_text(rendered, encoding="utf-8")
                    except OSError as error:
                        raise click.ClickException(
                            f"could not write {structural_json}: {error}"
                        ) from error
                    click.echo(f"✅ Structural DiffGraph written: {structural_json}", err=True)
            return

        # Keep the legacy AI/HTML path lazy so local structural output never
        # imports a network-capable SDK.
        try:
            from click_spinner import spinner
            from diffgraph.ai_analysis import CodeAnalysisAgent
            from diffgraph.html_report import generate_html_report, AnalysisResult
        except ImportError as error:
            raise click.ClickException(
                f"The AI report path requires additional dependencies: {error}"
            ) from error

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
