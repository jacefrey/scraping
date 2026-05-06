"""Env-resolution tests (spec §7.3)."""
import os
import pytest
from pathlib import Path
from apify_runner import ENV_AUTODISCOVER
from apify_runner.errors import ApifyAuthError
from apify_runner.env import resolve_apify_token


def test_autodiscover_finds_env_in_cwd(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()  # establish git-root boundary
    (tmp_path / ".env").write_text("APIFY_API_TOKEN=tok-cwd\n")
    os.chmod(tmp_path / ".env", 0o600)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path.parent))
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)

    token, source = resolve_apify_token(env_file=ENV_AUTODISCOVER)
    assert token == "tok-cwd"
    assert source == str(tmp_path / ".env")


def test_autodiscover_walks_to_git_root(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("APIFY_API_TOKEN=tok-root\n")
    os.chmod(tmp_path / ".env", 0o600)
    deeper = tmp_path / "src" / "app"
    deeper.mkdir(parents=True)
    monkeypatch.chdir(deeper)
    monkeypatch.setenv("HOME", str(tmp_path.parent))
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)

    token, source = resolve_apify_token(env_file=ENV_AUTODISCOVER)
    assert token == "tok-root"
    assert source == str(tmp_path / ".env")


def test_autodiscover_does_not_cross_git_root(tmp_path, monkeypatch):
    """A .env above the git-root must NOT be picked up."""
    (tmp_path / ".env").write_text("APIFY_API_TOKEN=tok-above\n")
    os.chmod(tmp_path / ".env", 0o600)
    inner = tmp_path / "project"
    inner.mkdir()
    (inner / ".git").mkdir()
    monkeypatch.chdir(inner)
    monkeypatch.setenv("HOME", str(tmp_path.parent))
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)

    with pytest.raises(ApifyAuthError):
        resolve_apify_token(env_file=ENV_AUTODISCOVER)


def test_explicit_path_used_directly(tmp_path, monkeypatch):
    custom = tmp_path / "custom.env"
    custom.write_text("APIFY_API_TOKEN=tok-explicit\n")
    os.chmod(custom, 0o600)
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    token, source = resolve_apify_token(env_file=custom)
    assert token == "tok-explicit"


def test_env_file_none_skips_discovery(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("APIFY_API_TOKEN=should-not-load\n")
    os.chmod(tmp_path / ".env", 0o600)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APIFY_API_TOKEN", "from-environ")
    token, source = resolve_apify_token(env_file=None)
    assert token == "from-environ"
    assert source == "os.environ"


def test_missing_everything_raises_auth_error(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    with pytest.raises(ApifyAuthError):
        resolve_apify_token(env_file=ENV_AUTODISCOVER)


def test_loose_permissions_warning(tmp_path, monkeypatch, caplog):
    (tmp_path / ".git").mkdir()
    env = tmp_path / ".env"
    env.write_text("APIFY_API_TOKEN=tok-loose\n")
    os.chmod(env, 0o644)  # world-readable
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path.parent))
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    import logging
    with caplog.at_level(logging.WARNING):
        token, _ = resolve_apify_token(env_file=ENV_AUTODISCOVER)
    assert token == "tok-loose"
    assert any("loose permissions" in rec.message for rec in caplog.records)


def test_strict_permissions_refuses(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    env = tmp_path / ".env"
    env.write_text("APIFY_API_TOKEN=tok\n")
    os.chmod(env, 0o644)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path.parent))
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    with pytest.raises(ApifyAuthError):
        resolve_apify_token(env_file=ENV_AUTODISCOVER, strict_permissions=True)
