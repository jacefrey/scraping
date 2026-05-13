"""Stem-naming tests (spec §5.8 — re-implemented locally per §8.1 rules)."""
from webpage_to_pdf.naming import derive_stem


def test_basic_url():
    stem = derive_stem("https://example.com/blog/post-title")
    parts = stem.split("__")
    assert parts[0] == "example-com"
    assert parts[1] == "blog-post-title"
    assert len(parts[2]) == 8


def test_query_changes_hash():
    a = derive_stem("https://example.com/article")
    b = derive_stem("https://example.com/article?utm=foo")
    assert a != b


def test_root_path():
    stem = derive_stem("https://example.com/")
    assert stem.split("__")[1] == "root"
