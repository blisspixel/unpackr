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
    elif module_name.endswith("test_integration_real_usage"):
        from tests.test_integration_real_usage import IntegrationTestRunner

        test_runner = IntegrationTestRunner()
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


def bind_app_helpers(app):
    """Attach the real shared UnpackrApp helpers to a hand-built fake app.

    Tests that drive UnpackrApp methods with a SimpleNamespace only stub what they
    care about; the shared video/archive helpers and issue lists are filled in here.
    """
    import types

    import unpackr

    for name in (
        "_note",
        "_record",
        "_record_folder_removed",
        "_process_archives",
        "_handle_video",
        "finish_issues",
        "_prepare_removal",
        "removal_summary",
        "_release_files",
        "_screen_release",
        "_decide_release_samples",
        "_longer_than_sample_cap",
        "_release_name",
        "_plan_destination",
        "_move_subtitles",
    ):
        if not hasattr(app, name):
            setattr(app, name, types.MethodType(getattr(unpackr.UnpackrApp, name), app))
    for attr in ("run_errors", "run_warnings"):
        if not hasattr(app, attr):
            setattr(app, attr, [])
    if not hasattr(app, "dry_run_plan"):
        app.dry_run_plan = None
    vp = getattr(app, "video_processor", None)
    if vp is not None:
        if not hasattr(vp, "probe_duration"):
            vp.probe_duration = lambda *_a, **_k: None
        if not hasattr(vp, "classify_preview"):
            vp.classify_preview = lambda *_a, **_k: None
        if not hasattr(vp, "last_verdict"):
            vp.last_verdict = None
    ap = getattr(app, "archive_processor", None)
    if ap is not None:
        if not hasattr(ap, "last_outcomes"):
            ap.last_outcomes = []
        if not hasattr(ap, "describe_missing"):
            ap.describe_missing = lambda missing, limit=3: ", ".join(missing[:limit])
    fh = getattr(app, "file_handler", None)
    if fh is not None:
        if not hasattr(fh, "hold_paths"):
            fh.hold_paths = lambda *_a, **_k: None
        if not hasattr(fh, "wait_for_file_release"):
            fh.wait_for_file_release = lambda *_a, **_k: True
    return app
