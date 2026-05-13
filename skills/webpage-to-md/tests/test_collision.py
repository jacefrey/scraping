"""Filename collision regression (spec §5.8, §9.5)."""
from webpage_to_md.naming import derive_stem


def test_same_path_different_hosts_no_collision():
    a = derive_stem("https://example.com/blog/post-title")
    b = derive_stem("https://other.com/blog/post-title")
    assert a != b
    # And the domain portion is visibly different
    assert a.split("__")[0] != b.split("__")[0]


def test_same_path_with_and_without_query_no_collision():
    a = derive_stem("https://example.com/article")
    b = derive_stem("https://example.com/article?utm=foo")
    assert a != b


def test_about_page_collision_resolved_by_hash():
    """Real-world hot collision: every site has /about."""
    sites = [
        "https://example.com/about",
        "https://other.com/about",
        "https://third.com/about",
    ]
    stems = [derive_stem(u) for u in sites]
    assert len(set(stems)) == 3  # three different stems
