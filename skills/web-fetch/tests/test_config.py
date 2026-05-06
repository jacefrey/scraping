"""Config loader tests — precedence + defaults (spec §4.4, §8.3)."""
import textwrap
from pathlib import Path
import pytest
from webfetch.config import load_config


def test_defaults_when_no_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))  # so ~/.config lookup misses
    cfg = load_config()
    assert cfg["fetch"]["http_timeout_s"] == 10
    assert cfg["fetch"]["network_retries"] == 3
    assert cfg["fetch"]["http_timeout_retries"] == 2
    assert cfg["fetch"]["use_head"] is True
    assert cfg["fetch"]["max_redirects"] == 20
    assert cfg["fetch"]["return_blocked_content"] is False
    assert cfg["fetch"]["magic_byte_peek_timeout_s"] == 5
    assert cfg["fetch"]["parse_safety"]["max_response_bytes"] == 50_000_000
    assert cfg["fetch"]["politeness"]["min_delay_ms_per_host"] == 500
    assert cfg["fetch"]["playwright"]["timeout_s"] == 30
    assert cfg["fetch"]["playwright"]["wait_for"] == "networkidle"
    assert cfg["fetch"]["detection"]["challenge_markers"] == []
    assert cfg["fetch"]["domain_overrides"] == []


def test_cwd_overrides_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "web-fetch.toml").write_text(textwrap.dedent("""
        [fetch]
        http_timeout_s = 99
    """))
    cfg = load_config()
    assert cfg["fetch"]["http_timeout_s"] == 99
    # other defaults still present
    assert cfg["fetch"]["network_retries"] == 3


def test_explicit_path_overrides_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "web-fetch.toml").write_text("[fetch]\nhttp_timeout_s = 1\n")
    explicit = tmp_path / "explicit.toml"
    explicit.write_text("[fetch]\nhttp_timeout_s = 7\n")
    cfg = load_config(toml_path=explicit)
    assert cfg["fetch"]["http_timeout_s"] == 7


def test_user_config_layer(tmp_path, monkeypatch):
    """The ~/.config/web-fetch.toml layer is loaded when present."""
    home = tmp_path / "home"
    user_cfg_dir = home / ".config"
    user_cfg_dir.mkdir(parents=True)
    (user_cfg_dir / "web-fetch.toml").write_text("[fetch]\nhttp_timeout_s = 42\n")
    monkeypatch.setenv("HOME", str(home))
    # CWD has no web-fetch.toml
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg["fetch"]["http_timeout_s"] == 42


def test_cwd_overrides_user_config(tmp_path, monkeypatch):
    """CWD config takes precedence over ~/.config."""
    home = tmp_path / "home"
    user_cfg_dir = home / ".config"
    user_cfg_dir.mkdir(parents=True)
    (user_cfg_dir / "web-fetch.toml").write_text("[fetch]\nhttp_timeout_s = 42\n")
    monkeypatch.setenv("HOME", str(home))
    cwd = tmp_path / "project"
    cwd.mkdir()
    (cwd / "web-fetch.toml").write_text("[fetch]\nhttp_timeout_s = 7\n")
    monkeypatch.chdir(cwd)
    cfg = load_config()
    assert cfg["fetch"]["http_timeout_s"] == 7  # CWD wins over ~/.config


def test_deep_nested_override(tmp_path, monkeypatch):
    """Sub-table overrides merge correctly via _deep_merge."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "web-fetch.toml").write_text(
        "[fetch.politeness]\nmin_delay_ms_per_host = 2000\n"
    )
    cfg = load_config()
    # Override applied:
    assert cfg["fetch"]["politeness"]["min_delay_ms_per_host"] == 2000
    # Sibling defaults preserved (deep-merge, not replace):
    assert cfg["fetch"]["politeness"]["respect_retry_after"] is True
    assert cfg["fetch"]["politeness"]["max_retry_after_s"] == 120
    # Top-level defaults still present:
    assert cfg["fetch"]["http_timeout_s"] == 10


def test_missing_explicit_path_raises(tmp_path):
    bad = tmp_path / "does-not-exist.toml"
    with pytest.raises(FileNotFoundError) as exc:
        load_config(toml_path=bad)
    assert "does-not-exist.toml" in str(exc.value)
