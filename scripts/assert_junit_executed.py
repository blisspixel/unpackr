"""Fail when a JUnit report has no tests or any skipped test.

The Windows real-tool job sets UNPACKR_REQUIRE_REAL_TOOLS=1. A skip there
means a required tool was missing, which is a failed gate, not an empty pass.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    if not suites and root.tag == "testsuite":
        suites = [root]
    tests = sum(int(suite.get("tests") or 0) for suite in suites)
    skipped_cases = [case.get("name") or "?" for case in root.iter("testcase") if case.find("skipped") is not None]
    if tests < 1:
        print(f"{path}: no tests were collected")
        return 1
    if skipped_cases:
        print(f"{path}: skipped tests are a failure on this gate:")
        for name in skipped_cases:
            print(f"  {name}")
        return 1
    print(f"{path}: {tests} tests executed, none skipped")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: assert_junit_executed.py REPORT.xml", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
