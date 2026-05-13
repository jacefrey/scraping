"""webpage-to-md — URL→Markdown with persisted source HTML. See SKILL.md."""
from webpage_to_md.errors import ConvertError, ConvertConfigError
from webpage_to_md.result import ConvertResult

__version__ = "0.1.0"
__all__ = ["ConvertError", "ConvertConfigError", "ConvertResult", "__version__"]
