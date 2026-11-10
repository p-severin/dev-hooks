"""Print hook findings and return a process status."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def report(findings: Sequence[str]) -> int:
    if not findings:
        return 0
    print("\n\n".join(findings), file=sys.stderr)
    return 1
