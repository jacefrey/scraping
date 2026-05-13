"""Page-format resolution tests (spec §6.4)."""
import pytest
from webpage_to_pdf.page_format import resolve_page_format, ResolvedFormat


def test_continuous_basic():
    rf = resolve_page_format(
        page_format="continuous",
        page_height_px=4800,
        viewport_width_px=1280,
    )
    # 4800 px / 96 dpi = 50"
    assert rf.is_continuous
    assert rf.height_in == pytest.approx(50.0)
    assert rf.width_in == pytest.approx(13.33, rel=0.01)
    assert rf.fell_back is False


def test_screen_is_alias_for_continuous():
    rf = resolve_page_format("screen", page_height_px=1000, viewport_width_px=1280)
    assert rf.is_continuous


def test_continuous_caps_at_200_inches():
    # 30,000 px / 96 dpi = 312.5"
    rf = resolve_page_format(
        page_format="continuous",
        page_height_px=30000,
        viewport_width_px=1280,
    )
    assert rf.fell_back is True
    # Falls back to screen-paginated
    assert rf.is_continuous is False
    assert rf.width_in == pytest.approx(13.33, rel=0.01)
    assert rf.height_in == pytest.approx(8.33, rel=0.01)


def test_letter_dimensions():
    rf = resolve_page_format("Letter", page_height_px=1, viewport_width_px=1280)
    assert rf.width_in == 8.5
    assert rf.height_in == 11.0
    assert rf.is_continuous is False


def test_a4_dimensions():
    rf = resolve_page_format("A4", page_height_px=1, viewport_width_px=1280)
    assert rf.width_in == pytest.approx(8.27, rel=0.01)
    assert rf.height_in == pytest.approx(11.69, rel=0.01)


def test_legal_dimensions():
    rf = resolve_page_format("Legal", page_height_px=1, viewport_width_px=1280)
    assert rf.width_in == 8.5
    assert rf.height_in == 14.0


def test_screen_paginated_dimensions():
    rf = resolve_page_format("screen-paginated", page_height_px=1, viewport_width_px=1280)
    assert rf.width_in == pytest.approx(13.33, rel=0.01)
    assert rf.height_in == pytest.approx(8.33, rel=0.01)


def test_dict_passthrough():
    rf = resolve_page_format(
        {"width": "16in", "height": "12in"}, page_height_px=1, viewport_width_px=1280
    )
    assert rf.raw == {"width": "16in", "height": "12in"}


def test_unknown_format_raises():
    from webpage_to_pdf.errors import ConvertError
    with pytest.raises(ConvertError):
        resolve_page_format("nope", page_height_px=1, viewport_width_px=1280)
