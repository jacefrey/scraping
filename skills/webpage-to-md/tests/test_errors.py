"""Exception class tests (spec §5.6, §8.4)."""
import pytest
from webpage_to_md.errors import ConvertError, ConvertConfigError


def test_convert_error_carries_message():
    err = ConvertError("boom")
    assert "boom" in str(err)


def test_convert_config_error_is_convert_error():
    err = ConvertConfigError("bad config: foo")
    assert isinstance(err, ConvertError)
    assert "bad config" in str(err)


def test_convert_config_error_is_not_not_implemented():
    """Spec §5.6: readability hook raises ConvertConfigError, NOT NotImplementedError."""
    err = ConvertConfigError("readability strategy requires Readify; not yet shipped")
    assert not isinstance(err, NotImplementedError)


def test_convert_error_optional_context():
    err = ConvertError("could not convert", url="https://example.com/x")
    assert err.context.get("url") == "https://example.com/x"

from pathlib import Path
from webpage_to_md.result import ConvertResult


def test_convert_result_html_case():
    r = ConvertResult(
        markdown_path=Path("/tmp/out/x.md"),
        source_path=Path("/tmp/out/x.html"),
        pdf_path=None,
        md_generated=True,
        content_type="text/html",
    )
    assert r.markdown_path == Path("/tmp/out/x.md")
    assert r.md_generated is True
    assert r.pdf_path is None


def test_convert_result_pdf_passthrough_v01():
    """Spec §5.9: in v0.1, PDF responses save <stem>.pdf and stop. No MD generated."""
    r = ConvertResult(
        markdown_path=None,
        source_path=None,
        pdf_path=Path("/tmp/out/x.pdf"),
        md_generated=False,
        content_type="application/pdf",
    )
    assert r.md_generated is False
    assert r.markdown_path is None
    assert r.pdf_path is not None
