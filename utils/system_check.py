"""
System tools validation for Unpackr.
Checks availability of required external tools.
"""

import subprocess
import os
from typing import Dict
from colorama import Fore, Style


class SystemCheck:
    """Validates system requirements and external tools."""
    
    REQUIRED_TOOLS = {
        '7z': {
            'name': '7-Zip',
            'command': ['7z'],
            'critical': True,
            'purpose': 'RAR extraction'
        },
        'par2': {
            'name': 'par2cmdline',
            'command': ['par2'],
            'critical': False,
            'purpose': 'PAR2 repair'
        },
        'ffmpeg': {
            'name': 'FFmpeg',
            'command': ['ffmpeg', '-version'],
            'critical': False,
            'purpose': 'video health checks'
        }
    }
    
    def __init__(self, config=None):
        """Initialize SystemCheck with optional config containing tool paths."""
        self.config = config or {}
    
    def check_tool(self, tool_key: str) -> bool:
        """
        Check if a specific tool is available.
        
        Args:
            tool_key: Key from REQUIRED_TOOLS dict
            
        Returns:
            True if tool is available, False otherwise
        """
        tool_info = self.REQUIRED_TOOLS.get(tool_key)
        if not tool_info:
            return False
        
        # Get tool path from config if available
        tool_paths = self.config.get('tool_paths', {})
        custom_paths = tool_paths.get(tool_key)
        
        # Convert single path to list for uniform handling
        if isinstance(custom_paths, str):
            custom_paths = [custom_paths]
        elif custom_paths is None:
            custom_paths = []
        
        # Add default command as fallback
        if not custom_paths:
            custom_paths = [tool_info['command'][0]]
        
        # Try each path until one works
        for custom_path in custom_paths:
            try:
                if os.path.isfile(custom_path):
                    # Full path to executable
                    command = [custom_path]
                    if tool_key == 'ffmpeg':
                        command.append('-version')
                else:
                    # Command name (still try it)
                    command = [custom_path]
                    if tool_key == 'ffmpeg':
                        command.append('-version')
                
                subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=2
                )
                # If we get here, it worked - store the working path
                self._working_paths = getattr(self, '_working_paths', {})
                self._working_paths[tool_key] = custom_path
                return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        return False
    
    def check_all_tools(self) -> Dict[str, bool]:
        """
        Check all required tools.
        
        Returns:
            Dictionary mapping tool keys to availability status
        """
        results = {}
        for tool_key in self.REQUIRED_TOOLS:
            results[tool_key] = self.check_tool(tool_key)
        return results
    
    def display_tool_status(self, tools_status: Dict[str, bool]) -> bool:
        """
        Display status of all tools and check if we can proceed.
        
        Args:
            tools_status: Dictionary from check_all_tools()
            
        Returns:
            True if we can proceed, False if critical tools missing
        """
        can_proceed = True
        status_parts = []
        
        for tool_key, is_available in tools_status.items():
            tool_info = self.REQUIRED_TOOLS[tool_key]
            
            if is_available:
                status_parts.append(f"{Fore.GREEN}{tool_info['name']}: OK{Style.RESET_ALL}")
            else:
                if tool_info['critical']:
                    status_parts.append(f"{Fore.RED}{tool_info['name']}: MISSING{Style.RESET_ALL}")
                    can_proceed = False
                else:
                    status_parts.append(f"{Fore.YELLOW}{tool_info['name']}: SKIP{Style.RESET_ALL}")
        
        print(" | ".join(status_parts))
        
        if not can_proceed:
            print(Fore.RED + "ERROR: Critical tools missing! Cannot continue." + Style.RESET_ALL)
            print(f"{Fore.YELLOW}TIP: Edit config_files/config.json and set correct paths in 'tool_paths' section{Style.RESET_ALL}")
        
        return can_proceed
    
    def get_tool_command(self, tool_key: str) -> list:
        """
        Get the command to run for a specific tool.
        
        Args:
            tool_key: Key from REQUIRED_TOOLS dict
            
        Returns:
            List of command parts to execute
        """
        tool_info = self.REQUIRED_TOOLS.get(tool_key)
        if not tool_info:
            return []
        
        # Use working path if we found one during check
        working_paths = getattr(self, '_working_paths', {})
        if tool_key in working_paths:
            return [working_paths[tool_key]]
        
        # Get tool path from config if available
        tool_paths = self.config.get('tool_paths', {})
        custom_paths = tool_paths.get(tool_key)
        
        # Convert single path to list for uniform handling
        if isinstance(custom_paths, str):
            custom_paths = [custom_paths]
        elif custom_paths is None:
            custom_paths = []
        
        # Try first available path, or fall back to default
        if custom_paths:
            return [custom_paths[0]]
        else:
            # Use default command (first part only, no arguments)
            return [tool_info['command'][0]]
