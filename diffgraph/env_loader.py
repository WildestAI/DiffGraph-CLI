"""
Environment variable loading utilities for DiffGraph CLI.
Handles loading .env files in both development and bundled environments.
"""

import os
import sys
from typing import List
from dotenv import load_dotenv


def is_pyinstaller_bundle() -> bool:
    """Check if running in a PyInstaller bundle."""
    return getattr(sys, 'frozen', False)


def get_bundle_directory() -> str:
    """Get the PyInstaller bundle directory if available."""
    if is_pyinstaller_bundle() and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return None


def get_possible_env_paths() -> List[str]:
    """Get all possible paths where .env file might be located."""
    possible_paths = [
        ".env",  # Current directory (development)
        os.path.join(os.path.dirname(__file__), "..", ".env"),  # Relative to module
    ]

    # Add executable path if available
    if hasattr(sys, 'executable'):
        possible_paths.append(os.path.join(os.path.dirname(sys.executable), ".env"))

    # If running in PyInstaller bundle, try to get the bundled .env file
    bundle_dir = get_bundle_directory()
    if bundle_dir:
        possible_paths.insert(0, os.path.join(bundle_dir, ".env"))

    return possible_paths


def load_env_file():
    """Load environment variables from .env file, handling both development and bundled environments."""
    env_loaded = False

    # Try each possible path
    for env_path in get_possible_env_paths():
        if os.path.exists(env_path):
            load_dotenv(env_path)
            env_loaded = True
            break

    if not env_loaded:
        # Fallback: try to load from current directory (original behavior)
        load_dotenv()


def get_environment_debug_info() -> dict:
    """Get debug information about environment variable loading."""
    info = {
        'current_working_directory': os.getcwd(),
        'executable_path': sys.executable,
        'module_path': __file__,
        'is_bundle': is_pyinstaller_bundle(),
        'bundle_directory': get_bundle_directory(),
        'possible_env_paths': get_possible_env_paths(),
        'env_file_exists': {},
        'openai_api_key_set': bool(os.getenv('OPENAI_API_KEY')),
        'openai_api_key_value': os.getenv('OPENAI_API_KEY', '')
    }

    # Check which .env files exist
    for path in info['possible_env_paths']:
        info['env_file_exists'][path] = os.path.exists(path)

    return info


def debug_environment(api_key_from_cli: str = None):
    """
    Display comprehensive debug information about environment variable loading.

    Args:
        api_key_from_cli: API key passed via command line argument
    """
    import click

    click.echo("🔍 Debugging environment variable loading...")

    # Get debug information from the environment loader module
    debug_info = get_environment_debug_info()

    click.echo(f"Current working directory: {debug_info['current_working_directory']}")
    click.echo(f"Executable path: {debug_info['executable_path']}")
    click.echo(f"Module path: {debug_info['module_path']}")

    if debug_info['is_bundle']:
        click.echo("✅ Running in PyInstaller bundle")
        if debug_info['bundle_directory']:
            click.echo(f"Bundle directory: {debug_info['bundle_directory']}")
    else:
        click.echo("📦 Running in development mode")

    click.echo("\n🔍 Checking for .env file:")
    for path in debug_info['possible_env_paths']:
        exists = debug_info['env_file_exists'][path]
        click.echo(f"  {path}: {'✅' if exists else '❌'}")

    # Check environment variables
    click.echo(f"\n🔑 OPENAI_API_KEY: {'✅ Set' if debug_info['openai_api_key_set'] else '❌ Not set'}")
    if debug_info['openai_api_key_value']:
        api_key_value = debug_info['openai_api_key_value']
        click.echo(f"   Value: {api_key_value[:10]}...{api_key_value[-4:] if len(api_key_value) > 14 else ''}")

    click.echo(f"🔑 API Key from CLI: {'✅ Set' if api_key_from_cli else '❌ Not set'}")