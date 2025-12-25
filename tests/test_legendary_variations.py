"""
Test different legendary effect variations to find the coolest one.
"""

import sys
import os
import time

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        else:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        os.system('chcp 65001 >nul 2>&1')
    except:
        pass

from colorama import init, Fore, Back, Style

# Initialize colorama for Windows color support
init()

def show_legendary_variations():
    """Show different legendary effect options."""
    print(f"\n{Style.BRIGHT}LEGENDARY EFFECT OPTIONS{Style.RESET_ALL}\n")

    sample_text = "Collective efficiency: your organization is impressive"

    print("Option 1 - Inverted (current):")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.BLACK}{Back.YELLOW}{Style.BRIGHT} {sample_text} {Style.RESET_ALL}")

    print("\nOption 2 - Double Border:")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}{'═' * 70}{Style.RESET_ALL}")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}║ {sample_text}{Style.RESET_ALL}")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}{'═' * 70}{Style.RESET_ALL}")

    print("\nOption 3 - Gradient-style (color cycling):")
    # Simulate gradient with multiple colors
    words = sample_text.split()
    colors = [Fore.YELLOW, Fore.WHITE, Fore.YELLOW, Fore.WHITE, Fore.YELLOW, Fore.WHITE, Fore.YELLOW]
    colored_words = [f"{colors[i % len(colors)]}{Style.BRIGHT}{word}" for i, word in enumerate(words)]
    print(f"  {Style.DIM}|{Style.RESET_ALL} {' '.join(colored_words)}{Style.RESET_ALL}")

    print("\nOption 4 - Mega Bright (multiple styles):")
    # Try stacking multiple bright effects
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}>>> {sample_text} <<<{Style.RESET_ALL}")

    print("\nOption 5 - Block with stars:")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.BLACK}{Back.YELLOW}{Style.BRIGHT} ★ {sample_text} ★ {Style.RESET_ALL}")

    print("\nOption 6 - Cyan on Black (reversed):")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.CYAN}{Back.BLACK}{Style.BRIGHT} {sample_text} {Style.RESET_ALL}")

    print("\nOption 7 - White on Magenta:")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.WHITE}{Back.MAGENTA}{Style.BRIGHT} {sample_text} {Style.RESET_ALL}")

    print("\nOption 8 - Double line with arrows:")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}>>> LEGENDARY DROP <<<{Style.RESET_ALL}")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}{sample_text}{Style.RESET_ALL}")

    print(f"\n{Style.DIM}Which effect looks coolest to you?{Style.RESET_ALL}\n")

if __name__ == '__main__':
    show_legendary_variations()
