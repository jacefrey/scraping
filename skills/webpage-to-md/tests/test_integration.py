"""Live-URL integration test — gated; not run in default suite (spec §8.8)."""
from pathlib import Path
import pytest
from webpage_to_md import convert


@pytest.mark.integration
def test_live_convert_example_com(tmp_path):
    result = convert("https://example.com/", output_dir=tmp_path)
    assert result.md_generated is True
    assert result.markdown_path.is_file()
    text = result.markdown_path.read_text()
    assert "Example Domain" in text
