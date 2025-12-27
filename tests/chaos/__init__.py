"""
Chaos Testing Infrastructure

This package implements systematic fault injection to test system resilience.
Chaos tests simulate real-world failure scenarios to ensure the system
degrades gracefully and maintains data integrity under adverse conditions.

Chaos testing philosophy:
- Inject failures systematically, not randomly
- Test one failure mode at a time for clarity
- Verify invariants are maintained even under failure
- Ensure no data loss or corruption occurs
- Validate cleanup happens even when operations fail

Reference: docs/DEEP_ANALYSIS.md - Systematic Defensiveness
"""

from .fault_injectors import (
    DiskFullInjector,
    PermissionDeniedInjector,
    CorruptDataInjector,
    NetworkTimeoutInjector,
    ProcessHangInjector,
    MemoryLimitInjector,
)

__all__ = [
    'DiskFullInjector',
    'PermissionDeniedInjector',
    'CorruptDataInjector',
    'NetworkTimeoutInjector',
    'ProcessHangInjector',
    'MemoryLimitInjector',
]
