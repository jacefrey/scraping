"""Pytest config — adds the skill root to sys.path so `from webpage_to_md import ...` works."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
