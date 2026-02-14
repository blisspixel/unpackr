"""
Pytest configuration and fixtures for Unpackr tests.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def runner():
    """Provide TestRunner fixture for tests that use it."""
    # Import here to avoid circular imports
    from tests.test_comprehensive import ComprehensiveRunner
    return ComprehensiveRunner()


@pytest.fixture
def safety_runner():
    """Provide SafetyTestRunner fixture for safety tests."""
    from tests.test_safety import SafetyTestRunner
    return SafetyTestRunner()


@pytest.fixture
def defensive_runner():
    """Provide DefensiveTestRunner fixture for defensive tests."""
    from tests.test_defensive import DefensiveTestRunner
    return DefensiveTestRunner()
