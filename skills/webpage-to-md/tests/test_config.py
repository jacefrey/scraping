"""Config loader tests — precedence + defaults + fingerprint (spec §5.10, §8.3)."""
import textwrap
from pathlib import Path
import pytest
from webpage_to_md.config import load_config, fingerprint


def test_defaults_when_no_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = load_config()
    assert cfg["convert"]["emit_frontmatter"] is True
    assert cfg["convert"]["default_selector"] == ""
    assert cfg["convert"]["extraction"]["strategy"] == "selector_then_body"
    assert cfg["convert"]["html_to_md"]["heading_style"] == "ATX"
    assert "ad" in cfg["convert"]["html_to_md"]["strip_classes"]
    assert cfg["convert"]["html_to_md"]["strip_selectors"] == []
    assert cfg["convert"]["html_to_md"]["preserve_classes"] == []


def test_cwd_overrides_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "webpage-to-md.toml").write_text(textwrap.dedent("""
        [convert]
        emit_frontmatter = false
    """))
    cfg = load_config()
    assert cfg["convert"]["emit_frontmatter"] is False
    assert cfg["convert"]["extraction"]["strategy"] == "selector_then_body"


def test_explicit_path_overrides_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "webpage-to-md.toml").write_text(
        "[convert]\ndefault_selector = 'cwd'\n"
    )
    explicit = tmp_path / "explicit.toml"
    explicit.write_text("[convert]\ndefault_selector = 'explicit'\n")
    cfg = load_config(toml_path=explicit)
    assert cfg["convert"]["default_selector"] == "explicit"


def test_fingerprint_is_stable_64_hex():
    fp = fingerprint(load_config())
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_changes_when_config_changes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    base = load_config()
    (tmp_path / "webpage-to-md.toml").write_text(
        "[convert.html_to_md]\nheading_style = 'SETEXT'\n"
    )
    changed = load_config()
    assert fingerprint(base) != fingerprint(changed)
