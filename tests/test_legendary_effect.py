"""
Quick test to preview the legendary comment effect.
"""

import sys
import os

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        else:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        os.system('chcp 65001 >nul 2>&1')
    except Exception:
        pass

from colorama import init, Fore, Style

# Initialize colorama for Windows color support
init()

def show_effect_comparison():
    """Show all rarity effects side by side."""
    print(f"\n{Style.BRIGHT}RARITY VISUAL EFFECTS COMPARISON{Style.RESET_ALL}\n")

    sample_text = "This is a sample comment to show the effect"

    # Common (60%) - white dim
    print(f"COMMON (60%):    {Style.DIM}|{Style.RESET_ALL} {Fore.WHITE}{Style.DIM}{sample_text}{Style.RESET_ALL}")

    # Uncommon (25%) - green normal
    print(f"UNCOMMON (25%):  {Style.DIM}|{Style.RESET_ALL} {Fore.GREEN}{sample_text}{Style.RESET_ALL}")

    # Rare (10%) - cyan bright
    print(f"RARE (10%):      {Style.DIM}|{Style.RESET_ALL} {Fore.CYAN}{Style.BRIGHT}{sample_text}{Style.RESET_ALL}")

    # Epic (4%) - magenta bright
    print(f"EPIC (4%):       {Style.DIM}|{Style.RESET_ALL} {Fore.MAGENTA}{Style.BRIGHT}{sample_text}{Style.RESET_ALL}")

    # Legendary (1%) - ROCKETS + GOLD/YELLOW + BRIGHT
    print(f"LEGENDARY (1%):  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}🚀 {sample_text} 🚀{Style.RESET_ALL}")

    print(f"\n{Style.DIM}The legendary drop has rockets and gold/yellow bright text for maximum hype!{Style.RESET_ALL}\n")

if __name__ == '__main__':
    show_effect_comparison()
