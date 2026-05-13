"""Source detection + PDF-magic check (spec §6.2, §5.3)."""
from pathlib import Path
import pytest
from webpage_to_pdf.routing import (
    resolve_source, SourceKind, looks_like_pdf,
)


FIX = Path(__file__).parent / "fixtures"


def test_https_routes_to_url():
    kind, value = resolve_source("https://example.com/x")
    assert kind == SourceKind.URL
    assert value == "https://example.com/x"


def test_path_routes_to_local(tmp_path):
    p = tmp_path / "x.html"
    p.write_text("<html></html>")
    kind, value = resolve_source(p)
    assert kind == SourceKind.LOCAL
    assert value == p.resolve()


def test_file_url_routes_to_local(tmp_path):
    p = tmp_path / "x.html"
    p.write_text("<html></html>")
    kind, value = resolve_source(f"file://{p}")
    assert kind == SourceKind.LOCAL
    assert value == p.resolve()


def test_looks_like_pdf_by_magic_bytes():
    assert looks_like_pdf(FIX / "sample.pdf") is True


def test_looks_like_pdf_false_for_html(tmp_path):
    p = tmp_path / "x.html"
    p.write_bytes(b"<!DOCTYPE html><html></html>")
    assert looks_like_pdf(p) is False


def test_looks_like_pdf_by_suffix_even_if_unreadable(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"")
    assert looks_like_pdf(p) is True
