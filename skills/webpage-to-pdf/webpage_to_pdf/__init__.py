"""webpage-to-pdf — URL→PDF via Playwright print-to-PDF. See SKILL.md."""
from webpage_to_pdf.errors import ConvertError
from webpage_to_pdf.result import ConvertResult

__version__ = "0.1.0"

from webpage_to_pdf.convert import convert  # noqa: E402

__all__ = ["convert", "ConvertResult", "ConvertError", "__version__"]
