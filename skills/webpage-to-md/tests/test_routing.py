"""Source-type detection (spec §5.3)."""
from pathlib import Path
import pytest
from webpage_to_md.routing import resolve_source, SourceKind


def test_https_url_routes_to_url(tmp_path):
    kind, value = resolve_source("https://example.com/article")
    assert kind == SourceKind.URL
    assert value == "https://example.com/article"


def test_http_url_routes_to_url():
    kind, value = resolve_source("http://example.com")
    assert kind == SourceKind.URL


def test_path_instance_routes_to_local(tmp_path):
    p = tmp_path / "saved.html"
    p.write_text("<html></html>")
    kind, value = resolve_source(p)
    assert kind == SourceKind.LOCAL
    assert value == p.resolve()


def test_file_url_routes_to_local(tmp_path):
    p = tmp_path / "saved.html"
    p.write_text("<html></html>")
    kind, value = resolve_source(f"file://{p}")
    assert kind == SourceKind.LOCAL
    assert value == p.resolve()


def test_bare_str_path_routes_to_local(tmp_path):
    p = tmp_path / "saved.html"
    p.write_text("<html></html>")
    kind, value = resolve_source(str(p))
    assert kind == SourceKind.LOCAL
    assert value == p.resolve()


def test_tilde_expansion(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "f.html").write_text("<html></html>")
    kind, value = resolve_source("~/f.html")
    assert kind == SourceKind.LOCAL
    assert value == (tmp_path / "f.html").resolve()
