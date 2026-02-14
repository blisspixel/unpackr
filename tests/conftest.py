"""
Pytest configuration and fixtures for Unpackr tests.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def runner(request: pytest.FixtureRequest):
    """Provide module-appropriate runner fixture for tests that use `runner`."""
    module_name = request.module.__name__

    if module_name.endswith("test_safety"):
        from tests.test_safety import SafetyTestRunner
        test_runner = SafetyTestRunner()
    elif module_name.endswith("test_defensive"):
        from tests.test_defensive import DefensiveTestRunner
        test_runner = DefensiveTestRunner()
    else:
        # Import here to avoid circular imports
        from tests.test_comprehensive import ComprehensiveRunner
        test_runner = ComprehensiveRunner()

    yield test_runner
    assert test_runner.failed == 0


@pytest.fixture
def safety_runner():
    """Provide SafetyTestRunner fixture for safety tests."""
    from tests.test_safety import SafetyTestRunner
    test_runner = SafetyTestRunner()
    yield test_runner
    assert test_runner.failed == 0


@pytest.fixture
def defensive_runner():
    """Provide DefensiveTestRunner fixture for defensive tests."""
    from tests.test_defensive import DefensiveTestRunner
    test_runner = DefensiveTestRunner()
    yield test_runner
    assert test_runner.failed == 0
