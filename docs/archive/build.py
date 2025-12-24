"""
Build script for creating standalone Unpackr executable.

Usage:
    python build.py

This will create:
    - dist/unpackr.exe (standalone executable)
    - dist/unpackr/ (folder with all dependencies)
"""

import PyInstaller.__main__
import shutil
from pathlib import Path

def build():
    """Build standalone executable using PyInstaller."""
    
    print("Building Unpackr executable...")
    
    # Clean previous builds
    if Path('build').exists():
        shutil.rmtree('build')
    if Path('dist').exists():
        shutil.rmtree('dist')
    
    # PyInstaller options
    PyInstaller.__main__.run([
        'unpackr.py',
        '--name=unpackr',
        '--onefile',
        '--console',
        '--clean',
        # Add data files
        '--add-data=config_files;config_files',
        '--add-data=core;core',
        '--add-data=utils;utils',
        # Hidden imports
        '--hidden-import=colorama',
        '--hidden-import=tqdm',
        '--hidden-import=psutil',
        # Icon (if you have one)
        # '--icon=icon.ico',
    ])
    
    print("\nBuild complete!")
    print("Executable: dist/unpackr.exe")
    print("\nTo install globally, add dist/ to your PATH or copy unpackr.exe to a directory in PATH")

if __name__ == '__main__':
    try:
        build()
    except ImportError:
        print("PyInstaller not found. Install with:")
        print("  pip install pyinstaller")
    except Exception as e:
        print(f"Build failed: {e}")
