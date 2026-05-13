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
