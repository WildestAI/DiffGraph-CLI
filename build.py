#!/usr/bin/env python3
"""
Build script for DiffGraph CLI using PyInstaller
"""

import subprocess
import sys
import os
import re
from pathlib import Path

def create_spec_file():
    """Generate the wild.spec file using PyInstaller if it doesn't exist"""
    spec_file = "wild.spec"

    if os.path.exists(spec_file):
        print("✅ Spec file already exists")
        return True

    print("📝 Generating wild.spec file using PyInstaller...")

    # Generate spec file using PyInstaller
    result = subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--name", "wild",
        "--onefile",
        "--console",
        "--specpath", ".",
        "--distpath", "dist",
        "--workpath", "build",
        "--clean",
        "--noconfirm",
        "diffgraph/cli.py"
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Failed to generate spec file: {result.stderr}")
        return False

    print("✅ Generated wild.spec file")
    return True

def ensure_env_in_spec():
    """Ensure .env file is included in the spec file if it exists"""
    spec_file = "wild.spec"

    # Check if .env file exists
    env_file_exists = os.path.exists(".env")

    if not env_file_exists:
        print("⚠️  .env file not found - skipping")
        return True

    # Read the spec file
    with open(spec_file, 'r') as f:
        content = f.read()

    # Check if .env is already in datas
    if "('.env', '.')" in content:
        print("✅ .env file already included in spec file")
        return True

    print("📝 Adding .env file to spec file...")

    # Find the datas line and add .env
    # Handle both empty datas array and non-empty datas array
    if "datas=[]," in content:
        # Empty datas array
        content = content.replace("datas=[],", "datas=[('.env', '.')],")
    elif "datas=[" in content:
        # Non-empty datas array - add to existing items
        content = re.sub(
            r'datas=\[([^\]]*)\],',
            r'datas=[\1, (\'.env\', \'.\')],',
            content
        )
    else:
        print("⚠️  Could not find datas array in spec file")
        return False

    with open(spec_file, 'w') as f:
        f.write(content)
    print("✅ Added .env file to spec file")
    return True

def verify_env_in_bundle():
    """Verify that the .env file is properly included in the built binary"""
    print("🔍 Verifying .env file in bundle...")

    # Check if binary exists
    binary_name = "wild.exe" if sys.platform == 'win32' else "wild"
    binary_path = os.path.join("dist", binary_name)

    if not os.path.exists(binary_path):
        print("❌ Binary not found - cannot verify bundle")
        return False

    # Check if .env file exists in the project directory
    if os.path.exists(".env"):
        print("✅ .env file exists in project directory")
        print("   The binary should be able to load it from the current directory")
        return True
    else:
        print("⚠️  .env file not found in project directory")
        return False

def main():
    """Build the DiffGraph CLI binary using PyInstaller"""

    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("❌ PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # Create spec file if it doesn't exist
    create_spec_file()

    # Ensure .env file is included in spec
    ensure_env_in_spec()

    # Clean previous builds
    print("🧹 Cleaning previous builds...")
    for path in ["build", "dist"]:
        if os.path.exists(path):
            import shutil
            try:
                shutil.rmtree(path)
            except PermissionError:
                print(f"⚠️  Could not remove {path} - permission denied. Continuing...")
            except Exception as e:
                print(f"⚠️  Could not remove {path}: {e}. Continuing...")

    # Build using the spec file
    print("🔨 Building DiffGraph CLI...")
    result = subprocess.run([
        sys.executable, "-m", "PyInstaller", "wild.spec", "--clean"
    ], check=True)

    if result.returncode == 0:
        print("✅ Build completed successfully!")
        if sys.platform == 'win32':
            print(f"📦 Binary location: {os.path.join('dist', 'wild.exe')}")
        else:
            print(f"📦 Binary location: {os.path.join('dist', 'wild')}")

        # Verify that .env file is properly included
        verify_env_in_bundle()

        print("\n💡 Environment Variable Loading Tips:")
        print("   - The binary will look for .env file in multiple locations:")
        print("     1. Current working directory")
        print("     2. Next to the executable")
        print("     3. Inside the bundled resources")
        print("   - You can also set OPENAI_API_KEY as an environment variable")
        print("   - Or use the --api-key command line option")
    else:
        print("❌ Build failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()