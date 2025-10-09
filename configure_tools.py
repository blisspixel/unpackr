#!/usr/bin/env python3
"""
Tool Path Configurator for Unpackr.
Helps users set up tool paths in config.json
"""

import json
import os
import sys
from pathlib import Path
from colorama import Fore, Style, init

# Initialize colorama
init()

def find_7zip_paths():
    """Find potential 7-Zip installation paths."""
    paths = [
        "C:\\Program Files\\7-Zip\\7z.exe",
        "C:\\Program Files (x86)\\7-Zip\\7z.exe",
        "7z.exe",  # If in PATH
        "7z"       # If in PATH (Unix style)
    ]
    
    found_paths = []
    for path in paths:
        if os.path.isfile(path):
            found_paths.append(path)
        elif path in ["7z.exe", "7z"]:
            # Check if it's in PATH
            try:
                import subprocess
                result = subprocess.run([path], capture_output=True, timeout=2)
                found_paths.append(path)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
    
    return found_paths

def find_par2_paths():
    """Find potential par2cmdline installation paths."""
    paths = [
        "par2.exe",
        "par2",
        "C:\\Program Files\\par2cmdline\\par2.exe",
        "C:\\Program Files (x86)\\par2cmdline\\par2.exe"
    ]
    
    found_paths = []
    for path in paths:
        if os.path.isfile(path):
            found_paths.append(path)
        elif path in ["par2.exe", "par2"]:
            # Check if it's in PATH
            try:
                import subprocess
                result = subprocess.run([path], capture_output=True, timeout=2)
                found_paths.append(path)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
    
    return found_paths

def find_ffmpeg_paths():
    """Find potential FFmpeg installation paths."""
    paths = [
        "ffmpeg.exe",
        "ffmpeg",
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe"
    ]
    
    found_paths = []
    for path in paths:
        if os.path.isfile(path):
            found_paths.append(path)
        elif path in ["ffmpeg.exe", "ffmpeg"]:
            # Check if it's in PATH
            try:
                import subprocess
                result = subprocess.run([path, "-version"], capture_output=True, timeout=2)
                if result.returncode == 0:
                    found_paths.append(path)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
    
    return found_paths

def load_config():
    """Load current configuration."""
    config_path = Path("config_files/config.json")
    if not config_path.exists():
        print(f"{Fore.RED}Error: config.json not found at {config_path}{Style.RESET_ALL}")
        return None
    
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"{Fore.RED}Error: Invalid JSON in config.json: {e}{Style.RESET_ALL}")
        return None

def save_config(config):
    """Save configuration to file."""
    config_path = Path("config_files/config.json")
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"{Fore.RED}Error saving config: {e}{Style.RESET_ALL}")
        return False

def test_tool(tool_path, tool_type):
    """Test if a tool works at the given path."""
    try:
        import subprocess
        if tool_type == "7z":
            result = subprocess.run([tool_path], capture_output=True, timeout=2)
        elif tool_type == "par2":
            result = subprocess.run([tool_path], capture_output=True, timeout=2)
        elif tool_type == "ffmpeg":
            result = subprocess.run([tool_path, "-version"], capture_output=True, timeout=2)
            return result.returncode == 0
        
        return True  # If no exception, tool exists
    except:
        return False

def configure_tool(tool_name, tool_key, config):
    """Configure a specific tool path."""
    print(f"\n{Fore.CYAN}=== Configuring {tool_name} ==={Style.RESET_ALL}")
    
    # Show current setting
    current_path = config.get('tool_paths', {}).get(tool_key, "Not set")
    print(f"Current path: {Fore.YELLOW}{current_path}{Style.RESET_ALL}")
    
    # Find potential paths
    if tool_key == "7z":
        found_paths = find_7zip_paths()
    elif tool_key == "par2":
        found_paths = find_par2_paths()
    elif tool_key == "ffmpeg":
        found_paths = find_ffmpeg_paths()
    else:
        found_paths = []
    
    if found_paths:
        print(f"\n{Fore.GREEN}Found potential installations:{Style.RESET_ALL}")
        for i, path in enumerate(found_paths, 1):
            working = "✓" if test_tool(path, tool_key) else "✗"
            print(f"  {i}. {path} {working}")
    else:
        print(f"{Fore.YELLOW}No automatic installations found{Style.RESET_ALL}")
    
    print(f"\nOptions:")
    if found_paths:
        print(f"  1-{len(found_paths)}. Use found installation")
    print(f"  c. Enter custom path")
    print(f"  s. Skip (keep current)")
    
    choice = input(f"\nEnter choice: ").strip().lower()
    
    if choice == 's':
        return config
    elif choice == 'c':
        custom_path = input(f"Enter full path to {tool_name}: ").strip()
        if custom_path:
            if 'tool_paths' not in config:
                config['tool_paths'] = {}
            config['tool_paths'][tool_key] = custom_path
            print(f"{Fore.GREEN}Set {tool_name} path to: {custom_path}{Style.RESET_ALL}")
    elif choice.isdigit():
        choice_num = int(choice)
        if 1 <= choice_num <= len(found_paths):
            selected_path = found_paths[choice_num - 1]
            if 'tool_paths' not in config:
                config['tool_paths'] = {}
            config['tool_paths'][tool_key] = selected_path
            print(f"{Fore.GREEN}Set {tool_name} path to: {selected_path}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Invalid choice{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Invalid choice{Style.RESET_ALL}")
    
    return config

def main():
    """Main configuration interface."""
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════╗
║         UNPACKR TOOL CONFIGURATOR        ║
║     Set paths to 7-Zip, par2, FFmpeg    ║
╚══════════════════════════════════════════╝{Style.RESET_ALL}
""")
    
    # Load current config
    config = load_config()
    if config is None:
        return 1
    
    print(f"This tool helps you configure paths to external tools that Unpackr needs.")
    print(f"You can use full paths to executables or just command names if they're in your PATH.")
    
    # Configure each tool
    tools = [
        ("7-Zip", "7z", True),
        ("par2cmdline", "par2", False),  
        ("FFmpeg", "ffmpeg", False)
    ]
    
    for tool_name, tool_key, required in tools:
        required_text = f" {Fore.RED}(REQUIRED){Style.RESET_ALL}" if required else f" {Fore.YELLOW}(Optional){Style.RESET_ALL}"
        print(f"\n{Fore.WHITE}{'='*50}{Style.RESET_ALL}")
        print(f"{tool_name}{required_text}")
        
        config = configure_tool(tool_name, tool_key, config)
    
    # Save configuration
    print(f"\n{Fore.WHITE}{'='*50}{Style.RESET_ALL}")
    print(f"Configuration complete!")
    
    if save_config(config):
        print(f"{Fore.GREEN}✓ Configuration saved successfully!{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}Next steps:{Style.RESET_ALL}")
        print(f"  1. Test your configuration: unpackr --help")
        print(f"  2. Run Unpackr: unpackr --source \"C:\\Downloads\" --destination \"D:\\Videos\"")
        return 0
    else:
        print(f"{Fore.RED}✗ Failed to save configuration{Style.RESET_ALL}")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Configuration cancelled{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}Unexpected error: {e}{Style.RESET_ALL}")
        sys.exit(1)