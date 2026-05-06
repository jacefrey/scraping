"""Config loader tests (spec §7.6, §8.3)."""
import textwrap
import pytest
from apify_runner.config import load_config


def test_defaults_when_no_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = load_config()
    assert cfg["apify"]["poll_interval_s"] == 5
    assert cfg["apify"]["default_timeout_s"] == 600
    assert cfg["apify"]["default_dataset_mode"] == "list"
    assert cfg["apify"]["max_dataset_items"] == 10000
    assert cfg["apify"]["jsonl_max_dataset_items"] == 100000
    assert cfg["apify"]["jsonl_max_dataset_bytes"] == 5_000_000_000
    assert cfg["apify"]["abort_on_timeout"] is False
    assert cfg["apify"]["strict_permissions"] is False
    assert cfg["apify"]["api_base"] == "https://api.apify.com/v2"
    assert cfg["apify"]["cost_buffer_percent"] == 0
    assert cfg["apify"]["dataset"]["on_partial"] == "rename"


def test_cwd_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "apify-runner.toml").write_text(textwrap.dedent("""
        [apify]
        poll_interval_s = 1
        cost_buffer_percent = 10
    """))
    cfg = load_config()
    assert cfg["apify"]["poll_interval_s"] == 1
    assert cfg["apify"]["cost_buffer_percent"] == 10
    # other defaults still present
    assert cfg["apify"]["default_timeout_s"] == 600


def test_user_config_layer(tmp_path, monkeypatch):
    """The ~/.config/apify-runner.toml layer is loaded when present."""
    home = tmp_path / "home"
    user_cfg_dir = home / ".config"
    user_cfg_dir.mkdir(parents=True)
    (user_cfg_dir / "apify-runner.toml").write_text(
        "[apify]\npoll_interval_s = 42\n"
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg["apify"]["poll_interval_s"] == 42


def test_cwd_overrides_user_config(tmp_path, monkeypatch):
    """CWD config takes precedence over ~/.config."""
    home = tmp_path / "home"
    user_cfg_dir = home / ".config"
    user_cfg_dir.mkdir(parents=True)
    (user_cfg_dir / "apify-runner.toml").write_text(
        "[apify]\npoll_interval_s = 42\n"
    )
    monkeypatch.setenv("HOME", str(home))
    cwd = tmp_path / "project"
    cwd.mkdir()
    (cwd / "apify-runner.toml").write_text("[apify]\npoll_interval_s = 7\n")
    monkeypatch.chdir(cwd)
    cfg = load_config()
    assert cfg["apify"]["poll_interval_s"] == 7


def test_deep_nested_override(tmp_path, monkeypatch):
    """Sub-table overrides merge correctly via _deep_merge."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "apify-runner.toml").write_text(
        '[apify.dataset]\non_partial = "delete"\n'
    )
    cfg = load_config()
    assert cfg["apify"]["dataset"]["on_partial"] == "delete"
    # Top-level defaults still present:
    assert cfg["apify"]["poll_interval_s"] == 5


def test_missing_explicit_path_raises(tmp_path):
    bad = tmp_path / "does-not-exist.toml"
    with pytest.raises(FileNotFoundError) as exc:
        load_config(toml_path=bad)
    assert "does-not-exist.toml" in str(exc.value)
