"""Helper: import a sibling skill's package, with explicit invariant checks (spec §8.1)."""
import importlib
import sys
from pathlib import Path

# Layout invariant: this file MUST live at:
#   <skills-root>/webpage-to-md/webpage_to_md/skill_imports.py
# parents[2] must resolve to a directory named "skills".
_SKILLS_ROOT = Path(__file__).resolve().parents[2]
assert _SKILLS_ROOT.name == "skills", (
    f"skill_imports.py layout invariant violated: parents[2] resolved to "
    f"{_SKILLS_ROOT}, expected a directory named 'skills'."
)


def use(skill_name: str) -> None:
    """Add <skills-root>/<skill_name>/ to sys.path; assert the skill exists.

    Idempotent. Raises ImportError on missing skill.
    """
    skill_dir = _SKILLS_ROOT / skill_name
    if not skill_dir.is_dir():
        raise ImportError(
            f"Required skill '{skill_name}' not found at {skill_dir}. "
            f"Install the scraping plugin or symlink to ~/.claude/skills/{skill_name}/."
        )
    skill_dir_str = str(skill_dir)
    if skill_dir_str not in sys.path:
        sys.path.insert(0, skill_dir_str)


def validate_imported(module_name: str, expected_skill: str) -> None:
    """Assert an imported module came from the expected skill directory."""
    mod = importlib.import_module(module_name)
    if mod.__file__ is None:
        return
    expected_prefix = str(_SKILLS_ROOT / expected_skill)
    if not str(Path(mod.__file__).resolve()).startswith(expected_prefix):
        raise ImportError(
            f"Expected '{module_name}' to come from {expected_prefix}, but "
            f"resolved to {mod.__file__}."
        )
