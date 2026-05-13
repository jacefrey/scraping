"""Live-URL integration test — gated (spec §8.8)."""
from pathlib import Path
import pytest
from webpage_to_pdf import convert


@pytest.mark.integration
def test_live_convert_example_com(tmp_path):
    result = convert("https://example.com/", output_dir=tmp_path)
    assert result.pdf_path.is_file()
    assert result.pdf_path.stat().st_size > 0
    # Magic-byte check on the produced PDF
    assert result.pdf_path.read_bytes()[:4] == b"%PDF"
