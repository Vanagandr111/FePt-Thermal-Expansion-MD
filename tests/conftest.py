"""Pytest bootstrap: make gui/ and scripts/ importable as top-level."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, 'gui'), os.path.join(ROOT, 'scripts'), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
