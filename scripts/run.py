#!/usr/bin/env python3
"""Shim so the skill can be run from any working directory without installing."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_tax.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
