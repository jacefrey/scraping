"""Stem-naming policy tests (spec §5.8)."""
from webpage_to_md.naming import derive_stem


def test_basic_url():
    stem = derive_stem("https://example.com/blog/post-title")
    parts = stem.split("__")
    assert parts[0] == "example-com"
    assert parts[1] == "blog-post-title"
    assert len(parts[2]) == 8
    assert all(c in "0123456789abcdef" for c in parts[2])


def test_query_string_affects_hash_not_path():
    a = derive_stem("https://example.com/article")
    b = derive_stem("https://example.com/article?utm=foo")
    a_parts = a.split("__")
    b_parts = b.split("__")
    assert a_parts[0] == b_parts[0]
    assert a_parts[1] == b_parts[1]
    assert a_parts[2] != b_parts[2]  # hash differs


def test_same_path_different_domains_distinct():
    a = derive_stem("https://example.com/blog/post-title")
    b = derive_stem("https://other.com/blog/post-title")
    assert a.split("__")[2] != b.split("__")[2]


def test_root_path_does_not_double_separator():
    stem = derive_stem("https://example.com/")
    parts = stem.split("__")
    assert parts[0] == "example-com"
    # Path slug for "/" should be a sentinel like "root" or empty-but-clean
    assert parts[1] in ("root", "index", "")
    # If empty, the joined stem should not start with __ at position 0
    assert not stem.startswith("__")


def test_unicode_path_slugified():
    stem = derive_stem("https://example.com/Über/München")
    parts = stem.split("__")
    # Non-word characters become hyphens
    assert parts[0] == "example-com"
    assert "-" in parts[1]


def test_deterministic():
    a = derive_stem("https://example.com/x/y/z?a=1&b=2")
    b = derive_stem("https://example.com/x/y/z?a=1&b=2")
    assert a == b
