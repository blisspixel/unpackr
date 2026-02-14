"""
Quick test script for path handling in Unpackr.
Tests that paths work with or without quotes.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from unpackr import clean_path

def test_clean_path():
    """Test path cleaning function."""
    
    test_cases = [
        # (input, expected)
        ('G:\\Test', 'G:\\Test'),
        ('"G:\\Test"', 'G:\\Test'),
        ("'G:\\Test'", 'G:\\Test'),
        ('  G:\\Test  ', 'G:\\Test'),
        ('"G:\\Test Path"', 'G:\\Test Path'),
        ('G:\\Test Path', 'G:\\Test Path'),
        ('"G:\\Test Path With Spaces"', 'G:\\Test Path With Spaces'),
    ]
    
    print("Testing path cleaning:")
    all_passed = True
    
    for input_path, expected in test_cases:
        result = clean_path(input_path)
        passed = result == expected
        status = "PASS" if passed else "FAIL"
        
        if not passed:
            all_passed = False
            
        print(f"  [{status}] Input: {input_path!r:40} -> Result: {result!r:30} (Expected: {expected!r})")
    
    print()
    if all_passed:
        print("All tests passed!")
    else:
        print("Some tests failed!")
    
    if __name__ == '__main__':
        return all_passed
    assert all_passed

if __name__ == '__main__':
    success = test_clean_path()
    sys.exit(0 if success else 1)
