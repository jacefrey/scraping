"""Public convert() orchestration for webpage-to-pdf (spec §6.2)."""
from __future__ import annotations
import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Union

from playwright.sync_api import sync_playwright

from webpage_to_pdf._clock import _clock
from webpage_to_pdf.config import load_config, fingerprint
from webpage_to_pdf.dom_ops import (
    apply_article_mask, inject_base_href,
    strip_selectors as _strip_selectors,
)
from webpage_to_pdf.errors import ConvertError
from webpage_to_pdf.manifest import append_manifest_row
from webpage_to_pdf.naming import derive_stem
from webpage_to_pdf.page_format import resolve_page_format
from webpage_to_pdf.pdf_render import (
    flatten_sticky_elements,
    hide_fixed_elements,
    measure_scroll_height,
    render_pdf,
    run_lazy_load_loop,
)
from webpage_to_pdf.result import ConvertResult
from webpage_to_pdf.routing import SourceKind, looks_like_pdf, resolve_source
from webpage_to_pdf.sidecar import read_meta_sidecar, write_meta_sidecar
from webpage_to_pdf.skill_imports import use, validate_imported

use("web-fetch")
import webfetch  # noqa: E402
validate_imported("webfetch", "web-fetch")
from webfetch import fetch as _wf_fetch  # noqa: E402
WEB_FETCH_VERSION = getattr(webfetch, "__version__", "unknown")


def _fetch(url: str):
    """Indirection so tests can patch webpage_to_pdf.convert._fetch."""
    return _wf_fetch(url)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resolve_flatten_sticky(cfg_value: Any, page_format: str | dict) -> bool:
    """Spec §6.6: 'auto' → False for continuous, True for paginated."""
    if isinstance(cfg_value, bool):
        return cfg_value
    if isinstance(cfg_value, str) and cfg_value.lower() == "auto":
        if isinstance(page_format, str) and page_format in ("continuous", "screen"):
            return False
        return True
    return False


def _resolve_inject_page_break(cfg_value: Any, page_format: str | dict) -> bool:
    if isinstance(cfg_value, bool):
        return cfg_value
    if isinstance(cfg_value, str) and cfg_value.lower() == "auto":
        if isinstance(page_format, str) and page_format in ("continuous", "screen"):
            return False
        return True
    return False


def convert(
    source: Union[str, Path],
    output_dir: Path,
    *,
    output_stem: str | None = None,
    selector: str | None = None,
    page_format: Any = None,
    render_mode: str | None = None,
    margin_in: float | None = None,
    flatten_sticky: Any = None,
    base_url: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> ConvertResult:
    """URL or local-source → PDF (spec §6.1, §6.2)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if cfg is None:
        cfg = load_config()
    render_cfg = cfg["render"]
    config_sha256 = fingerprint(cfg)
    manifest_path = output_dir / "manifest.jsonl"

    eff_page_format = page_format or render_cfg["page_format"]
    eff_render_mode = render_mode or render_cfg["render_mode"]
    eff_margin_in = margin_in if margin_in is not None else render_cfg["margin_in"]
    eff_flatten = flatten_sticky if flatten_sticky is not None else render_cfg["flatten_sticky"]
    hide_fixed = bool(render_cfg.get("hide_fixed", False))
    flatten_bool = _resolve_flatten_sticky(eff_flatten, eff_page_format)
    inject_pb = _resolve_inject_page_break(render_cfg["inject_page_break_avoid"], eff_page_format)

    kind, value = resolve_source(source)

    if kind == SourceKind.LOCAL:
        return _convert_local(
            path=value,
            output_dir=output_dir,
            output_stem=output_stem,
            selector=selector,
            page_format=eff_page_format,
            margin_in=eff_margin_in,
            flatten_bool=flatten_bool,
            hide_fixed=hide_fixed,
            inject_pb=inject_pb,
            base_url=base_url,
            cfg=cfg, render_cfg=render_cfg,
            config_sha256=config_sha256,
            manifest_path=manifest_path,
        )

    return _convert_url(
        url=value,
        output_dir=output_dir,
        output_stem=output_stem,
        selector=selector,
        page_format=eff_page_format,
        render_mode=eff_render_mode,
        margin_in=eff_margin_in,
        flatten_bool=flatten_bool,
        hide_fixed=hide_fixed,
        inject_pb=inject_pb,
        cfg=cfg, render_cfg=render_cfg,
        config_sha256=config_sha256,
        manifest_path=manifest_path,
    )


def _convert_url(
    *,
    url: str,
    output_dir: Path,
    output_stem: str | None,
    selector: str | None,
    page_format: Any,
    render_mode: str,
    margin_in: float,
    flatten_bool: bool,
    hide_fixed: bool,
    inject_pb: bool,
    cfg: dict[str, Any],
    render_cfg: dict[str, Any],
    config_sha256: str,
    manifest_path: Path,
) -> ConvertResult:
    started = _clock()
    try:
        result = _fetch(url)
    except Exception as e:
        completed = _clock()
        append_manifest_row(
            manifest_path, status="failed", result=None,
            requested_url=url,
            error_category=getattr(e, "error_category", "unknown"),
            error_message=str(e),
            config_sha256=config_sha256,
            duration_ms=(completed - started).total_seconds() * 1000,
            started_at=started, completed_at=completed,
            render_mode=render_mode, page_format=page_format,
            flatten_sticky=flatten_bool, hide_fixed=hide_fixed,
        )
        raise

    stem = output_stem or derive_stem(result.final_url)

    # PDF passthrough
    if (result.content_type or "").lower().startswith("application/pdf"):
        return _passthrough_pdf_from_bytes(
            result=result, output_dir=output_dir, stem=stem,
            config_sha256=config_sha256,
            manifest_path=manifest_path, started=started,
            page_format=page_format,
        )

    if not (result.content_type or "").lower().startswith("text/html"):
        completed = _clock()
        msg = f"unsupported content type: {result.content_type}"
        append_manifest_row(
            manifest_path, status="failed", result=result,
            error_category="unsupported_content_type",
            error_message=msg, config_sha256=config_sha256,
            duration_ms=(completed - started).total_seconds() * 1000,
            render_mode=render_mode, page_format=page_format,
            flatten_sticky=flatten_bool, hide_fixed=hide_fixed,
        )
        raise ConvertError(msg)

    # Persist source HTML + sidecar
    out_html = output_dir / f"{stem}.html"
    out_html.write_bytes(result.content)
    write_meta_sidecar(
        out_html.with_suffix(".html.meta.json"),
        result=result, web_fetch_version=WEB_FETCH_VERSION,
    )

    if render_mode == "live":
        return _render_live(
            url=result.final_url,
            result=result,
            stem=stem,
            output_dir=output_dir, source_html_path=out_html,
            selector=selector,
            page_format=page_format,
            margin_in=margin_in,
            flatten_bool=flatten_bool, hide_fixed=hide_fixed,
            inject_pb=inject_pb,
            cfg=cfg, render_cfg=render_cfg,
            config_sha256=config_sha256,
            manifest_path=manifest_path,
            started=started,
        )

    # captured_html lands in B.2.13
    return _render_captured(
        source_html=result.content,
        result=result,
        stem=stem,
        output_dir=output_dir, source_html_path=out_html,
        selector=selector,
        page_format=page_format,
        margin_in=margin_in,
        flatten_bool=flatten_bool, hide_fixed=hide_fixed,
        inject_pb=inject_pb,
        cfg=cfg, render_cfg=render_cfg,
        config_sha256=config_sha256,
        manifest_path=manifest_path,
        started=started,
        base_url=result.final_url,
    )


def _render_live(
    *,
    url: str,
    result,
    stem: str,
    output_dir: Path,
    source_html_path: Path,
    selector: str | None,
    page_format: Any,
    margin_in: float,
    flatten_bool: bool,
    hide_fixed: bool,
    inject_pb: bool,
    cfg: dict[str, Any],
    render_cfg: dict[str, Any],
    config_sha256: str,
    manifest_path: Path,
    started,
) -> ConvertResult:
    out_pdf = output_dir / f"{stem}.pdf"
    rendered_html_artifact: str | None = None
    rendered_html_path: Path | None = None
    render_html_sha256: str | None = None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={
            "width": render_cfg["viewport"]["width_px"],
            "height": render_cfg["viewport"]["height_px"],
        })
        page = context.new_page()
        page.goto(url)

        if render_cfg.get("strip_selectors"):
            for sel in render_cfg["strip_selectors"]:
                page.evaluate(
                    f"document.querySelectorAll({sel!r}).forEach(e => e.remove());"
                )
        if selector:
            page.evaluate(
                """(sel) => {
                    const tgt = document.querySelector(sel);
                    if (!tgt) return;
                    let cur = tgt;
                    while (cur) {
                        cur.classList.add('__wpdf_visible__');
                        cur = cur.parentElement;
                    }
                    tgt.querySelectorAll('*').forEach(d => d.classList.add('__wpdf_visible__'));
                    const style = document.createElement('style');
                    style.textContent =
                        ':not(.__wpdf_visible__){display:none !important;}' +
                        '.__wpdf_visible__{display:revert;}';
                    document.head.appendChild(style);
                }""",
                selector,
            )

        run_lazy_load_loop(page, cfg)

        if hide_fixed:
            hide_fixed_elements(page)
        elif flatten_bool:
            flatten_sticky_elements(page)

        # Resolve page geometry
        if isinstance(page_format, str) and page_format in ("continuous", "screen"):
            page_height_px = measure_scroll_height(page)
        else:
            page_height_px = 1
        rf = resolve_page_format(
            page_format,
            page_height_px=page_height_px,
            viewport_width_px=render_cfg["viewport"]["width_px"],
        )

        render_pdf(
            page,
            out_path=out_pdf,
            width_in=rf.width_in if not isinstance(rf.raw, dict) else 0,
            height_in=rf.height_in if not isinstance(rf.raw, dict) else 0,
            margin_in=margin_in,
            inject_page_break_avoid=inject_pb,
        )

        if render_cfg.get("persist_rendered_html", True):
            rendered = page.content().encode("utf-8")
            rendered_html_path = output_dir / f"{stem}.rendered.html"
            rendered_html_path.write_bytes(rendered)
            rendered_html_artifact = rendered_html_path.name
            render_html_sha256 = _sha256(rendered)

        browser.close()

    completed = _clock()
    append_manifest_row(
        manifest_path, status="ok", result=result,
        source_artifact=source_html_path.name,
        derived_artifact=out_pdf.name,
        selector=selector,
        config_sha256=config_sha256,
        duration_ms=(completed - started).total_seconds() * 1000,
        render_mode="live",
        page_format=page_format,
        flatten_sticky=flatten_bool,
        hide_fixed=hide_fixed,
        live_double_fetch=True,
        render_html_sha256=render_html_sha256,
        rendered_html_artifact=rendered_html_artifact,
        passthrough=False,
    )
    return ConvertResult(
        pdf_path=out_pdf,
        source_html_path=source_html_path,
        rendered_html_path=rendered_html_path,
        render_mode="live",
        live_double_fetch=True,
        passthrough=False,
    )


def _render_captured(**kwargs) -> ConvertResult:
    """Stub — replaced in B.2.13."""
    raise ConvertError("captured_html render mode not yet implemented; see B.2.13")


def _convert_local(**kwargs) -> ConvertResult:
    """Stub — replaced in B.2.14."""
    raise ConvertError("local-input path not yet implemented; see B.2.14")


def _passthrough_pdf_from_bytes(
    *, result, output_dir: Path, stem: str, config_sha256: str,
    manifest_path: Path, started, page_format,
) -> ConvertResult:
    """URL PDF response → copy bytes, no render."""
    out_pdf = output_dir / f"{stem}.pdf"
    out_pdf.write_bytes(result.content)
    completed = _clock()
    append_manifest_row(
        manifest_path, status="ok", result=result,
        source_artifact=out_pdf.name,
        derived_artifact=None,
        selector=None,
        config_sha256=config_sha256,
        duration_ms=(completed - started).total_seconds() * 1000,
        render_mode=None, page_format=None,
        flatten_sticky=None, hide_fixed=None,
        live_double_fetch=False,
        render_html_sha256=None,
        rendered_html_artifact=None,
        passthrough=True,
    )
    return ConvertResult(
        pdf_path=out_pdf,
        source_html_path=None,
        rendered_html_path=None,
        render_mode=None,
        live_double_fetch=False,
        passthrough=True,
    )
