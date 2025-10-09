# Building Unpackr

## Option 1: Batch File (Recommended - Simple)

1. Copy `unpackr.bat` to a directory in your PATH (e.g., `C:\Windows\System32` or `C:\bin`)
2. Run from anywhere:
   ```powershell
   unpackr --source "G:\Downloads" --destination "G:\Videos"
   ```

**Pros:**
- Simple, no build needed
- Easy to update (just edit unpackr.py)
- Small footprint

**Cons:**
- Requires Python installed
- Batch file must be in PATH

## Option 2: PyInstaller Executable (Advanced)

Build a standalone .exe that doesn't require Python:

```powershell
# Install PyInstaller
pip install pyinstaller

# Build executable
python build.py

# Result: dist/unpackr.exe
```

**Pros:**
- Standalone (no Python needed)
- Single .exe file
- Can distribute to others

**Cons:**
- Large file size (~20-50 MB)
- Rebuild needed for updates
- Slower startup

## Option 3: Add to PATH (Developer Mode)

Add the Unpackr directory to your PATH:

```powershell
# Add to PATH (PowerShell Admin)
$path = [Environment]::GetEnvironmentVariable('PATH', 'User')
$newPath = $path + ';G:\Unpackr'
[Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')

# Create alias
New-Alias -Name unpackr -Value "G:\Unpackr\unpackr.py"

# Run from anywhere
unpackr --help
```

**Pros:**
- Direct access to source
- No build/copy needed
- Easy debugging

**Cons:**
- Requires PATH configuration
- Python must be in PATH

## Recommendation

**For personal use:** Option 1 or 3 (simple, easy to update)  
**For distribution:** Option 2 (standalone executable)

## After Installation

Test it works:
```powershell
unpackr --help
unpackr --source "G:\test" --destination "G:\output"
```
