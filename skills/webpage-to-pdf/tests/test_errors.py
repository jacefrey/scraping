"""Exception class tests (spec §8.4)."""
from webpage_to_pdf.errors import ConvertError


def test_convert_error_carries_message():
    err = ConvertError("boom")
    assert "boom" in str(err)


def test_convert_error_context():
    err = ConvertError("could not render", url="https://example.com/")
    assert err.context.get("url") == "https://example.com/"

from pathlib import Path
from webpage_to_pdf.result import ConvertResult


def test_convert_result_live_mode():
    r = ConvertResult(
        pdf_path=Path("/tmp/x.pdf"),
        source_html_path=Path("/tmp/x.html"),
        rendered_html_path=Path("/tmp/x.rendered.html"),
        render_mode="live",
        live_double_fetch=True,
        passthrough=False,
    )
    assert r.render_mode == "live"
    assert r.live_double_fetch is True


def test_convert_result_passthrough():
    r = ConvertResult(
        pdf_path=Path("/tmp/x.pdf"),
        source_html_path=None,
        rendered_html_path=None,
        render_mode=None,
        live_double_fetch=None,
        passthrough=True,
    )
    assert r.passthrough is True
