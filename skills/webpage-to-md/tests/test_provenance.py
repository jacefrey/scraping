"""Frontmatter + sidecar tests (spec §5.3, §5.4, §8.5)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
from webpage_to_md.provenance import (
    build_frontmatter,
    write_meta_sidecar,
    read_meta_sidecar,
)


def _fake_result(**overrides):
    base = dict(
        requested_url="https://example.com/article",
        final_url="https://example.com/article",
        redirect_chain=["https://example.com/old"],
        started_at=datetime(2026, 5, 12, 10, 29, 59, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 12, 10, 30, 0, tzinfo=timezone.utc),
        content_type="text/html; charset=utf-8",
        content_type_source="get_header",
        http_status=200,
        fetch_method="http",
        content_hash_sha256="7e8b3f9c0d1e2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2",
        etag='"abc"',
        last_modified="Wed, 12 May 2026 10:30:00 GMT",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_frontmatter_round_trip():
    r = _fake_result()
    fm = build_frontmatter(
        result=r,
        source_artifact="example-com__article__a1b2c3d4.html",
        derived_artifact="example-com__article__a1b2c3d4.md",
        selector=None,
        extraction_strategy="selector_then_body",
        config_sha256="a" * 64,
        title="Article Title",
        canonical_url="https://example.com/article",
    )
    assert fm.startswith("---\n")
    assert fm.endswith("---\n")
    data = yaml.safe_load(fm.strip().strip("-").strip())
    assert data["url"] == "https://example.com/article"
    assert data["final_url"] == "https://example.com/article"
    assert data["canonical_url"] == "https://example.com/article"
    assert data["title"] == "Article Title"
    assert data["http_status"] == 200
    assert data["fetch_method"] == "http"
    assert data["source_artifact"] == "example-com__article__a1b2c3d4.html"
    assert data["derived_artifact"] == "example-com__article__a1b2c3d4.md"
    assert data["source_sha256"].startswith("7e8b3f")
    assert data["extraction_strategy"] == "selector_then_body"
    assert data["selector"] is None
    assert data["config_sha256"] == "a" * 64
    assert data["converter"] == "webpage-to-md"
    assert data["converter_version"] == "0.1.0"
    assert data["manifest_schema_version"] == "1.0"


def test_build_frontmatter_handles_title_with_special_chars():
    r = _fake_result()
    fm = build_frontmatter(
        result=r,
        source_artifact="x.html",
        derived_artifact="x.md",
        selector=None,
        extraction_strategy="selector_then_body",
        config_sha256="b" * 64,
        title='Title: with "quotes" and --- separator',
        canonical_url=None,
    )
    # PyYAML must escape these; round-trip recovers the string
    data = yaml.safe_load(fm.strip().strip("-").strip())
    assert data["title"] == 'Title: with "quotes" and --- separator'


def test_build_frontmatter_reconversion_fields():
    r = _fake_result()
    fm = build_frontmatter(
        result=r,
        source_artifact="x.html",
        derived_artifact="x.md",
        selector=None,
        extraction_strategy="selector_then_body",
        config_sha256="c" * 64,
        title="t",
        canonical_url=None,
        original_fetched_at=datetime(2026, 5, 12, 10, 30, 0, tzinfo=timezone.utc),
        re_converted_at=datetime(2026, 5, 12, 15, 0, 0, tzinfo=timezone.utc),
    )
    data = yaml.safe_load(fm.strip().strip("-").strip())
    assert data["original_fetched_at"] == "2026-05-12T10:30:00+00:00"
    assert data["re_converted_at"] == "2026-05-12T15:00:00+00:00"


def test_sidecar_round_trip(tmp_path):
    r = _fake_result()
    p = tmp_path / "x.html.meta.json"
    write_meta_sidecar(p, result=r, web_fetch_version="0.1.0")
    data = read_meta_sidecar(p)
    assert data["url"] == "https://example.com/article"
    assert data["final_url"] == "https://example.com/article"
    assert data["fetched_at"] == "2026-05-12T10:30:00+00:00"
    assert data["fetch_method"] == "http"
    assert data["http_status"] == 200
    assert data["content_type_source"] == "get_header"
    assert data["etag"] == '"abc"'
    assert data["last_modified"] == "Wed, 12 May 2026 10:30:00 GMT"
    assert data["redirect_chain"] == ["https://example.com/old"]
    assert data["source_sha256"].startswith("7e8b3f")
    assert data["web-fetch_version"] == "0.1.0"


def test_read_meta_sidecar_returns_none_when_absent(tmp_path):
    assert read_meta_sidecar(tmp_path / "missing.html.meta.json") is None
