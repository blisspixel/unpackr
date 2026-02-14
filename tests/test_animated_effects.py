"""
Test animated effects for legendary drops.
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
    except Exception:
        pass

from colorama import init, Fore, Style

# Initialize colorama for Windows color support
init()

def demo_blinking_effect():
    """Demo 1: Blinking effect using ANSI escape codes."""
    print("\n1. BLINKING EFFECT (if terminal supports it):")
    # \033[5m is the blink code - not widely supported
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}\033[5m🚀 This text should blink 🚀\033[0m")
    time.sleep(2)

def demo_color_cycling():
    """Demo 2: Rapid color cycling to simulate animation."""
    print("\n2. COLOR CYCLING (simulated glow):")
    colors = [Fore.YELLOW, Fore.WHITE, Fore.YELLOW, Fore.WHITE]
    text = "🚀 Collective efficiency: your organization is impressive 🚀"

    for i in range(8):  # Show 8 frames
        sys.stdout.write(f"\r  {Style.DIM}|{Style.RESET_ALL} {colors[i % len(colors)]}{Style.BRIGHT}{text}")
        sys.stdout.flush()
        time.sleep(0.15)
    print()  # newline

def demo_expanding_effect():
    """Demo 3: Expanding brackets effect."""
    print("\n3. EXPANDING BRACKETS:")
    text = "Collective efficiency: your organization is impressive"

    frames = [
        f"🚀 {text} 🚀",
        f"🚀 ▸ {text} ◂ 🚀",
        f"🚀 » {text} « 🚀",
        f"🚀 ═ {text} ═ 🚀",
    ]

    for frame in frames:
        sys.stdout.write(f"\r  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}{frame}")
        sys.stdout.flush()
        time.sleep(0.2)
    print()  # newline

def demo_wave_effect():
    """Demo 4: Wave effect with different brightness."""
    print("\n4. WAVE EFFECT (brightness cycling):")
    text = "🚀 Collective efficiency: your organization is impressive 🚀"

    for i in range(6):
        if i % 2 == 0:
            sys.stdout.write(f"\r  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}{text}")
        else:
            sys.stdout.write(f"\r  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.NORMAL}{text}")
        sys.stdout.flush()
        time.sleep(0.2)
    print()  # newline

def demo_static_enhanced():
    """Demo 5: Static but with multiple visual enhancements."""
    print("\n5. STATIC ENHANCED (no animation):")
    text = "Collective efficiency: your organization is impressive"
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}{'═' * 75}")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}🚀 ▸▸▸ {text} ◂◂◂ 🚀")
    print(f"  {Style.DIM}|{Style.RESET_ALL} {Fore.YELLOW}{Style.BRIGHT}{'═' * 75}")

def main():
    print(f"\n{Style.BRIGHT}LEGENDARY ANIMATION TESTS{Style.RESET_ALL}")
    print(f"{Style.DIM}Note: Some effects require terminal support and may not work everywhere{Style.RESET_ALL}")

    demo_blinking_effect()
    demo_color_cycling()
    demo_expanding_effect()
    demo_wave_effect()
    demo_static_enhanced()

    print(f"\n{Style.DIM}Problem: Most animations would freeze the UI during processing.{Style.RESET_ALL}")
    print(f"{Style.DIM}Best option: Static effect with maximum visual impact (rockets, borders, etc.){Style.RESET_ALL}\n")

if __name__ == '__main__':
    main()
