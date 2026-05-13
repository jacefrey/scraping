"""Exception class tests (spec §8.4)."""
from webpage_to_pdf.errors import ConvertError


def test_convert_error_carries_message():
    err = ConvertError("boom")
    assert "boom" in str(err)


def test_convert_error_context():
    err = ConvertError("could not render", url="https://example.com/")
    assert err.context.get("url") == "https://example.com/"
