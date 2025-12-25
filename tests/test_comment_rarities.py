"""
Test script to preview all comment rarities and their visual effects.
Run this to see examples of each rarity tier with proper colors.
"""

import json
import sys
from pathlib import Path
from colorama import init, Fore, Style

# Initialize colorama for Windows color support
init()

def load_comments():
    """Load comments.json from config_files."""
    comments_file = Path(__file__).parent.parent / 'config_files' / 'comments.json'

    if not comments_file.exists():
        print(f"{Fore.RED}Error: comments.json not found at {comments_file}{Style.RESET_ALL}")
        return None

    with open(comments_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def display_rarity_stats(data):
    """Display rarity drop rates."""
    rarities = data.get('rarities', {})
    comments = data.get('comments', {})

    total_weight = sum(r.get('weight', 0) for r in rarities.values())

    print(f"\n{Style.BRIGHT}RARITY DROP RATES{Style.RESET_ALL}")
    print(f"{Style.DIM}{'─' * 60}{Style.RESET_ALL}\n")

    for rarity_name, config in rarities.items():
        weight = config.get('weight', 0)
        color = config.get('color', 'white')
        prefix = config.get('prefix', '')
        effect = config.get('effect', '')
        count = len(comments.get(rarity_name, []))
        drop_rate = (weight / total_weight) * 100

        # Get colorama color
        color_map = {
            'white': Fore.WHITE,
            'green': Fore.GREEN,
            'cyan': Fore.CYAN,
            'magenta': Fore.MAGENTA,
            'yellow': Fore.YELLOW,
            'red': Fore.RED,
            'blue': Fore.BLUE
        }
        fore_color = color_map.get(color, Fore.WHITE)

        # Display with color and effects
        style = Style.BRIGHT if effect == 'bold' else ''
        display_name = f"{prefix}{rarity_name.upper()}"

        print(f"  {fore_color}{style}{display_name:<20}{Style.RESET_ALL}  "
              f"{drop_rate:>5.1f}%  "
              f"{Style.DIM}({count} comments){Style.RESET_ALL}")

    print(f"\n{Style.DIM}Total comments: {sum(len(c) for c in comments.values())}{Style.RESET_ALL}\n")

def display_examples(data):
    """Display example comments from each rarity tier."""
    rarities = data.get('rarities', {})
    comments = data.get('comments', {})

    print(f"\n{Style.BRIGHT}RARITY EXAMPLES{Style.RESET_ALL}")
    print(f"{Style.DIM}{'─' * 60}{Style.RESET_ALL}\n")

    for rarity_name, config in rarities.items():
        color = config.get('color', 'white')
        prefix = config.get('prefix', '')
        effect = config.get('effect', '')
        comment_list = comments.get(rarity_name, [])

        if not comment_list:
            continue

        # Get colorama color
        color_map = {
            'white': Fore.WHITE,
            'green': Fore.GREEN,
            'cyan': Fore.CYAN,
            'magenta': Fore.MAGENTA,
            'yellow': Fore.YELLOW,
            'red': Fore.RED,
            'blue': Fore.BLUE
        }
        fore_color = color_map.get(color, Fore.WHITE)
        style = Style.BRIGHT if effect == 'bold' else ''

        # Show first 3 examples from this rarity
        print(f"{fore_color}{style}{prefix}{rarity_name.upper()}{Style.RESET_ALL}")
        for i, comment in enumerate(comment_list[:3], 1):
            display_comment = f"{prefix}{comment}"
            print(f"  {Style.DIM}│{Style.RESET_ALL} {fore_color}{style}{display_comment}{Style.RESET_ALL}")

        if len(comment_list) > 3:
            print(f"  {Style.DIM}... and {len(comment_list) - 3} more{Style.RESET_ALL}")
        print()

def display_full_preview(data):
    """Display in-game preview showing how comments appear during actual use."""
    rarities = data.get('rarities', {})
    comments = data.get('comments', {})

    print(f"\n{Style.BRIGHT}IN-GAME PREVIEW{Style.RESET_ALL}")
    print(f"{Style.DIM}{'─' * 60}{Style.RESET_ALL}\n")
    print(f"{Style.DIM}How comments appear during processing:{Style.RESET_ALL}\n")

    for rarity_name, config in rarities.items():
        color = config.get('color', 'white')
        prefix = config.get('prefix', '')
        effect = config.get('effect', '')
        comment_list = comments.get(rarity_name, [])

        if not comment_list:
            continue

        # Get colorama color
        color_map = {
            'white': Fore.WHITE,
            'green': Fore.GREEN,
            'cyan': Fore.CYAN,
            'magenta': Fore.MAGENTA,
            'yellow': Fore.YELLOW,
            'red': Fore.RED,
            'blue': Fore.BLUE
        }
        fore_color = color_map.get(color, Fore.WHITE)
        style = Style.BRIGHT if effect == 'bold' else ''

        # Show example in context
        example_comment = comment_list[0]
        display_comment = f"{prefix}{example_comment}"

        print(f"  {Style.DIM}>{Style.RESET_ALL} [foldername] video.mkv")
        print(f"  {Style.DIM}│{Style.RESET_ALL} {fore_color}{style}{display_comment}{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}⠸{Style.RESET_ALL} {Style.DIM}validating{Style.RESET_ALL}\n")

def main():
    """Main test function."""
    print(f"\n{Style.BRIGHT}{Fore.CYAN}Unpackr Comment Rarity System Test{Style.RESET_ALL}\n")

    data = load_comments()
    if not data:
        return

    # Check format
    if not isinstance(data.get('comments'), dict):
        print(f"{Fore.RED}Error: comments.json is using old format (flat list).{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Please update to the new rarity-based format.{Style.RESET_ALL}")
        return

    display_rarity_stats(data)
    display_examples(data)
    display_full_preview(data)

    print(f"{Fore.GREEN}Test complete!{Style.RESET_ALL}\n")
    print(f"{Style.DIM}Rarity weights:{Style.RESET_ALL}")
    print(f"{Style.DIM}  Common: 60% | Uncommon: 25% | Rare: 10% | Epic: 4% | Legendary: 1%{Style.RESET_ALL}\n")

if __name__ == '__main__':
    main()
