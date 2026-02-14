"""
Test to debug why comments aren't showing in real processing.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unpackr import UnpackrApp
from core import Config

def test_comment_display():
    """Test comment display as it would happen during processing."""

    # Create unpackr instance
    config = Config()
    unpackr = UnpackrApp(config)

    print("\n" + "="*60)
    print("Testing comment display during simulated processing")
    print("="*60)

    # Check if comments loaded
    print(f"\nComments loaded: {unpackr.comments is not None}")
    print(f"Comments type: {type(unpackr.comments)}")
    if isinstance(unpackr.comments, dict):
        print(f"Rarities: {list(unpackr.comments.get('rarities', {}).keys())}")
        print(f"Comment categories: {list(unpackr.comments.get('comments', {}).keys())}")

    print("\nInitial state:")
    print(f"  last_comment_folder: {unpackr.last_comment_folder}")
    print(f"  current_comment_display: {unpackr.current_comment_display}")

    # Simulate processing folders 1-50
    print("\nSimulating folder processing:")
    print("-" * 60)

    for folder_num in [1, 2, 11, 21, 31, 41, 45]:
        comment = unpackr._get_random_comment(folder_num)
        if comment:
            print(f"Folder {folder_num:3d}: COMMENT - {comment[0][:50]}...")
        else:
            print(f"Folder {folder_num:3d}: No comment")

        # Show internal state
        print(f"              last_comment_folder={unpackr.last_comment_folder}, "
              f"current_comment_display={'SET' if unpackr.current_comment_display else 'None'}")

    print("\n" + "="*60)

if __name__ == '__main__':
    test_comment_display()
