"""Entry point untuk ``python -m chemflow``."""

from __future__ import annotations

import sys

from chemflow.cli import main

if __name__ == "__main__":
    sys.exit(main())
