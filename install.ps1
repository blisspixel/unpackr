# Unpackr Installation Script
# Automates the setup process for Unpackr

param(
    [switch]$Admin,
    [switch]$UserPath,
    [switch]$Profile,
    [switch]$Help
)

# Colors for output
$Green = "Green"
$Red = "Red"
$Yellow = "Yellow"
$Cyan = "Cyan"

function Show-Help {
    Write-Host @"
Unpackr Installation Script

USAGE:
    .\install.ps1 [options]

OPTIONS:
    -Admin      Install to System32 (requires admin rights)
    -UserPath   Add to user PATH (recommended, no admin needed)
    -Profile    Create PowerShell function in profile
    -Help       Show this help

EXAMPLES:
    .\install.ps1 -UserPath     # Recommended method
    .\install.ps1 -Admin        # System-wide install
    .\install.ps1 -Profile      # PowerShell function only

If no options specified, will prompt for choice.
"@ -ForegroundColor $Cyan
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-Dependencies {
    Write-Host "📦 Installing Python dependencies..." -ForegroundColor $Yellow
    
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Host "❌ Python not found! Please install Python first." -ForegroundColor $Red
        Write-Host "   Download from: https://python.org/downloads" -ForegroundColor $Cyan
        return $false
    }
    
    try {
        python -m pip install -r requirements.txt
        Write-Host "✅ Dependencies installed successfully!" -ForegroundColor $Green
        return $true
    }
    catch {
        Write-Host "❌ Failed to install dependencies: $($_.Exception.Message)" -ForegroundColor $Red
        return $false
    }
}

function Install-ToSystem32 {
    Write-Host "🔧 Installing to System32..." -ForegroundColor $Yellow
    
    if (-not (Test-Administrator)) {
        Write-Host "❌ Administrator rights required for System32 installation." -ForegroundColor $Red
        Write-Host "   Run PowerShell as Administrator or use -UserPath option." -ForegroundColor $Cyan
        return $false
    }
    
    try {
        Copy-Item "unpackr.bat" "C:\Windows\System32\" -Force
        Write-Host "✅ Installed to C:\Windows\System32\unpackr.bat" -ForegroundColor $Green
        return $true
    }
    catch {
        Write-Host "❌ Failed to copy to System32: $($_.Exception.Message)" -ForegroundColor $Red
        return $false
    }
}

function Install-ToUserPath {
    Write-Host "🔧 Adding to user PATH..." -ForegroundColor $Yellow
    
    try {
        $currentPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
        $unpackrPath = $PWD.Path
        
        # Check if already in PATH
        if ($currentPath -split ';' -contains $unpackrPath) {
            Write-Host "ℹ️  Already in PATH: $unpackrPath" -ForegroundColor $Yellow
            return $true
        }
        
        # Add to PATH
        $newPath = if ($currentPath) { "$currentPath;$unpackrPath" } else { $unpackrPath }
        [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
        
        Write-Host "✅ Added to user PATH: $unpackrPath" -ForegroundColor $Green
        Write-Host "ℹ️  Restart your terminal to use 'unpackr' command" -ForegroundColor $Cyan
        return $true
    }
    catch {
        Write-Host "❌ Failed to add to PATH: $($_.Exception.Message)" -ForegroundColor $Red
        return $false
    }
}

function Install-PowerShellProfile {
    Write-Host "🔧 Creating PowerShell function..." -ForegroundColor $Yellow
    
    try {
        $profilePath = $PROFILE
        $unpackrPath = Join-Path $PWD.Path "unpackr.py"
        $functionCode = "function unpackr { python `"$unpackrPath`" @args }"
        
        # Create profile directory if it doesn't exist
        $profileDir = Split-Path $profilePath -Parent
        if (-not (Test-Path $profileDir)) {
            New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
        }
        
        # Check if function already exists
        if (Test-Path $profilePath) {
            $profileContent = Get-Content $profilePath -Raw
            if ($profileContent -match "function unpackr") {
                Write-Host "ℹ️  PowerShell function already exists in profile" -ForegroundColor $Yellow
                return $true
            }
        }
        
        # Add function to profile
        Add-Content $profilePath $functionCode
        Write-Host "✅ Added PowerShell function to profile: $profilePath" -ForegroundColor $Green
        Write-Host "ℹ️  Run '. `$PROFILE' to reload, or restart PowerShell" -ForegroundColor $Cyan
        return $true
    }
    catch {
        Write-Host "❌ Failed to create PowerShell function: $($_.Exception.Message)" -ForegroundColor $Red
        return $false
    }
}

function Test-Installation {
    Write-Host "🧪 Testing installation..." -ForegroundColor $Yellow
    
    # Test if unpackr.bat exists
    if (-not (Test-Path "unpackr.bat")) {
        Write-Host "❌ unpackr.bat not found in current directory" -ForegroundColor $Red
        return $false
    }
    
    # Test if unpackr.py exists
    if (-not (Test-Path "unpackr.py")) {
        Write-Host "❌ unpackr.py not found in current directory" -ForegroundColor $Red
        return $false
    }
    
    Write-Host "✅ All files found!" -ForegroundColor $Green
    return $true
}

function Show-Menu {
    Write-Host @"
🚀 Unpackr Installation Options

1. User PATH (Recommended) - No admin needed
2. System32 - Requires admin rights
3. PowerShell Function - Profile-based
4. All methods
5. Exit

"@ -ForegroundColor $Cyan
    
    do {
        $choice = Read-Host "Choose installation method (1-5)"
        switch ($choice) {
            "1" { return "UserPath" }
            "2" { return "Admin" }
            "3" { return "Profile" }
            "4" { return "All" }
            "5" { return "Exit" }
            default { Write-Host "Invalid choice. Please enter 1-5." -ForegroundColor $Red }
        }
    } while ($true)
}

# Main execution
Clear-Host
Write-Host @"
╔══════════════════════════════════════════╗
║           🚀 UNPACKR INSTALLER           ║
║      Your Digital Declutterer Setup      ║
╚══════════════════════════════════════════╝

"@ -ForegroundColor $Cyan

# Show help if requested
if ($Help) {
    Show-Help
    exit 0
}

# Test basic requirements
if (-not (Test-Installation)) {
    Write-Host "❌ Installation failed - missing files" -ForegroundColor $Red
    exit 1
}

# Install dependencies first
if (-not (Install-Dependencies)) {
    Write-Host "⚠️  Continuing without dependencies..." -ForegroundColor $Yellow
}

# Determine installation method
$method = $null
if ($Admin) { $method = "Admin" }
elseif ($UserPath) { $method = "UserPath" }
elseif ($Profile) { $method = "Profile" }
else { $method = Show-Menu }

if ($method -eq "Exit") {
    Write-Host "👋 Installation cancelled" -ForegroundColor $Yellow
    exit 0
}

# Execute installation
$success = $false
switch ($method) {
    "Admin" {
        $success = Install-ToSystem32
    }
    "UserPath" {
        $success = Install-ToUserPath
    }
    "Profile" {
        $success = Install-PowerShellProfile
    }
    "All" {
        Write-Host "🔄 Installing using all methods..." -ForegroundColor $Cyan
        $success1 = Install-ToUserPath
        $success2 = Install-PowerShellProfile
        if (Test-Administrator) {
            $success3 = Install-ToSystem32
            $success = $success1 -or $success2 -or $success3
        } else {
            Write-Host "ℹ️  Skipping System32 (no admin rights)" -ForegroundColor $Yellow
            $success = $success1 -or $success2
        }
    }
}

# Final status
Write-Host ""
if ($success) {
    Write-Host @"
✅ Installation completed successfully!

🎯 NEXT STEPS:
   1. Restart your terminal/PowerShell
   2. Configure tools: python configure_tools.py
   3. Test with: unpackr --help  
   4. Run: unpackr --source C:\Downloads --destination D:\Videos

📚 DOCUMENTATION:
   - README.md - Full documentation
   - INSTALL.md - Detailed install guide  
   - docs/ - Additional guides

🆘 SUPPORT:
   - Check logs/ for error details
   - Run tests: python tests/test_comprehensive.py

"@ -ForegroundColor $Green
} else {
    Write-Host @"
❌ Installation failed!

🔧 TROUBLESHOOTING:
   - Try running as Administrator
   - Check Python is installed and in PATH  
   - Verify file permissions
   - See INSTALL.md for manual setup

"@ -ForegroundColor $Red
    exit 1
}