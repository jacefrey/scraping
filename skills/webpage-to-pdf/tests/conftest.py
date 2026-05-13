# tests/conftest.py
"""Pytest config — adds the skill root to sys.path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
