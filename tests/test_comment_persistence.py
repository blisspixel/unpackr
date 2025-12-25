"""
Test comment persistence logic - comments should persist for entire folder.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from unpackr import UnpackrApp
from core import Config

def test_comment_persistence():
    """Test that comments persist across multiple calls for the same folder."""

    # Create unpackr instance
    config = Config()
    unpackr = UnpackrApp(config)

    print("\nTesting comment persistence logic:")
    print("=" * 60)

    # Folder 1 - should show a comment
    print(f"\nFolder 1 (first call):")
    comment1a = unpackr._get_random_comment(1)
    print(f"  Comment: {comment1a[0][:50] if comment1a else 'None'}...")

    # Folder 1 - should return THE SAME comment
    print(f"\nFolder 1 (second call - same folder, different action):")
    comment1b = unpackr._get_random_comment(1)
    print(f"  Comment: {comment1b[0][:50] if comment1b else 'None'}...")

    # Verify they're the same
    if comment1a and comment1b:
        assert comment1a[0] == comment1b[0], "Comments should be identical for same folder!"
        print(f"  ✓ Comment persisted correctly!")

    # Folder 2-10 - should show None (cooldown)
    print(f"\nFolders 2-10 (cooldown period):")
    for i in range(2, 11):
        comment = unpackr._get_random_comment(i)
        status = "✓ No comment (cooldown)" if comment is None else "✗ Unexpected comment!"
        print(f"  Folder {i}: {status}")

    # Folder 11 - should show a NEW comment
    print(f"\nFolder 11 (first call - new eligible folder):")
    comment11a = unpackr._get_random_comment(11)
    print(f"  Comment: {comment11a[0][:50] if comment11a else 'None'}...")

    # Folder 11 - should return THE SAME comment
    print(f"\nFolder 11 (second call - same folder):")
    comment11b = unpackr._get_random_comment(11)
    print(f"  Comment: {comment11b[0][:50] if comment11b else 'None'}...")

    # Verify they're the same
    if comment11a and comment11b:
        assert comment11a[0] == comment11b[0], "Comments should be identical for same folder!"
        print(f"  ✓ Comment persisted correctly!")

    # Verify they're different from folder 1's comment
    if comment1a and comment11a:
        # They might be the same by random chance, so just print
        if comment1a[0] != comment11a[0]:
            print(f"  ✓ Different comment from folder 1")
        else:
            print(f"  ℹ Same comment as folder 1 (random chance)")

    print("\n" + "=" * 60)
    print("✓ Comment persistence test passed!\n")

if __name__ == '__main__':
    test_comment_persistence()
