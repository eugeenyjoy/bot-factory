"""
Bot Factory — Setup
Works on Windows, Linux, macOS
"""

import subprocess
import sys
import os
import platform

def run(cmd):
    print(f"  > {cmd}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0

def main():
    system = platform.system()

    # project root = one level up from setup/
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    print("=" * 50)
    print("  Bot Factory — Setup")
    print(f"  OS: {system}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Folder: {project_root}")
    print("=" * 50)
    print()

    # check Python version
    if sys.version_info < (3, 9):
        print("[ERROR] Need Python 3.9+")
        print("  https://www.python.org/downloads/")
        input("\nPress Enter...")
        sys.exit(1)

    if sys.version_info >= (3, 13):
        print("[ERROR] Python 3.13+ is too new, libraries don't support it yet")
        print("  Install Python 3.12:")
        print("  https://www.python.org/downloads/release/python-31210/")
        input("\nPress Enter...")
        sys.exit(1)

    # check requirements.txt
    if not os.path.exists("requirements.txt"):
        print("[ERROR] requirements.txt not found")
        print("  Run from project root: python setup/setup.py")
        input("\nPress Enter...")
        sys.exit(1)

    # paths
    venv_dir = os.path.join(project_root, "venv")

    if system == "Windows":
        python = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        python = os.path.join(venv_dir, "bin", "python")

    # create venv
    if not os.path.exists(venv_dir):
        print("[1/3] Creating virtual environment...")
        if not run(f"{sys.executable} -m venv venv"):
            print("[ERROR] Failed to create venv")
            input("\nPress Enter...")
            sys.exit(1)
    else:
        print("[1/3] Virtual environment exists OK")

    # upgrade pip (using python -m pip to avoid Windows lock)
    print("[2/3] Upgrading pip...")
    run(f"{python} -m pip install --upgrade pip")

    # install dependencies
    print("[3/3] Installing dependencies (2-5 minutes)...")
    if not run(f"{python} -m pip install -r requirements.txt"):
        print("[ERROR] Failed to install dependencies")
        input("\nPress Enter...")
        sys.exit(1)

    # done
    print()
    print("=" * 50)
    print("  [OK] Installation complete!")
    print("=" * 50)
    print()

    if system == "Windows":
        print("  To start: double-click Launch_Windows.bat")
    else:
        print("  To start: bash Launch_Linux.sh")
    print("  Then open: http://localhost:8000")
    print()
    input("Press Enter...")

if __name__ == "__main__":
    main()
