"""webpage-to-md — URL→Markdown with persisted source HTML. See SKILL.md."""
from webpage_to_md.errors import ConvertError, ConvertConfigError
from webpage_to_md.result import ConvertResult

__version__ = "0.1.0"

# Imported AFTER __version__ so submodules can read it.
from webpage_to_md.convert import convert  # noqa: E402

__all__ = [
    "convert", "ConvertResult",
    "ConvertError", "ConvertConfigError",
    "__version__",
]
