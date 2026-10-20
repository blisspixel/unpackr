"""Fail when a JUnit report ran nothing, or skipped a required tool.

The Windows real-tool job sets UNPACKR_REQUIRE_REAL_TOOLS=1. A skip whose
reason is a missing 7-Zip, PAR2, or ffmpeg is a failed gate. A skip for
another platform (freedesktop trash, a Linux-only PATH trick) is not.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET

# "needs 7-Zip and ffmpeg", "par2 not available on PATH". Not "hides par2 by narrowing PATH".
_TOOL_SKIP = re.compile(r"needs .*(?:7-Zip|\b7z\b|ffmpeg|par2)|not available on PATH", re.IGNORECASE)


def skip_message(skipped: ET.Element) -> str:
    """The reason pytest wrote on a ``<skipped>`` element."""
    return skipped.get("message") or (skipped.text or "")


def is_required_tool_skip(message: str) -> bool:
    """True when the skip means a required external tool was missing."""
    return _TOOL_SKIP.search(message) is not None


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    if not suites and root.tag == "testsuite":
        suites = [root]
    tests = sum(int(suite.get("tests") or 0) for suite in suites)
    tool_skips = []
    other_skips = 0
    for case in root.iter("testcase"):
        skipped = case.find("skipped")
        if skipped is None:
            continue
        message = skip_message(skipped)
        if is_required_tool_skip(message):
            tool_skips.append(f"{case.get('name') or '?'}: {message}")
        else:
            other_skips += 1
    if tests < 1:
        print(f"{path}: no tests were collected")
        return 1
    if tool_skips:
        print(f"{path}: a required tool was missing, so these tests did not run:")
        for line in tool_skips:
            print(f"  {line}")
        return 1
    print(f"{path}: {tests} tests collected, no required-tool skips ({other_skips} other skips)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: assert_junit_executed.py REPORT.xml", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
