# Quick Install Guide

## Make `unpackr` Available as a Command

After installation, you can run from anywhere:
```powershell
unpackr --source "C:\Downloads" --destination "D:\Videos"
```

## Installation Steps

### Option 1: Copy Batch File (Easiest)

1. **Copy the launcher to a directory in PATH:**
   ```powershell
   # Copy to System32 (requires admin)
   copy unpackr.bat C:\Windows\System32\
   ```

2. **Test it works:**
   ```powershell
   cd C:\
   unpackr --help
   ```

3. **Use from anywhere:**
   ```powershell
   unpackr --source "C:\test" --destination "D:\test"
   ```

### Option 2: Add to User PATH (No Admin Required)

1. **Add Unpackr directory to your PATH:**
   ```powershell
   # Open System Properties > Environment Variables
   # Or use PowerShell:
   $currentPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
   $newPath = $currentPath + ';G:\Unpackr'
   [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
   ```

2. **Restart your terminal**

3. **Run from anywhere:**
   ```powershell
   unpackr.bat --source "C:\test" --destination "D:\test"
   ```

### Option 3: PowerShell Alias (Session-Based)

1. **Create alias in PowerShell profile:**
   ```powershell
   # Edit profile
   notepad $PROFILE
   
   # Add this line:
   function unpackr { python G:\Unpackr\unpackr.py $args }
   ```

2. **Reload profile:**
   ```powershell
   . $PROFILE
   ```

3. **Use it:**
   ```powershell
   unpackr --source "C:\test" --destination "D:\test"
   ```

## Verification

After installation, test from any directory:

```powershell
cd C:\
unpackr --help

# Should show ASCII art and help text
```

## Usage Examples

Once installed:

```powershell
# Interactive mode (prompts for paths)
unpackr

# With arguments
unpackr --source "C:\Downloads" --destination "D:\Videos"

# With custom config
unpackr --source "C:\Downloads" --destination "D:\Videos" --config "custom.json"

# Paths with or without quotes work
unpackr --source C:\Downloads --destination D:\Videos
unpackr --source "C:\My Downloads" --destination "D:\My Videos"
```

## Troubleshooting

**"unpackr is not recognized..."**
- PATH not set correctly
- Restart terminal after PATH changes
- Check: `where unpackr.bat` or `where unpackr`

**"Python not found..."**
- Python not in PATH
- Install Python or add to PATH
- Or build standalone .exe (see BUILD.md)

**Permission denied**
- Run as Administrator
- Or use Option 2 (User PATH)
