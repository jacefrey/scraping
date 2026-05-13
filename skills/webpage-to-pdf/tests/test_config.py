"""Config loader tests (spec §6.7, §8.3)."""
import textwrap
from pathlib import Path
import pytest
from webpage_to_pdf.config import load_config, fingerprint


def test_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = load_config()
    r = cfg["render"]
    assert r["page_format"] == "continuous"
    assert r["render_mode"] == "live"
    assert r["margin_in"] == 0.3
    assert r["flatten_sticky"] == "auto"
    assert r["hide_fixed"] is False
    assert r["inject_page_break_avoid"] == "auto"
    assert r["persist_rendered_html"] is True
    assert r["strip_selectors"] == []
    assert cfg["render"]["viewport"]["width_px"] == 1280
    assert cfg["render"]["viewport"]["height_px"] == 800
    assert cfg["render"]["wait"]["strategy"] == "networkidle"
    assert cfg["render"]["wait"]["timeout_s"] == 10
    assert cfg["render"]["lazy_load"]["scroll_pause_ms"] == 800
    assert cfg["render"]["lazy_load"]["max_scroll_steps"] == 50
    assert cfg["render"]["lazy_load"]["max_scroll_seconds"] == 30
    assert cfg["render"]["lazy_load"]["layout_settle_ms"] == 250


def test_cwd_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "webpage-to-pdf.toml").write_text(textwrap.dedent("""
        [render]
        page_format = "Letter"
        render_mode = "captured_html"
    """))
    cfg = load_config()
    assert cfg["render"]["page_format"] == "Letter"
    assert cfg["render"]["render_mode"] == "captured_html"


def test_explicit_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    p = tmp_path / "explicit.toml"
    p.write_text("[render]\nmargin_in = 0.5\n")
    cfg = load_config(toml_path=p)
    assert cfg["render"]["margin_in"] == 0.5


def test_fingerprint_stable():
    fp = fingerprint(load_config())
    assert len(fp) == 64


def test_fingerprint_changes_on_render_mode_change(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    base = fingerprint(load_config())
    (tmp_path / "webpage-to-pdf.toml").write_text("[render]\nrender_mode = 'captured_html'\n")
    changed = fingerprint(load_config())
    assert base != changed
