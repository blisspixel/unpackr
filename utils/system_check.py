"""
System tools validation for Unpackr.
Checks availability of required external tools.
"""

import subprocess
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
    
    @staticmethod
    def check_tool(tool_key: str) -> bool:
        """
        Check if a specific tool is available.
        
        Args:
            tool_key: Key from REQUIRED_TOOLS dict
            
        Returns:
            True if tool is available, False otherwise
        """
        tool_info = SystemCheck.REQUIRED_TOOLS.get(tool_key)
        if not tool_info:
            return False
        
        try:
            subprocess.run(
                tool_info['command'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @staticmethod
    def check_all_tools() -> Dict[str, bool]:
        """
        Check all required tools.
        
        Returns:
            Dictionary mapping tool keys to availability status
        """
        results = {}
        for tool_key in SystemCheck.REQUIRED_TOOLS:
            results[tool_key] = SystemCheck.check_tool(tool_key)
        return results
    
    @staticmethod
    def display_tool_status(tools_status: Dict[str, bool]) -> bool:
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
            tool_info = SystemCheck.REQUIRED_TOOLS[tool_key]
            
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
        
        return can_proceed
